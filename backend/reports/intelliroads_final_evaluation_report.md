# IntelliRoads — Final Evaluation Report (FYP)

*Scope: the IntelliRoads Final Year Project worktree only (branch `fyp/stage1-observation-and-transitions`, HEAD `d8b9701`, with uncommitted FYP changes). Every number in this report was read programmatically from the stored artifacts listed in Appendix A; nothing was re-simulated for this report.*

---

## A. Executive summary

**Problem.** Fixed signal programmes cannot react to the traffic that is actually present. IntelliRoads investigates whether a learned controller can reduce vehicle delay at a small signalised network while respecting hard signal-safety rules.

**Approach.** A four-junction network (junctionA–D, 16 incoming lanes) is simulated in **SUMO 1.18.0** and controlled through **TraCI**. A **Double DQN** agent with one shared policy for all four junctions chooses, every 5 s, one of four actions (KEEP, SWITCH, EXTEND, REDUCE). Every action passes through a **safe action layer** (minimum green 10 s, maximum green 60 s, yellow fixed at 5 s, ±5 s steps, legal-action masks). The agent observes a normalised per-junction state. The final model uses the **obs-v2** schema: the original 11 features plus 4 phase-relative approach-presence features (15 in total).

**Evaluation.** The final evaluation used the project's pre-specified protocol:
- 300 s warm-up, 1,800 s measured window, new demand cut off at 2,100 s, drain of at most 600 s;
- 30 matched seeds (4,000,031–4,000,060) on which all four controllers saw identical traffic;
- primary metric: trip-based waiting time per vehicle (`wait_per_vehicle_all_s`).

**Principal measured findings (final evaluation, 30 matched seeds, 120 episodes, no failures):**

| Controller | Waiting time per vehicle (s), mean ± SD |
|---|---:|
| Fixed-Time | 28.86 ± 6.91 |
| Rule-Based | 24.82 ± 4.19 |
| Actuated-Style | 13.61 ± 2.95 |
| **obs-v2 DQN** | **11.95 ± 4.45** |

- Against **Fixed-Time**, the obs-v2 DQN reduced waiting time by **16.91 s** per vehicle (95 % CI [−18.59, −15.23]), with lower waiting on all 30 seeds.
- Against **Rule-Based**, the reduction was **12.87 s** (95 % CI [−13.60, −12.14]), again on all 30 seeds.
- Against the project's **Actuated-Style** heuristic, the reduction was **1.66 s** (95 % CI [−2.51, −0.82]), with lower waiting on 28 of 30 seeds.
- **Throughput** against Actuated-Style and Rule-Based was not distinguishable (both intervals include 0).
- A separate **head-to-head on 30 validation seeds** showed obs-v2 (episode 240) waiting **4.39 s** less than the original v1 model (episode 400), 95 % CI [−4.90, −3.87], better on 30 of 30 seeds.

**What has not been demonstrated.**
- Generalisation to other networks, demand patterns or training seeds.
- Behaviour with real detectors or real traffic.
- Any statistically corrected or confirmatory claim of superiority; all intervals are descriptive.
- That the custom Actuated-Style controller represents SUMO's native actuated control (it does not; see §C.4).

---

## B. System architecture and implementation

### B.1 Components

| Layer | Implementation (verified in source) |
|---|---|
| Simulation | SUMO 1.18.0 (`versions.sumo` in both training configs), network `sumo/network/intelliroads.net.xml`, config `sumo/config/intelliroads.sumocfg`. Each episode's routes are generated into a temporary file by `app/sumo_tools/route_generator.py`; the tracked route file is never written. |
| Control interface | TraCI (`traci`/`sumolib`). `app/environment/traffic_env.py` (`TrafficSignalEnv`) reads lane and vehicle state and issues `setPhase` / `setPhaseDuration` commands. |
| Observation | `app/environment/observation.py` (schemas `fyp-obs-v1`, `fyp-obs-v2`). |
| Safety | `app/environment/signal_safety.py` (`SignalSafetyConfig`, `legal_action_mask`, `command_for`, `validate_transition`). |
| Learning | `app/training/double_dqn.py` (`MaskedDoubleDQN`), `app/training/trainer.py`, `app/training/replay.py`, entry point `train_dqn.py`. |
| Selection | `app/evaluation/selection.py`, entry point `select_checkpoint.py`. |
| Evaluation | `app/evaluation/{protocol,runner,metrics,controllers,seeds}.py`, entry point `evaluate_fyp.py`. |
| Application | A FastAPI backend (`app/main.py`) and a React + TypeScript (Vite, Tailwind) frontend (`frontend/src`) exist in the repository. They were **not modified or evaluated** in this work; the results in this report come only from the offline evaluation pipeline above. |

### B.2 Observation generation and normalisation

One observation vector is produced per junction at every 5 s decision; all entries lie in [0, 1].

**v1 features (11)** (`FEATURE_NAMES`):

