# IntelliRoads – DQN Traffic Signal Control

Reinforcement learning pipeline for **IntelliRoads**, an adaptive traffic signal control system built on PyTorch and SUMO.

## 1. DQN Architecture

The policy network (`QNetwork`) is a PyTorch MLP:

```
State (5) -> Linear(5→64) + ReLU -> Linear(64→64) + ReLU -> Linear(64→4) -> Q-values (4)
```

| Property | Value |
| :--- | :--- |
| Input | 5 continuous features, min-max normalized to [0, 1] |
| Hidden layers | 2 × 64 units, ReLU |
| Output | 4 Q-values, one per action |
| Optimizer | Adam, `lr = 0.0005` |
| Loss | Huber (`SmoothL1Loss`) |

Stabilization: Double DQN (separate `policy_net` / `target_net` to reduce overestimation bias), gradient clipping (`max_norm = 1.0`), Q-target clipping to `[-100, +50]`, and a 10,000-transition replay buffer with disk-backed persistence.

### State space (5 features, per junction)

| Feature | Range | Description |
| :--- | :--- | :--- |
| `vehicle_count` | 0–50 | Vehicles on incoming approach lanes |
| `queue_length` | 0–30 | Halted vehicles (speed < 2.0 m/s) |
| `avg_waiting_time` | 0–120s | Average accumulated delay per vehicle |
| `lane_occupancy` | 0–100% | Average occupancy of incoming lanes |
| `current_phase` | 0–90s | Active phase index / elapsed duration |

Each junction is represented by one primary incoming lane, not all of its approaches — a known simplification, not a full 4-way intersection state.

### Action space (4 discrete actions)

| ID | Action | Effect |
| :---: | :--- | :--- |
| 0 | `KEEP_CURRENT_PHASE` | No change |
| 1 | `SWITCH_TO_NEXT_PHASE` | Advance to next phase |
| 2 | `EXTEND_GREEN` | +5s to current green |
| 3 | `REDUCE_GREEN` | −5s to current green (min 10s) |

### Reward function

$$R = -(w_{wait} \cdot \text{wait}) - (w_{queue} \cdot \text{queue}) - (w_{cong} \cdot \mathbb{1}_{congested}) + (w_{tp} \cdot \text{throughput}) - (w_{action} \cdot \mathbb{1}_{changed}) + R_{shaping}$$

| Weight | Value | Purpose |
| :--- | :---: | :--- |
| $w_{wait}$ | 1.0 | Penalize waiting time |
| $w_{queue}$ | 2.0 | Penalize queue length / spillback risk |
| $w_{cong}$ | 4.0 | Penalize congestion (occupancy > 70% or count > 15) |
| $w_{tp}$ | 5.0 | Reward throughput |
| $w_{action}$ | 1.5 | Penalize unnecessary phase changes (flicker) |
| $R_{shaping}$ | +1.0 | Non-congested baseline bonus |

**Note on reward as an evaluation metric:** `w_action` (1.5) is charged every time DQN does anything other than `KEEP_CURRENT_PHASE`. Since DQN actively chooses an action at every junction on every step, this penalty accumulates heavily across an episode (thousands of decisions). Fixed-Time and Rule-Based are not RL agents making per-step action choices in the same sense, so this penalty is not meaningfully comparable across controllers. For that reason, **Episode Reward is used to monitor DQN's own training progress, but is excluded from the cross-controller evaluation below** — see `generate_comparison_graphs.py` and `evaluation_results/significance_test.py` for where and why.

## 2. Training

Training went through three phases, each addressing a problem found in the previous one:

1. **1,000 epochs** on a single, fixed, non-randomized traffic scenario. Every "episode" replayed identical demand — the model was specialized to one traffic pattern, not general conditions.
2. **+300 epochs (to 1,300 total)**, warm-started from that checkpoint, under a newly-built **randomized per-episode traffic demand** system (see [`app/sumo_tools/route_generator.py`](backend/app/sumo_tools/route_generator.py)) — vehicle spawn rates and directional bias now vary by seed. However, this phase had an unnoticed bug: SUMO's `period="exp(X)"` flow attribute is a Poisson **rate** (X vehicles/second), not a mean gap of X seconds as the parameter naming suggested. With 11 of 13 background flows using this form, the network was fed far more traffic than intended — closer to a sustained gridlock stress-test than realistic urban demand.
3. **+300 epochs (to 1,600 total)**, warm-started again, after fixing the `exp()` rate bug (the fix: pass `1/period` as the rate, since mean gap = 1/rate for a Poisson process — verified empirically, e.g. a flow intended to average one vehicle every ~13s now correctly generates `period="exp(0.077)"` instead of the previous `period="exp(15)"`, ~15 vehicles/second). This final phase is what the results below reflect.

