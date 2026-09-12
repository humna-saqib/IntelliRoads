# IntelliRoads – Deep Q-Network (DQN) Traffic Signal Control

This directory contains the final Reinforcement Learning (RL) pipeline deliverables for **IntelliRoads**, an intelligent adaptive traffic signal control system built on PyTorch and the SUMO (Simulation of Urban MObility) microscopic traffic simulator.

---

## 1. Deep Q-Network (DQN) Architecture

### Network Topology
The policy network (`QNetwork`) is implemented as a PyTorch Multi-Layer Perceptron (MLP) designed for multi-junction adaptive signal control.

```
State Input (5)  -->  Linear(5 -> 64) + ReLU  -->  Linear(64 -> 64) + ReLU  -->  Linear(64 -> 4)  -->  Action Q-Values (4)
```

- **Input Dimension**: 5 continuous state features (min-max normalized to `[0, 1]`).
- **Hidden Layers**: 2 fully connected hidden layers with 64 units each and ReLU activations.
- **Output Dimension**: 4 discrete Q-values corresponding to traffic signal control actions.
- **Optimizer**: Adam (`learning_rate = 0.0005`).
- **Loss Function**: Huber Loss (`nn.SmoothL1Loss`).
- **Stabilization Mechanisms**:
  - **Double DQN**: Decouples action selection (`policy_net`) from target evaluation (`target_net`) to eliminate Q-value overestimation bias.
  - **Gradient Clipping**: Norm clamped at `max_norm = 1.0` to prevent gradient explosion.
  - **Q-Target Clipping**: Clamped target values within `[-100.0, +50.0]` range for training stability.
  - **Replay Memory**: Buffer capacity of 10,000 transitions with crash-resilient disk serialization.

---

### State Space Vector (5 Features)
For each monitored junction, the environment constructs a 5-element state vector:

1. `vehicle_count` ($[0, 50]$): Total count of vehicles on incoming approach lanes.
2. `queue_length` ($[0, 30]$): Total count of halted vehicles (speed $< 2.0\text{ m/s}$).
3. `avg_waiting_time` ($[0, 120\text{s}]$): Average accumulated delay per vehicle across incoming lanes.
4. `lane_occupancy` ($[0, 100\%]$): Average occupancy percentage of incoming lanes.
5. `current_phase` ($[0, 90\text{s}]$): Active green phase index / current elapsed phase duration.

*All raw feature values are min-max scaled into $[0, 1]$ before passing into the network.*

---

### Action Space Vector (4 Discrete Actions)
The agent selects one of 4 discrete actions per step:

| Action ID | Name | Description |
| :---: | :--- | :--- |
| **0** | `KEEP_CURRENT_PHASE` | Maintain the current green light phase without alteration. |
| **1** | `SWITCH_TO_NEXT_PHASE` | Transition traffic light to the next phase sequence. |
| **2** | `EXTEND_GREEN` | Extend current green phase duration by $+5\text{ seconds}$. |
| **3** | `REDUCE_GREEN` | Reduce current green phase duration by $-5\text{ seconds}$ (min bound $10\text{s}$). |

---

### Reward Function & Weights

The scalar reward signal $R$ is formulated to minimize vehicle delay and queue spillback while maximizing throughput and signal stability:

$$R = - (w_{\text{wait}} \cdot \text{avg\_waiting\_time}) - (w_{\text{queue}} \cdot \text{queue\_length}) - (w_{\text{cong}} \cdot \mathbb{I}_{\text{congested}}) + (w_{\text{tp}} \cdot \text{throughput}) - (w_{\text{action}} \cdot \mathbb{I}_{\text{action\_change}}) + R_{\text{shaping}}$$

- **Hyperparameter Weights**:
  - $w_{\text{wait}} = 1.0$: Penalizes driver waiting time.
  - $w_{\text{queue}} = 2.0$: Penalizes queue lengths to avoid spillback into upstream junctions.
  - $w_{\text{cong}} = 4.0$: Penalizes active congestion states ($\text{lane\_occupancy} > 70\%$ or $\text{vehicle\_count} > 15$).
  - $w_{\text{tp}} = 5.0$: Rewards total vehicles successfully passing through the junction.
  - $w_{\text{action}} = 1.5$: Penalizes non-KEEP action changes to prevent signal flickering.
  - $R_{\text{shaping}} = +1.0$: Non-congested bonus to lift baseline without altering optimal policy order.