| # | Name | Meaning / normalisation |
|---|---|---|
| 0 | `count_frac` | vehicles on the junction's incoming lanes ÷ lane capacity (lane length / 7.5 m jam spacing) |
| 1 | `halting_frac` | halting vehicles (speed < 0.1 m/s) ÷ lane capacity |
| 2 | `mean_wait_norm` | mean accumulated waiting time per vehicle ÷ 100 s (`WAIT_MAX_S`, SUMO's waiting-time memory) |
| 3 | `occupancy` | length-weighted mean lane occupancy (fraction) |
| 4 | `halting_frac_g0` | halting fraction of the lanes served by the first green phase |
| 5 | `halting_frac_g1` | halting fraction of the lanes served by the second green phase |
| 6–9 | `phase_0` … `phase_3` | one-hot of the current phase (G, y, G, y) |
| 10 | `elapsed_norm` | time since the current phase started ÷ maximum green (60 s) |

**obs-v2 additional features (4)** (`PRESENCE_FEATURE_NAMES`). These are phase-relative counts of vehicles within the detector range D = 40 m of the stop line:

| # | Name | Meaning |
|---|---|---|
| 11 | `served_moving_near` | moving vehicles (speed ≥ 0.1 m/s) on the approach group the signal currently serves |
| 12 | `served_stopped_near` | stopped vehicles (speed < 0.1 m/s) on the served group |
| 13 | `opposing_moving_near` | moving vehicles on the other group |
| 14 | `opposing_stopped_near` | stopped vehicles on the other group |

- **Served group (`served_group`).** During green it is that green's group. During yellow it is the group whose green has just ended, because the programmes are G, y, G, y.
- **Normalisation.** Each count is divided by its group's physical capacity within D, Σ min(D, lane length) / 7.5 m, and clipped to [0, 1].
- **Clipping.** Clipping can occur when short vehicles pack more densely than 7.5 m. An integration test against independently logged counts bounds it at < 1 % of feature values.
- **Detector range.** 40 m was chosen to equal the Actuated-Style controller's detector range. It is documented in the source as "an experimental parameter, not a tuned optimum".
- **Effect on the v1 part.** The v1 part of a v2 vector is byte-identical to the v1 observation, and rewards and masks are unchanged (tested).

### B.3 Double DQN model and action selection

- **Network** (`QNetwork`): an MLP, input → 64 → ReLU → 64 → ReLU → 4 Q-values. The input is 11 features for v1 and 15 for v2; the final checkpoint's first layer is 64 × 15.
- **Shared policy.** One network serves all four junctions; each junction contributes its own transitions.
- **Training target** (`double_dqn_targets`): a* = argmax over legal actions of Q_policy(s′, ·); y = r + γ · Q_target(s′, a*). The next-state legality mask is applied to the policy network's argmax.
- **Training settings.**
  - Loss: Smooth-L1, with gradient clipping at 1.0.
  - Hard target-network update every 500 gradient steps.
  - Rewards scaled by 0.01, with no target clamping.
- **Action selection.**
  - During training: ε-greedy over legal actions.
  - During evaluation: greedy (ε = 0) masked argmax. An illegal action is never executed; the evaluation runner aborts if any action is coerced.
- **Reward.** The per-junction **legacy reward formula** is kept unchanged (`legacy_reward`): −1.0·mean wait − 2.0·halting − 4.0·congestion flag + 5.0·departures/s − 1.5·(non-KEEP action) + 1.0 if not congested, computed on corrected measurements. The reward was **not** redesigned in this project.

### B.4 Signal safety and legal-action masks

`SignalSafetyConfig` defaults (used for training and every evaluation):

| Parameter | Value |
|---|---|
| Minimum green | 10 s |
| Maximum green | 60 s |
| EXTEND / REDUCE step | 5 s |
| Yellow | 5 s, never altered |
| Minimum green left after REDUCE | 1 s |

The legal-action mask (`legal_action_mask`) works as follows:
- **KEEP** is always legal.
- **During yellow**, only KEEP is legal.
- **SWITCH** is legal once the green has run ≥ 10 s. It moves the signal to the programme's own yellow.
- **EXTEND** is legal if the total green stays ≤ 60 s.
- **REDUCE** is legal if it leaves ≥ 1 s of green and the total green stays ≥ 10 s.

`validate_transition` independently checks every phase change after the fact. Only the next phase is allowed, green duration must be within [10, 60] s, and yellow must last exactly 5 s. Any violation aborts an evaluation run.

### B.5 Workflows

1. **Training** (`train_dqn.py`): 400 episodes on training seeds 2,000,001–2,000,400. Proxy validation runs every 20 episodes on 5 seeds (3,000,001–3,000,005), using a lane-based waiting proxy (`mean_wait_s`). Periodic checkpoints `ckpt_epNNNN.pt` are written, and `best.json`/`best.pt` record the proxy-best checkpoint.
2. **Checkpoint selection** (`select_checkpoint.py` / `selection.py`): a two-stage re-ranking of the 20 periodic checkpoints. It uses the evaluation protocol's own trip metric on fresh validation seeds (§D.3).
3. **Final evaluation** (`evaluate_fyp.py --mode final --confirm-final`): runs once per checkpoint, guarded by `ledger.jsonl`, on reserved final seeds.

Seed ranges for these three workflows are disjoint and enforced in code (`app/evaluation/seeds.py`, `app/training/seeds.py`).

---

## C. Experimental methodology

### C.1 Episode structure (verified in `fyp_final_s0_obs_v2/protocol.json`)

| Item | Value |
|---|---|
| SUMO | 1.18.0 |
| Network | 4 signalised junctions (junctionA–D), 16 incoming lanes measured every second |
| Warm-up | 300 s (controllers act, nothing measured) |
| Measured window | 1,800 s (t ∈ [300, 2100)) |
| Demand cut-off | 2,100 s (`demand_end_s`) |
| Drain | until the network is empty, at most 600 s (horizon 2,700 s) |
| Decision interval | 5 s |
| Seeds | 30 matched seeds, 4,000,031 … 4,000,060 |
| Controllers | Fixed-Time, Rule-Based, Actuated-Style, obs-v2 DQN (120 episodes) |

### C.2 Matched seeds and trip accounting

- **Matched seeds.** Seed *k* determines both the generated demand and SUMO's random seed, so every controller faces identical traffic on seed *k*. The seed is the experimental unit (paired design).
- **Measured cohort.** Every vehicle inserted at or after t = 300 s.
- **Delayed insertions.** A vehicle inserted after 2,100 s is a delayed insertion of window demand. It stays in the cohort and is counted in `departed_after_window`.
- **Completed and unfinished trips.** A trip is *completed* if it arrives before the drain ends. Otherwise it is *unfinished*; never-inserted vehicles count as `trips_not_inserted` and are also unfinished. No trip is dropped silently.
- **Primary metric.** `wait_per_vehicle_all_s` = (1/n) Σ_v w_v over all inserted cohort trips. Here w_v is the time the vehicle spent at speed ≤ 0.1 m/s since insertion. Unfinished trips contribute the waiting accumulated until the run ends.
- **Travel time.** `travel_time_completed_s` covers completed trips only and is never mixed with unfinished ages. `unfinished_age_mean_s` is a lower bound reported separately.
- **Lane metrics.** Queue, occupancy, vehicles and congestion come from the measured window only (16 × 1,800 lane-seconds). Drain seconds are never included.
- **Congested lane-step.** A lane-second with occupancy > 0.70 or more than 15 vehicles.
- **Throughput.** Arrivals in [300, 2100) ÷ 0.5 h.
- **Drain fields.** `drain_s_used`, `drain_exhausted` (1 if the 600 s were used up) and `vehicles_left_at_end` are recorded per episode.
- **Abort conditions.** The run stops with an error rather than reporting if any of these occur:
  - wrong episode length or decision count;
  - any illegal action or safety violation;
  - lane observations ≠ 16 × 1,800;
  - a network that empties while trips are unfinished;
  - no vehicles in the measured window;
  - a Fixed-Time timing mismatch.

### C.3 Statistical procedure (EVALUATION_PROTOCOL.md §3)

- **Unit and aggregation.** One episode per seed and controller. Results are the unweighted mean and sample SD (ddof = 1) over seeds.
- **Paired differences.** d_s = m(controller, s) − m(reference, s), with a 95 % Student-t interval mean(d) ± t(0.975, 29)·SD(d)/√30.
- **No hypothesis tests.** No p-values and no multiple-comparison adjustment are applied; the intervals are descriptive.

### C.4 Controllers (verified against `protocol.json` → `controllers` and `app/evaluation/controllers.py`)

| Controller | Definition |
|---|---|
| **Fixed-Time** (`fixed_time`) | SUMO's own static programme (30 s green, 5 s yellow, 30 s green, 5 s yellow, offset 0), action KEEP at every decision. It was checked in every episode against the network file; the timing check passed on 30/30 seeds. |
| **Rule-Based** (`rule_based`) | The legacy density rule. At the start of each green it takes the maximum density on the served lanes: < 20 veh/km → 20 s, < 40 veh/km → 35 s, otherwise 55 s. The green is moved toward the target with safe EXTEND/REDUCE steps. The thresholds are the legacy ones and were not tuned. |
| **Actuated-Style** (`actuated_style`) | **A custom, untuned emulation of gap-based actuated control written for this project; it is not SUMO's native actuated controller** (no `type="actuated"` logic, no SUMO detectors). Its "detector" is the set of vehicles within 40 m of the stop line, read from TraCI. Min green 10 s, max green 50 s. It gaps out (SWITCH) when the served group is empty, the other group is not, and the min green has elapsed. It extends by 5 s when the green is about to end and served vehicles are present. |
| **obs-v2 DQN** (`dqn`) | Greedy masked policy of the training run's validation-selected checkpoint (`best.pt` = `ckpt_best_ep0240.pt`, SHA-256 `e7bc8722…`), schema `fyp-obs-v2`, 15 features, D = 40 m. |

All four controllers act through the same safe action layer.

---

## D. Training and checkpoint selection

### D.1 Training runs (verified from `training_runs/*/config.json`)

| | v1 (`fyp_s0`) | obs-v2 (`fyp_s0_obs_v2`) |
|---|---|---|
| Command | `train_dqn.py --run-id fyp_s0 --seed 0` | `train_dqn.py --run-id fyp_s0_obs_v2 --seed 0 --obs-version fyp-obs-v2 --detector-range-m 40` |
| Observation | `fyp-obs-v1`, 11 features | `fyp-obs-v2`, 15 features, D = 40 m |
| Episodes | 400 (training horizon 1,800 s) | 400 (training horizon 1,800 s) |
| Seed / training seeds | 0 / 2,000,001–2,000,400 | 0 / 2,000,001–2,000,400 |
| Hidden size | 64 (two layers) | 64 (two layers) |
| γ / learning rate | 0.95 / 5·10⁻⁴ | 0.95 / 5·10⁻⁴ |
| Batch / replay buffer / warm-up transitions | 64 / 50,000 / 1,000 | 64 / 50,000 / 1,000 |
| Updates per decision / target update | 4 / every 500 gradient steps | 4 / every 500 gradient steps |
| ε schedule | 1.0 → 0.05 (decay over half the planned decisions) | same |
| Reward scale / grad clip | 0.01 / 1.0 | 0.01 / 1.0 |
| Proxy validation | every 20 episodes, 5 seeds, metric `mean_wait_s` | same |
| Proxy-best checkpoint (`best.json`) | episode 400 (score 1.0277) | episode 240 (score 0.8049) |
| Wall time | 3,692.6 s | 4,797.5 s |
| Software | Python 3.13.16, NumPy 2.5.4, PyTorch 2.14.1, SUMO 1.18.0 | same |

The two runs differ only in the observation schema. Both training configs record `git_dirty: true`: they were trained from the uncommitted FYP working tree at `d8b9701`. Each config stores SHA-256 hashes of every source file that determines the run.

### D.2 Why approach-presence features were added

Earlier diagnostics with the v1 model (validation seeds only, not final results) indicated that it tended to end greens early. Two diagnostics are recorded:
- **`diagnostic_runs/mingreen_ep400_r2`.** Forcing a longer minimum green at inference made waiting worse. A 15 s minimum green gave **+2.07 s** (95 % CI [0.11, 4.03]) relative to the default 10 s, on 10 seeds.
- **`diagnostic_runs/decision_logging_ep400`.** Decision-level logs were compared with the Actuated-Style controller.

The hypothesis drawn from these diagnostics was that the v1 observation does not say whether vehicles are *about to reach* the stop line on the green approach. Its counts are lane-wide and do not separate moving from stopped vehicles near the stop line. The four obs-v2 features add exactly this information.

The input size changes from 11 to 15, so a v1 checkpoint cannot be reused. obs-v2 was therefore trained as a separate run with otherwise identical settings. The loaders refuse any cross-schema loading or reshaping.

### D.3 Two-stage checkpoint selection (`selection_runs/sel_fyp_s0_obs_v2/decision.json`)

1. **Stage A (screening).** All 20 periodic checkpoints (episodes 20–400) ran on 10 fresh validation seeds, 3,000,401–3,000,410.
   - A checkpoint is *eligible* only if no drain was exhausted, no trip was unfinished or not inserted, and completion was ≥ 0.999. All 20 were eligible.
   - The 3 eligible challengers with the lowest mean waiting time advanced with the incumbent: episodes 360 (10.14 s), 320 (10.27 s) and 400 (10.30 s), plus incumbent 240 (10.47 s).
2. **Stage B (confirmation).** The finalists ran on 20 independent seeds, 3,000,501–3,000,520.
   - **Pre-specified rule:** replace the incumbent only if an eligible challenger's Bonferroni-adjusted two-sided t-interval (confidence 1 − 0.05/3 = 98.33 %, t = 2.625) of mean(challenger − incumbent) waiting time lies entirely below 0.

| Challenger | Stage-B mean wait (s) | Mean diff vs ep 240 (s) | Adjusted interval | Supported improvement |
|---|---:|---:|---|---|
| 320 | 11.44 | −0.18 | [−0.48, 0.11] | no |
| 360 | 11.48 | −0.14 | [−0.52, 0.25] | no |
| 400 | 11.31 | −0.31 | [−0.95, 0.34] | no |

The incumbent's Stage-B mean was 11.62 s.

**Result:** episode 240 was kept (`replaced: false`). The challengers' point estimates were slightly lower, but every adjusted interval included 0, so the pre-specified rule did not permit replacement. This is a conservative rule against selection noise. It does **not** show that episode 240 is the best checkpoint of the run, and no claim of optimality is made.

**Checkpoint files.**
- `decision.json` records the selected *periodic* file `ckpt_ep0240.pt` (SHA-256 `7a30427d…`).
- The final-evaluation entrypoint, by its established rule, loads the run's validation-selected `best.pt` = `ckpt_best_ep0240.pt` (`e7bc8722…`).
- The two files differ in hash but have **identical policy weights** (verified before the final run). The same episode-240 model was therefore evaluated.

---

## E. Head-to-head comparison: v1 vs obs-v2 (`evaluation_runs/h2h_v1ep400_vs_v2ep240_s0/`)

**Design.**
- **Models:** v1 `fyp_s0/ckpt_ep0400.pt` (SHA-256 `8727962b…`) against obs-v2 `fyp_s0_obs_v2/ckpt_ep0240.pt` (`7a30427d…`), each in an environment of its own schema.
- **Seeds:** 30 matched validation seeds, 3,000,601–3,000,630 (60 episodes).
- **Protocol:** the same as the final evaluation.
- **Execution:** completed with no error in 1,416.8 s.

| Primary metric (v2 − v1) | Value |
|---|---|
| Mean difference | -4.388 s |
| SD of differences | 1.377 s |
| Median difference | -4.285 s |
| 95 % Student-t CI | [-4.902, -3.874] s |
| v2 better / tie / worse | 30 / 0 / 0 seeds |
| Per-seed range | -7.19 to -0.62 s (every seed favours v2) |

| Metric | v1 ep 400 (mean ± SD) | obs-v2 ep 240 (mean ± SD) | v2 − v1 mean | 95 % CI |
|---|---:|---:|---:|---|
| Waiting time per vehicle, all trips (s) (primary) | 15.86 ± 3.33 | 11.47 ± 3.53 | -4.388 | [-4.902, -3.874] |
| Waiting time per vehicle, completed trips (s) | 15.86 ± 3.33 | 11.47 ± 3.53 | -4.388 | [-4.902, -3.874] |
| Travel time, completed trips (s) | 143.1 ± 5.5 | 137.8 ± 6.4 | -5.39 | [-6.31, -4.47] |
| Mean queue per lane (veh) | 0.74 ± 0.20 | 0.55 ± 0.19 | -0.190 | [-0.216, -0.165] |
| Mean occupancy (%) | 6.30 ± 0.91 | 5.97 ± 0.88 | -0.331 | [-0.387, -0.276] |
| Mean vehicles per lane | 4.65 ± 0.65 | 4.40 ± 0.63 | -0.246 | [-0.289, -0.202] |
| Throughput (veh/h) | 2485 ± 249 | 2490 ± 249 | 4.9 | [-0.1, 9.8] |
| Maximum queue on any lane (veh) | 10.6 ± 3.2 | 10.3 ± 6.6 | -0.23 | [-1.63, 1.17] |
| Congested lane-steps (%) | 0.75 ± 1.91 | 0.53 ± 1.59 | -0.226 | [-0.429, -0.022] |

Completion was 1.0 for both models, with 0 unfinished trips, 0 teleports and no drain exhaustion. Mean drain used was 166.7 s (v1) and 160.2 s (v2).

**Interpretation.** On these 30 seeds the obs-v2 checkpoint waited consistently less than the v1 checkpoint. This supports a statement about **these two specific checkpoints under this protocol**. It is not a statement about the two observation schemas in general, which would need several training seeds.

---

## F. Final evaluation results (`evaluation_runs/fyp_final_s0_obs_v2/`)

Mean ± sample SD over the 30 matched seeds 4,000,031–4,000,060 (from `summary.json`):

| Metric | Fixed-Time | Rule-Based | Actuated-Style | obs-v2 DQN |
|---|---:|---:|---:|---:|
| Waiting time per vehicle, all trips (s) — **primary** | 28.86 ± 6.91 | 24.82 ± 4.19 | 13.61 ± 2.95 | 11.95 ± 4.45 |
| Waiting time per vehicle, completed trips (s) | 28.85 ± 6.87 | 24.82 ± 4.19 | 13.61 ± 2.95 | 11.95 ± 4.45 |
| Travel time, completed trips (s) | 160.7 ± 11.1 | 153.3 ± 6.4 | 140.5 ± 4.7 | 139.2 ± 8.5 |
| Mean queue per lane (veh) | 1.29 ± 0.38 | 1.14 ± 0.31 | 0.65 ± 0.21 | 0.58 ± 0.28 |
| Mean occupancy (%) | 7.20 ± 1.30 | 6.81 ± 1.18 | 6.07 ± 0.99 | 6.05 ± 1.23 |
| Mean vehicles per lane | 5.33 ± 0.89 | 5.05 ± 0.83 | 4.50 ± 0.70 | 4.48 ± 0.86 |
| Throughput (veh/h) | 2463 ± 262 | 2479 ± 285 | 2489 ± 284 | 2485 ± 282 |
| Maximum queue on any lane (veh) | 15.4 ± 5.4 | 17.1 ± 5.6 | 13.0 ± 3.4 | 11.2 ± 6.1 |
| Congested lane-steps (%) | 1.24 ± 2.24 | 2.00 ± 2.75 | 1.08 ± 1.91 | 1.19 ± 3.03 |

The DQN's waiting-time SD (4.45 s) is larger than the Actuated-Style SD (2.95 s); its per-seed performance is less uniform. Its throughput is within a few veh/h of the other adaptive controllers.

---

## G. Paired statistical comparisons

Unit: the seed (n = 30 pairs). Difference = obs-v2 DQN − reference controller. **Negative values favour the DQN** for waiting, travel time, queue, occupancy, maximum queue and congestion; **positive values favour it for throughput**. The intervals are 95 % Student-t (t = 2.045), **unadjusted** for multiple comparisons. The comparisons against Fixed-Time are those stored in `summary.json`. Those against Rule-Based and Actuated-Style were computed with the same function (`runner.paired_difference`) from `episodes.csv`.

| obs-v2 DQN − … | Metric | Mean diff | SD diff | Median | 95 % CI | DQN better / tie / worse (seeds) |
|---|---|---:|---:|---:|---|---|
| Fixed-Time | Waiting time per vehicle, all trips (s) (primary) | -16.911 | 4.501 | -15.669 | [-18.591, -15.230] | 30 / 0 / 0 |
| Fixed-Time | Travel time, completed trips (s) | -21.51 | 6.62 | -19.89 | [-23.98, -19.04] | 30 / 0 / 0 |
| Fixed-Time | Mean queue per lane (veh) | -0.715 | 0.203 | -0.665 | [-0.791, -0.639] | 30 / 0 / 0 |
| Fixed-Time | Mean occupancy (%) | -1.154 | 0.431 | -1.067 | [-1.315, -0.993] | 30 / 0 / 0 |
| Fixed-Time | Throughput (veh/h) | 21.9 | 32.6 | 13.0 | [9.8, 34.1] | 26 / 1 / 3 |
| Fixed-Time | Maximum queue on any lane (veh) | -4.20 | 4.48 | -5.00 | [-5.87, -2.53] | 26 / 2 / 2 |
| Fixed-Time | Congested lane-steps (%) | -0.048 | 1.745 | 0.000 | [-0.700, 0.603] | 14 / 6 / 10 |
| Rule-Based | Waiting time per vehicle, all trips (s) (primary) | -12.869 | 1.957 | -12.798 | [-13.600, -12.139] | 30 / 0 / 0 |
| Rule-Based | Travel time, completed trips (s) | -14.10 | 3.80 | -14.49 | [-15.52, -12.68] | 30 / 0 / 0 |
| Rule-Based | Mean queue per lane (veh) | -0.557 | 0.110 | -0.570 | [-0.598, -0.516] | 30 / 0 / 0 |
| Rule-Based | Mean occupancy (%) | -0.764 | 0.234 | -0.809 | [-0.852, -0.677] | 29 / 0 / 1 |
| Rule-Based | Throughput (veh/h) | 5.7 | 16.1 | 3.0 | [-0.3, 11.7] | 18 / 0 / 12 |
| Rule-Based | Maximum queue on any lane (veh) | -5.97 | 2.74 | -5.50 | [-6.99, -4.95] | 29 / 0 / 1 |
| Rule-Based | Congested lane-steps (%) | -0.806 | 0.949 | -0.688 | [-1.160, -0.452] | 27 / 2 / 1 |
| Actuated-Style | Waiting time per vehicle, all trips (s) (primary) | -1.663 | 2.270 | -2.204 | [-2.511, -0.815] | 28 / 0 / 2 |
| Actuated-Style | Travel time, completed trips (s) | -1.32 | 4.90 | -2.58 | [-3.15, 0.51] | 28 / 0 / 2 |
| Actuated-Style | Mean queue per lane (veh) | -0.070 | 0.114 | -0.093 | [-0.113, -0.028] | 28 / 0 / 2 |
| Actuated-Style | Mean occupancy (%) | -0.025 | 0.359 | -0.114 | [-0.159, 0.109] | 27 / 0 / 3 |
| Actuated-Style | Throughput (veh/h) | -3.7 | 12.3 | -6.0 | [-8.3, 0.9] | 12 / 1 / 17 |
| Actuated-Style | Maximum queue on any lane (veh) | -1.87 | 4.10 | -2.50 | [-3.40, -0.34] | 23 / 3 / 4 |
| Actuated-Style | Congested lane-steps (%) | 0.114 | 1.280 | -0.151 | [-0.364, 0.592] | 23 / 3 / 4 |

The baselines relative to Fixed-Time (waiting time, from `summary.json`) were:

| Controller − Fixed-Time | Mean diff (s) | 95 % CI (s) |
|---|---:|---|
| Rule-Based | -4.04 | [-6.00, -2.08] |
| Actuated-Style | -15.25 | [-17.26, -13.23] |
| obs-v2 DQN | -16.91 | [-18.59, -15.23] |

**Reading the table.**
- **Fixed-Time and Rule-Based.** The DQN's waiting-time, travel-time and queue intervals are far from 0, and it was better on every seed for each.
- **Actuated-Style.** The waiting-time and mean-queue intervals exclude 0, but the effect is small: −1.66 s, about 12 % of the actuated mean. The travel-time, occupancy, congestion and throughput intervals include 0, so no difference is shown on those metrics.

---

## H. Completion, safety and integrity

| Controller | Episodes | Completion rate (mean, min) | Unfinished trips (total) | Not inserted (total) | Delayed insertions (mean) | Drain used s (mean / max) | Drain exhausted | Vehicles left (total) | Teleports (total) |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|
| Fixed-Time | 30 | 0.9997, 0.9914 | 14 | 0 | 6.23 | 221.0 / 600 | 1 | 14 | 0 |
| Rule-Based | 30 | 1.0000, 1.0000 | 0 | 0 | 1.50 | 179.8 / 215 | 0 | 0 | 0 |
| Actuated-Style | 30 | 1.0000, 1.0000 | 0 | 0 | 1.50 | 151.5 / 180 | 0 | 0 | 0 |
| obs-v2 DQN | 30 | 1.0000, 1.0000 | 0 | 0 | 1.50 | 156.7 / 240 | 0 | 0 | 0 |

- **Episodes.** 120 of 120 planned episodes completed: 30 seeds × 4 controllers, with no failed episode.
- **Safety.** No illegal action, coerced action or safety violation occurred; the runner aborts on any of these, and none was raised. There were 0 teleports in every episode.
- **Fixed-Time timing check.** Passed on all 30 seeds: the programme ran exactly 30/5/30/5 s.
- **Fixed-Time drain exhaustion, seed 4,000,033.**
  - The 600 s drain was used up with **14 trips unfinished** (completion 0.9914) and 14 vehicles left in the network. 83 cohort vehicles were delayed insertions.
  - That episode's waiting time was 45.91 s, and the mean age of its unfinished trips was 211.2 s, a lower bound.
  - Under the protocol the episode is **retained**, not excluded.
  - Because unfinished trips contribute only the waiting accumulated so far, Fixed-Time's waiting time on this seed is, if anything, an *under*-estimate. Its completed-trip travel time there is optimistic.
  - This affects only Fixed-Time. The three adaptive controllers completed every trip on every seed.
- **Delayed insertions.** Fixed-Time also had more of them (mean 6.23 against 1.50); `departed_after_window` makes these visible.
- **DQN action mix** (all junction-decisions over 30 episodes, 4 junctions × 13,540 decisions): KEEP 37,151, SWITCH 13,388, EXTEND 2,468, REDUCE 1,153.
- **Ledger.** `evaluation_runs/ledger.jsonl` received one new entry through its normal mechanism: `fyp_final_s0_obs_v2`, mode `final`, checkpoint `e7bc8722…`, seeds [4,000,031, 4,000,060], `repeat: false`. The earlier `fyp_final_s0` entry is unchanged.
- **Preserved artifacts.** All earlier evaluation, training, selection and diagnostic artifacts and the route, network and config files were verified byte-identical after the run.

### H.1 Context: the earlier v1 final evaluation (`evaluation_runs/fyp_final_s0/`)

The v1 model (`best.pt`, episode 400) was evaluated earlier on the different seeds 4,000,001–4,000,030.

| Controller | Waiting time (s) |
|---|---:|
| Fixed-Time | 31.20 ± 8.81 |
| Rule-Based | 27.18 ± 7.82 |
| Actuated-Style | 15.48 ± 5.54 |
| v1 DQN | 18.78 ± 7.40 |

In that run the v1 DQN improved on Fixed-Time by −12.42 s [−14.02, −10.82] but waited longer than Actuated-Style. Because the seeds differ, these numbers must **not** be subtracted from the obs-v2 results. The controlled v1-against-v2 comparison is the head-to-head in §E.

---

## I. Discussion and interpretation

**Measured outcomes.**
1. On matched validation seeds, the obs-v2 checkpoint reduced trip waiting time relative to the v1 checkpoint by 4.39 s (about 28 %), on every seed.
2. In the final evaluation, obs-v2 DQN had the lowest mean waiting time of the four controllers. It was clearly better than Fixed-Time and Rule-Based, and better than Actuated-Style by a small but consistent margin (28/30 seeds).
3. Throughput hardly differed among the adaptive controllers.

**Why lower waiting need not mean higher throughput.**
- Throughput counts arrivals in the measured window. In this demand family every adaptive controller completed all trips, so network demand, not signal capacity, bounds arrivals.
- Waiting time measures how *long* vehicles stand still, not how *many* arrive. A controller can serve the same vehicles with less stopping, which lowers waiting and travel time without raising throughput.
- Fixed-Time's higher throughput deficit (−21.9 veh/h compared with the DQN) is consistent with its backlog, including the drain-exhausted seed.

**Hypotheses (not established by these experiments).**
- obs-v2's gain over v1 is consistent with the diagnostic finding that v1 lacked information about vehicles approaching the green. The presence features supply that information.
- No ablation or causal analysis isolates this mechanism. With one training seed per schema, part of the difference could be run-to-run training variance.
- The DQN's higher SD and its 2 losing seeds against Actuated-Style suggest that its advantage is not uniform across traffic conditions. The reasons were not analysed.

**Limitations of the current design (from the code).**
- The reward is the unchanged **legacy** per-junction formula, a lane/queue/throughput proxy. It is not the evaluation's trip waiting metric, and model selection inside training also used a lane proxy (`mean_wait_s`). The trip-based selection stage partly compensates for this.
- The policy is shared across junctions and sees only local per-junction state, with no coordination features.
- The presence features use a fixed 40 m range and a 7.5 m spacing normaliser. Values can clip slightly with short vehicles.

---

## J. Limitations and future work

**Limitations.**
1. One training seed (seed 0) per DQN run; training variance is unknown.
2. One four-junction network and one randomised demand family (8 routes, with sparse emergency-vehicle flows pooled into all metrics).
3. The detector range of 40 m was not tuned or sensitivity-tested.
4. Checkpoint selection used validation seeds from the same distribution as the final seeds, and covered 20 correlated checkpoints of one run.
5. Confidence intervals are descriptive and **not corrected for multiple comparisons** (several controllers × several metrics). The Bonferroni adjustment applies only inside the selection rule.
6. Rule-Based uses untuned legacy thresholds, and Actuated-Style is an untuned project-specific emulation, **not** SUMO's native actuated control or a tuned industrial controller.
7. Delayed insertions are not counted as travel time (SUMO convention). They are reported separately.
8. All results are from simulation; they do not establish real-world effectiveness, detector robustness or safety in deployment.
9. The FastAPI/React application was not part of this evaluation.

**Future work (not implemented).**
- Multiple training seeds for both schemas, so that the schema effect and training variance can be estimated.
- Additional demand patterns (peaks, asymmetric and incident demand) and further networks.
- Detector-range sensitivity analysis, and an ablation of the four presence features.
- A comparison with SUMO's native actuated control and with tuned baselines.
- A reward aligned with the trip-waiting objective.
- Pre-registered confirmatory testing with multiplicity control.
- Validation with realistic sensor noise and, eventually, real-world data.

---

## K. Conclusion

Under the established protocol (SUMO 1.18.0, 4 junctions, 30 matched final seeds, trip-based waiting time), the IntelliRoads obs-v2 Double DQN controller showed the following:
- **Safety.** It operated within all signal-safety constraints, with no illegal actions, violations, teleports or failed episodes.
- **Completion.** It completed every trip on every seed.
- **Fixed-Time.** It reduced waiting time by 16.9 s per vehicle, with a 95 % CI of [−18.6, −15.2] s.
- **Rule-Based.** It reduced waiting time by 12.9 s, with a 95 % CI of [−13.6, −12.1] s.
- **Actuated-Style.** It had a smaller but consistent advantage of 1.7 s, with a 95 % CI of [−2.5, −0.8] s. There was no demonstrated difference in throughput or travel time against this controller.
- **v1 model.** A separate matched comparison showed the obs-v2 checkpoint outperforming the earlier v1 checkpoint by 4.4 s.

These results demonstrate that, for this network and demand family, a safely constrained learned controller with phase-relative approach-presence features can reduce vehicle waiting relative to the implemented baselines.

They do **not** establish:
- robustness across training seeds, networks or demand patterns;
- superiority over native or tuned actuated control;
- any real-world benefit.

---

## Appendix A — Sources and verification

| Artifact | SHA-256 (prefix) |
|---|---|
| `evaluation_runs/fyp_final_s0_obs_v2/summary.json` | `0800f24f4bfe` |
| `evaluation_runs/fyp_final_s0_obs_v2/episodes.csv` | `89add50cb034` |
| `evaluation_runs/fyp_final_s0_obs_v2/protocol.json` | `ad87e7eb2c4b` |
| `evaluation_runs/h2h_v1ep400_vs_v2ep240_s0/summary.json` | `caff6a450ac1` |
| `evaluation_runs/h2h_v1ep400_vs_v2ep240_s0/protocol.json` | `9dfdc027a42b` |
| `selection_runs/sel_fyp_s0_obs_v2/decision.json` | `752622976319` |
| `selection_runs/sel_fyp_s0_obs_v2/plan.json` | `2ba6441c287e` |
| `training_runs/fyp_s0/config.json` | `78593bc7fe46` |
| `training_runs/fyp_s0_obs_v2/config.json` | `f2e989ba29e6` |
| `training_runs/fyp_s0_obs_v2/best.pt` (= `ckpt_best_ep0240.pt`) | `e7bc8722fe62` |
| `training_runs/fyp_s0_obs_v2/ckpt_ep0240.pt` | `7a30427d4e6e` |
| `training_runs/fyp_s0/ckpt_ep0400.pt` | `8727962b06d1` |
| `evaluation_runs/fyp_final_s0/summary.json` | `b1c64173ef05` |

## Appendix B — Notes on discrepancies found while preparing this report

1. **Rounding.** The cross-check value for obs-v2 DQN congested lane-steps SD was given as 3.04. The stored value rounds to **3.03** (3.0349…), so this report uses 3.03. All other cross-check values match the stored artifacts.
2. **Stale wording in `EVALUATION_PROTOCOL.md` §4 and §9.** The text read "format `fyp-stage3-v1`, 11 features", "No checkpoint suitable for this exists yet" and "Stage 5 tooling; not yet run". It also listed 4,000,001–4,000,030 as the final seeds. These describe the state before the v2 work. The code accepts `fyp-ckpt-v2` checkpoints (§10 of the same document), selection has been run, and the obs-v2 final evaluation used the reserved fresh seeds 4,000,031–4,000,060, as §9 itself prescribes for a later checkpoint. This was corrected afterwards in `EVALUATION_PROTOCOL.md` revision 3 (status, §4 DQN description, §5 seed table, §8, §9 heading, new §11 run record); the episode structure, metrics, statistics and baseline definitions were not changed.
3. **Checkpoint file naming.** The selection records `ckpt_ep0240.pt` (`7a30427d…`), while the final evaluation's ledger records `best.pt` (`e7bc8722…`). These are different files with identical policy weights (§D.3). Both hashes should be cited when describing the evaluated model.