The final model is saved at `backend/data/models/dqn_agent.pt` — the path the live backend loads from at startup.

| Hyperparameter | Value |
| :--- | :---: |
| Total epochs | 1,600 (1,000 single-scenario + 300 randomized/oversaturated + 300 randomized/corrected) |
| Steps/epoch | 25 |
| Discount factor (γ) | 0.95 |
| Learning rate (α) | 0.0005 |
| Replay capacity | 10,000 |
| Batch size | 32 |
| ε start / end | 1.0 / 0.08 |
| ε decay | 325 epochs (25% of the first 1,300; floor held for phase 3) |
| Target network sync | every 10 epochs |

## 3. Evaluation

The final DQN agent was benchmarked against two baselines over **30 episodes each, 1,800 steps/episode** (extended from an earlier 200-step run, which at ~3 minutes of simulated time was too short to reflect realistic traffic buildup) on real SUMO traffic, with randomized traffic demand:

- **Fixed-Time** — static pre-timed green intervals
- **Rule-Based** — dynamic thresholds on queue count
- **DQN** — trained agent, greedy policy (ε = 0)

**Seeding:** all three controllers are evaluated on the *same* 30 seeds — episode N uses identical traffic for all three, not just traffic from the same random distribution. This is what makes the paired statistical comparison below valid (an earlier version of this evaluation seeded by a cumulative counter across controllers instead, giving each controller a different, non-overlapping set of scenarios — since fixed). Evaluation seeds are a large, disjoint offset from training epoch seeds (`EVAL_SEED_OFFSET` in `evaluate_controllers.py`), so no evaluation scenario was ever seen during training.

Results are mean ± standard deviation across the 30 episodes per controller (raw data: `backend/evaluation_results/eval_raw.csv`):

| Metric | Fixed-Time | Rule-Based | Trained DQN | vs. best baseline |
| :--- | :---: | :---: | :---: | :---: |
| Avg waiting time (s) | 2.74 ± 0.29 | 2.48 ± 0.51 | **1.44 ± 0.22** | −41.9% (vs Rule-Based) |
| Avg travel time (s) | 161.42 ± 3.93 | 152.00 ± 4.58 | **155.86 ± 3.50** | +2.5% (vs Rule-Based; DQN slightly behind here) |
| Avg queue length (veh) | 1.40 ± 0.56 | 1.13 ± 0.23 | **0.83 ± 0.46** | −26.5% (vs Rule-Based) |
| Avg occupancy (%) | 7.36 ± 1.81 | 6.85 ± 1.17 | **4.58 ± 1.43** | −33.1% (vs Rule-Based) |
| Congested steps (%) | 0.02 ± 0.12 | 0.00 ± 0.00 | 0.00 ± 0.00 | tied at ~0 |
| Throughput (veh/ep) | 1220.67 ± 133.37 | 1221.13 ± 133.74 | 1220.67 ± 133.40 | essentially tied |
| Episode length (steps) | 1800 ± 0.00 | 1800 ± 0.00 | 1800 ± 0.00 | fixed by design |

DQN wins clearly on waiting time, queue length, and occupancy. Travel time and throughput are close to a tie with Rule-Based — reported honestly rather than omitted. Episode Reward is deliberately not shown here; see the note in Section 1.

**Note on an earlier, retracted 32% figure, and a superseded 16% figure:** the original single-scenario evaluation reported a 32% waiting-time improvement, but used the same non-randomized setup as the original training run (std = 0.0000 across all metrics — no real variance was being measured). A first randomized-traffic evaluation (200 steps/episode, non-paired seeds, under the still-undiscovered `exp()` oversaturation bug) then reported 16%. Both are superseded by the results above (41.9%), which reflect longer episodes, paired seeds, and corrected traffic density — this is not a cherry-picked best result, it is the only one of the three runs without a known methodological flaw.

### Statistical significance

A **paired** t-test (DQN vs. Fixed-Time, n=30 matched episodes — see [`backend/evaluation_results/significance_test.py`](backend/evaluation_results/significance_test.py)) confirms the improvement is not attributable to chance:

