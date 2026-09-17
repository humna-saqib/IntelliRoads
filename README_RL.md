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

## 2. Training

Initially trained for 1,000 episodes, then continued for a further 300 epochs (1,300 total) under **randomized per-episode traffic demand** — see [`app/sumo_tools/route_generator.py`](backend/app/sumo_tools/route_generator.py). The original 1,000-episode run used a single fixed, non-randomized traffic scenario; every episode replayed identical demand, so the model was effectively specialized to one traffic pattern rather than general conditions. The additional 300 epochs, warm-started from that checkpoint, exposed the agent to varied vehicle spawn rates and directional demand so it generalizes rather than memorizes.

The final model is saved at `backend/data/models/dqn_agent.pt` — the path the live backend loads from at startup.

| Hyperparameter | Value |
| :--- | :---: |
| Total episodes | 1,300 (1,000 original + 300 under randomized demand) |
| Steps/episode | 25 |
| Discount factor (γ) | 0.95 |
| Learning rate (α) | 0.0005 |
| Replay capacity | 10,000 |
| Batch size | 32 |
| ε start / end | 1.0 / 0.08 |
| ε decay | 325 epochs (25% of total, linear) |
| Target network sync | every 5 epochs |

## 3. Evaluation

The final DQN agent was benchmarked against two baselines over 30 episodes each (200 steps/episode) on real SUMO traffic, with **randomized traffic demand per episode** (seeded, held out from the seeds used during training — see `EVAL_SEED_OFFSET` in `evaluate_controllers.py`):

- **Fixed-Time** — static pre-timed green intervals
- **Rule-Based** — dynamic thresholds on queue count
- **DQN** — trained agent, greedy policy (ε = 0)

Results are mean ± standard deviation across the 30 episodes per controller (raw data: `backend/evaluation_results/eval_raw.csv`):

| Metric | Fixed-Time | Rule-Based | Trained DQN | vs. best baseline |
| :--- | :---: | :---: | :---: | :---: |
| Avg waiting time (s) | 4.32 ± 0.17 | 5.50 ± 0.15 | **3.63 ± 0.11** | −16.0% |
| Avg travel time (s) | 15.61 ± 0.22 | 17.15 ± 0.20 | **14.72 ± 0.14** | −5.7% |
| Avg queue length (veh) | 10.67 ± 0.16 | 10.15 ± 0.21 | **9.94 ± 0.21** | −6.8% vs Fixed-Time |
| Throughput (veh/ep) | 541.13 ± 9.11 | 543.53 ± 9.26 | **546.27 ± 9.06** | best |
| Episode reward | −3011.15 ± 82.45 | −3023.84 ± 109.21 | **+2502.68 ± 219.66** | positive vs. negative |

**Note on an earlier, retracted figure:** an initial evaluation reported a 32% waiting-time improvement. That run used the same non-randomized single-scenario setup as the original training run — every "episode" replayed identical traffic, so standard deviation was 0.0000 across all metrics, meaning no real variance was being measured. That result has been superseded by the randomized evaluation above, which is smaller (16% vs. 32%) but statistically valid.

### Statistical significance

An unpaired Welch's t-test (DQN vs. Fixed-Time, n=30 independent episodes each — see [`backend/evaluation_results/significance_test.py`](backend/evaluation_results/significance_test.py)) confirms the improvement is not attributable to chance:

| Metric | t-statistic | df | Significance |
| :--- | :---: | :---: | :---: |
| Avg waiting time | −18.807 | 48.2 | p < 0.001 |
| Avg travel time | −18.807 | 48.2 | p < 0.001 |
| Avg queue length | −15.135 | 53.8 | p < 0.001 |
| Episode reward | 128.720 | 37.0 | p < 0.001 |

A Welch's (unpaired) test is used rather than a paired test because each controller's 30 episodes use independent, non-overlapping random seeds — episode 1 of Fixed-Time and episode 1 of DQN are different traffic scenarios, not matched pairs.

## 4. Reproducing results

Run from `backend/` with the virtual environment active:

```bash
# 1. Evaluate all three controllers (writes to backend/evaluation_results/)
python evaluate_controllers.py --episodes 30 --steps 200

# 2. Run the significance test
python evaluation_results/significance_test.py

# 3. Generate comparison charts
python generate_comparison_graphs.py
```

(Windows: use `venv\Scripts\python.exe` in place of `python`.)

## 5. Directory structure

```
backend/
├── data/models/
│   └── dqn_agent.pt               # Final trained weights (loaded by the live backend)
├── final_dqn_model/
│   └── dqn_episode_*.pt           # Training checkpoints (every 50 epochs)
├── evaluation_results/
│   ├── eval_raw.csv               # Per-episode benchmark data (30 ep × 3 controllers)
│   ├── eval_summary.csv           # Mean/std summary
│   ├── eval_summary.json
│   └── significance_test.py       # Welch's t-test, DQN vs Fixed-Time
└── comparison_graphs/
    ├── waiting_time_comparison.png
    ├── travel_time_comparison.png
    ├── queue_length_comparison.png
    ├── throughput_comparison.png
    ├── reward_comparison.png
    └── overall_benchmark_comparison.png

rl_pipeline/
├── training_results/
│   └── episode_log.csv            # Original 1,000-episode training log
└── training_graphs/
    └── reward_curve.png           # Original training reward curve
```