---

## 2. Training Process & Hyperparameters

The model was trained over 1,000 episodes on real SUMO simulations with the following finalized hyperparameter configuration:

| Hyperparameter | Value | Description |
| :--- | :---: | :--- |
| **Total Episodes** | 1,000 | Model achieved convergence; episode 950 checkpoint (`dqn_episode_0950.pt`) adopted as FINAL. |
| **Steps per Episode** | 25 | Environment step interactions per episode. |
| **Discount Factor ($\gamma$)** | 0.95 | Future reward discount factor. |
| **Learning Rate ($\alpha$)** | 0.0005 | Adam optimizer learning rate. |
| **Replay Capacity** | 10,000 | Experience replay memory buffer size. |
| **Batch Size** | 32 | Minibatch SGD training size. |
| **$\epsilon$-Start / $\epsilon$-End** | 1.0 / 0.08 | Epsilon-Greedy exploration bounds. |
| **$\epsilon$-Decay Duration** | 250 Epochs | Linear decay duration for exploration rate. |
| **Target Network Sync** | Every 5 Epochs | Weight copy interval from `policy_net` to `target_net`. |

---

## 3. Evaluation & Benchmark Results

The final trained DQN agent (`dqn_episode_0950.pt`) was benchmarked against two baseline controllers across **30 evaluation episodes (200 steps each, total 6,000 steps per controller)** on real SUMO traffic:

1. **Fixed-Time Controller**: Pre-timed traffic signal cycles with static green intervals.
2. **Rule-Based Controller**: Dynamic threshold controller switching green phases based on lane queue counts.
3. **Trained DQN Controller**: Deep Q-Network agent selecting optimal actions per step.

### Summary Benchmark Results

| Metric | Fixed-Time | Rule-Based | Trained DQN | DQN Improvement vs Best Baseline |
| :--- | :---: | :---: | :---: | :---: |
| **Avg Waiting Time (s)** | 4.951s | 6.776s | **3.366s** | **32.0% Reduction** |
| **Avg Travel Time (s)** | 16.437s | 18.809s | **14.376s** | **12.5% Reduction** |
| **Avg Queue Length (veh)**| 12.514 | 12.961 | **10.777** | **13.9% Reduction** |
| **Vehicle Throughput** | 556 | 557 | **524** | *Slight trade-off for zero congestion* |
| **Episode Reward** | -3845.78 | -4394.68 | **+1701.36** | **Positive vs Deeply Negative** |

---

## 4. How to Reproduce Training & Evaluation

All commands must be executed from the project root using the dedicated Python virtual environment (`myenv\Scripts\python.exe`):

### 1. Evaluate Controllers
Run 30 evaluation episodes per controller on SUMO:
```cmd
myenv\Scripts\python.exe backend/evaluate_controllers.py --episodes 30 --steps 200
```

### 2. Process Evaluation Summary
Compute summary statistics (`eval_summary.csv` and `eval_summary.json`):
```cmd
myenv\Scripts\python.exe backend/process_eval_results.py
```

### 3. Generate Comparison Bar Charts
Generate high-resolution PNG charts for FYP report:
```cmd
myenv\Scripts\python.exe backend/generate_comparison_graphs.py
```

---

## 5. Deliverables Directory Structure

All deliverables are organized under `Areeba/` at the repository root:

```
Areeba/
├── final_dqn_model/
│   └── dqn_episode_0950.pt        # Adopted final PyTorch DQN model weights
├── training_results/
│   └── episode_log.csv            # 1,000-episode training metric log (reward, loss, Q-values)
├── evaluation_results/
│   ├── eval_raw.csv               # Per-episode raw benchmark evaluation metrics (30 ep x 3 ctrl)
│   ├── eval_summary.csv           # Mean and standard deviation summary metrics
│   └── eval_summary.json          # Formatted JSON evaluation metadata
├── training_graphs/
│   └── reward_curve.png           # Training reward curve graph
├── comparison_graphs/
│   ├── waiting_time_comparison.png
│   ├── travel_time_comparison.png
│   ├── queue_length_comparison.png
│   ├── throughput_comparison.png
│   ├── reward_comparison.png
│   └── overall_benchmark_comparison.png  # FYP report summary dashboard
└── README_RL.md                   # This documentation file
```
