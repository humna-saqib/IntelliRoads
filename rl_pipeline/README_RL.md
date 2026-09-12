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

Trained for 1,000 episodes on real SUMO simulations. The episode-950 checkpoint (`dqn_episode_0950.pt`) was selected as final after convergence.

| Hyperparameter | Value |
| :--- | :---: |
| Episodes | 1,000 |
| Steps/episode | 25 |
| Discount factor (γ) | 0.95 |
| Learning rate (α) | 0.0005 |
| Replay capacity | 10,000 |
| Batch size | 32 |
| ε start / end | 1.0 / 0.08 |
| ε decay | 250 epochs (linear) |
| Target network sync | every 5 epochs |

## 3. Evaluation

The final DQN agent was benchmarked against two baselines over 30 episodes (200 steps each, 6,000 steps/controller) on real SUMO traffic:

- **Fixed-Time** — static pre-timed green intervals
- **Rule-Based** — dynamic thresholds on queue count
- **DQN** — trained agent, greedy policy (ε = 0)

| Metric | Fixed-Time | Rule-Based | DQN | vs. best baseline |
| :--- | :---: | :---: | :---: | :---: |
| Avg waiting time (s) | 4.951 | 6.776 | **3.366** | −32.0% |
| Avg travel time (s) | 16.437 | 18.809 | **14.376** | −12.5% |
| Avg queue length (veh) | 12.514 | 12.961 | **10.777** | −13.9% |
| Throughput (veh) | 556 | 557 | 524 | small trade-off |
| Episode reward | −3845.78 | −4394.68 | **+1701.36** | positive vs. negative |

## 4. Reproducing results

Run from the project root with the backend virtual environment active:

```bash
# 1. Evaluate all three controllers
python backend/evaluate_controllers.py --episodes 30 --steps 200

# 2. Compute summary statistics
python backend/process_eval_results.py

# 3. Generate comparison charts
python backend/generate_comparison_graphs.py
```

(Windows: use `venv\Scripts\python.exe` in place of `python`.)

## 5. Directory structure

```
rl_pipeline/
├── final_dqn_model/
│   └── dqn_episode_0950.pt        # Final trained weights
├── training_results/
│   └── episode_log.csv            # Per-episode training log (reward, loss, Q-values)
├── evaluation_results/
│   ├── eval_raw.csv               # Per-episode benchmark data (30 ep × 3 controllers)
│   ├── eval_summary.csv           # Mean/std summary
│   └── eval_summary.json
├── training_graphs/
│   └── reward_curve.png
└── comparison_graphs/
    ├── waiting_time_comparison.png
    ├── travel_time_comparison.png
    ├── queue_length_comparison.png
    ├── throughput_comparison.png
    ├── reward_comparison.png
    └── overall_benchmark_comparison.png
```