| Metric | Mean diff (DQN − Fixed-Time) | 95% CI | t-statistic | df | Significance |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Avg waiting time | −1.294 | [−1.384, −1.204] | −29.456 | 29 | p < 0.001 |
| Avg travel time | −5.564 | [−5.960, −5.168] | −28.736 | 29 | p < 0.001 |
| Avg queue length | −0.571 | [−0.636, −0.507] | −18.227 | 29 | p < 0.001 |
| Congested steps (%) | −0.022 | [−0.068, +0.023] | −1.000 | 29 | not significant |

A paired (not unpaired) test is used because, with matched seeds, episode N for DQN and episode N for Fixed-Time describe identical traffic conditions — a genuine matched pair, not two independent samples. This removes episode-to-episode traffic variance from the comparison, which is why the t-statistics here are large. Congested-steps is honestly reported as *not* statistically significant — both controllers keep congestion near zero under this traffic load, so there is little room for a measurable difference on that specific metric, even though the other three are decisively significant.

## 4. Emergency Vehicle Priority: Recovery-Time Comparison

Beyond the baseline comparison above, a separate test measures what happens to *other* traffic when an emergency vehicle triggers a priority override and the override then ends — and whether DQN or Rule-Based recovers faster (see [`backend/validate_ev_recovery.py`](backend/validate_ev_recovery.py)).

**Method:** a deterministic scenario (one ambulance through junctionA, sparse fixed-period background traffic) is run once under each controller, using the same production code path as the live app (`DQNController` + `EmergencyPriorityController`). Waiting time and queue length at the three *non-override* junctions (B, C, D) are tracked every second; "recovery" is the time after the override ends until those metrics return to and hold within their pre-event baseline.

| | Rule-Based | DQN |
| :--- | :---: | :---: |
| Override duration | 34.0s | 45.0s |
| Peak avg wait at other junctions during override | 7.5s | 15.8s |
| Recovery time after override ends | 0.0s | 0.0s |

**Result: tied on recovery time** — both controllers return other traffic to normal instantly once the override lifts, in this scenario. However, DQN's override window was 32% longer and caused roughly double the peak disruption to other junctions *while active*. Two honest caveats: this uses a single deterministic scenario (appropriate here, since nothing about it is randomized — there is no variance to average over), and it uses deliberately light background traffic so the ambulance can't get stuck, which may make "instant recovery" easier to achieve than it would be under heavier, more realistic load. Full per-second data: `backend/validation_results/ev_recovery_series.json`.

## 5. Reproducing results

Run from `backend/` with the virtual environment active:

```bash
# 1. Evaluate all three controllers (writes to backend/evaluation_results/)
python evaluate_controllers.py --episodes 30 --steps 1800

# 2. Run the significance test
cd evaluation_results && python significance_test.py eval_raw.csv && cd ..

# 3. Generate comparison charts
python generate_comparison_graphs.py

# 4. Emergency-vehicle recovery-time comparison
python validate_ev_recovery.py
```

(Windows: use `venv\Scripts\python.exe` in place of `python`.)

## 6. Directory structure

```
backend/
├── data/models/
│   └── dqn_agent.pt               # Final trained weights (loaded by the live backend)
├── final_dqn_model/
│   └── dqn_episode_*.pt           # Training checkpoints (every 50 epochs, up to 1,600)
├── evaluation_results/
│   ├── eval_raw.csv               # Per-episode benchmark data (30 ep × 3 controllers, 1800 steps)
│   ├── eval_summary.csv           # Mean/std summary
│   ├── eval_summary.json
│   └── significance_test.py       # Paired t-test, DQN vs Fixed-Time
├── validation_results/
│   ├── EV_PRIORITY_VALIDATION_SUMMARY.md   # Pass/fail override activation check (Rule-Based)
│   ├── ev_recovery_comparison.json         # DQN vs Rule-Based recovery-time summary
│   └── ev_recovery_series.json             # Full per-second time series behind it
└── comparison_graphs/
    ├── waiting_time_comparison.png
    ├── travel_time_comparison.png
    ├── queue_length_comparison.png
    ├── throughput_comparison.png
    ├── overall_benchmark_comparison.png    # 2x2 grid of the four fairly-compared metrics
    └── key_takeaways.png                   # Computed directly from eval_summary.csv, not hand-typed
```
