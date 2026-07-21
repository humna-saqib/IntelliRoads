"""
IntelliRoads – Modular Deep Q-Network (DQN) Agent.

Contains:
- Neural Network Architecture (QNetwork) using PyTorch MLP
- Replay Memory (ReplayMemory) for experience replay storage
- Epsilon-Greedy Action Selection
- Experience Replay Training Step with Bellman Q-learning update
- Target Network Support (policy_net & target_net synchronization)
- Checkpoint Save / Load utilities
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random
from pathlib import Path
from typing import List, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Architecture Dimensions
STATE_SIZE: int = 5    # [vehicle_count, queue_length, avg_waiting_time, lane_occupancy, current_phase]
ACTION_SIZE: int = 4   # [0: KEEP, 1: SWITCH, 2: EXTEND, 3: REDUCE]
HIDDEN_SIZE: int = 64

# Feature normalization bounds [min, max] for min-max scaling to [0, 1]
_FEATURE_MIN = [0.0, 0.0, 0.0, 0.0, 0.0]
_FEATURE_MAX = [50.0, 30.0, 120.0, 100.0, 90.0]

from app.core.dqn_config import load_dqn_config

_config_defaults = load_dqn_config()

# Default Hyperparameters (dynamically loaded from config)
GAMMA: float = _config_defaults.gamma
LEARNING_RATE: float = _config_defaults.learning_rate
HIDDEN_SIZE: int = _config_defaults.hidden_size
DEFAULT_MODEL_PATH: Path = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "dqn_agent.pt"



def normalize_state(state: List[float]) -> List[float]:
    """Min-max normalisation of raw 5-feature state vector to [0, 1]."""
    return [
        (v - lo) / (hi - lo) if hi > lo else 0.0
        for v, lo, hi in zip(state, _FEATURE_MIN, _FEATURE_MAX)
    ]


@dataclass
class Experience:
    """Single transition tuple (s, a, r, s', done)."""
    state: List[float]
    action: int
    reward: float
    next_state: List[float]
    done: bool


class ReplayMemory:
    """
    Experience Replay Memory ring buffer using collections.deque.
    Stores past experience tuples and samples random minibatches for training.
    """

    def __init__(self, capacity: int = 10000) -> None:
        self.capacity = capacity
        self.memory: deque[Experience] = deque(maxlen=capacity)

    def push(
        self,
        state: List[float],
        action: int,
        reward: float,
        next_state: List[float],
        done: bool,
    ) -> None:
        """Store experience transition in memory buffer."""
        self.memory.append(Experience(state, action, reward, next_state, done))

    def sample(self, batch_size: int) -> List[Experience]:
        """Randomly sample a minibatch of experiences from memory."""
        return random.sample(self.memory, min(batch_size, len(self.memory)))

    def __len__(self) -> int:
        return len(self.memory)


class QNetwork(nn.Module):
    """
    PyTorch Neural Network for Deep Q-Learning (MLP).
    Input: State space vector (5 features)
    Output: Q-value vector for each discrete action (4 actions)
    """

    def __init__(
        self,
        state_size: int = STATE_SIZE,
        action_size: int = ACTION_SIZE,
        hidden_size: int = HIDDEN_SIZE,
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, action_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DQNAgent:
    """
    Deep Q-Network (DQN) Agent for Traffic Signal Control.

    Features:
    ---------
    - Policy Network (policy_net) & Target Network (target_net)
    - Replay Memory (ReplayMemory)
    - Epsilon-Greedy Action Selection (select_action)
    - Experience Replay Training Step (train_step)
    - Target Network Weight Synchronization (update_target_network)
    """

    def __init__(
        self,
        state_size: int = STATE_SIZE,
        action_size: int = ACTION_SIZE,
        device: Optional[str] = None,
        memory_capacity: Optional[int] = None,
        gamma: Optional[float] = None,
        learning_rate: Optional[float] = None,
        hidden_size: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        self.state_size = state_size
        self.action_size = action_size
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

        config = load_dqn_config()
        self.gamma = gamma if gamma is not None else config.gamma
        self.learning_rate = learning_rate if learning_rate is not None else config.learning_rate
        self.hidden_size = hidden_size if hidden_size is not None else config.hidden_size
        self.batch_size = batch_size if batch_size is not None else config.batch_size_online
        capacity = memory_capacity if memory_capacity is not None else config.memory_capacity

        # Initialize Policy Network & Target Network
        self.policy_net = QNetwork(state_size, action_size, hidden_size=self.hidden_size).to(self.device)
        self.target_net = QNetwork(state_size, action_size, hidden_size=self.hidden_size).to(self.device)
        self.update_target_network()
        self.target_net.eval()

        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=self.learning_rate)
        self.loss_fn = nn.SmoothL1Loss()
        self.memory = ReplayMemory(capacity=capacity)
        self.train_step_count: int = 0

        logger.info(
            f"DQNAgent initialised on device={self.device}, "
            f"state_size={state_size}, action_size={action_size}, "
            f"hidden_size={self.hidden_size}, learning_rate={self.learning_rate}, "
            f"gamma={self.gamma}, batch_size={self.batch_size}, memory_capacity={capacity}"
        )

    # ------------------------------------------------------------------
    # Core API: select_action, store_transition, train_step, update_target
    # ------------------------------------------------------------------

    def select_action(self, state: List[float], epsilon: float = 0.1) -> int:
        """
        Select action using Epsilon-Greedy Policy.

        Parameters
        ----------
        state : List[float]
            5-element traffic state vector.
        epsilon : float
            Exploration probability (0.0 <= epsilon <= 1.0).

        Returns
        -------
        int
            Selected discrete action index (0: KEEP, 1: SWITCH, 2: EXTEND, 3: REDUCE).
        """
        if random.random() < epsilon:
            # Random exploration action
            return random.randrange(self.action_size)
        else:
            # Exploitation: Select action with highest predicted Q-value
            with torch.no_grad():
                norm_state = normalize_state(state)
                state_tensor = torch.tensor(
                    [norm_state], dtype=torch.float32, device=self.device
                )
                q_values = self.policy_net(state_tensor)
                action_index = int(torch.argmax(q_values, dim=1).item())
                return action_index

    def store_transition(
        self,
        state: List[float],
        action: int,
        reward: float,
        next_state: List[float],
        done: bool,
    ) -> None:
        """Store (s, a, r, s', done) experience tuple in replay memory."""
        self.memory.push(state, action, reward, next_state, done)

    def train_step(self, batch_size: Optional[int] = None) -> Optional[Tuple[float, float]]:
        """
        Perform one gradient step of Experience Replay training on a sampled minibatch.

        Parameters
        ----------
        batch_size : int, optional
            Number of experiences to sample from replay memory. If None, uses configured batch_size.

        Returns
        -------
        Optional[Tuple[float, float]]
            (loss, mean_q_value) if trained, or None if buffer has insufficient data.
        """
        if batch_size is None:
            batch_size = self.batch_size

        if len(self.memory) < batch_size:
            return None

        batch = self.memory.sample(batch_size)

        states = torch.tensor(
            [normalize_state(exp.state) for exp in batch],
            dtype=torch.float32,
            device=self.device,
        )
        actions = torch.tensor(
            [exp.action for exp in batch],
            dtype=torch.int64,
            device=self.device,
        ).unsqueeze(1)
        rewards = torch.tensor(
            [exp.reward for exp in batch],
            dtype=torch.float32,
            device=self.device,
        )
        next_states = torch.tensor(
            [normalize_state(exp.next_state) for exp in batch],
            dtype=torch.float32,
            device=self.device,
        )
        dones = torch.tensor(
            [float(exp.done) for exp in batch],
            dtype=torch.float32,
            device=self.device,
        )

        # Compute Q(s, a) from policy network
        current_q = self.policy_net(states).gather(1, actions).squeeze(1)

        # Compute Target Q = r + gamma * max_a' Q_target(s', a') * (1 - done)
        with torch.no_grad():
            next_q_max = self.target_net(next_states).max(dim=1).values
            target_q = rewards + self.gamma * next_q_max * (1.0 - dones)

        loss = self.loss_fn(current_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.train_step_count += 1

        return float(loss.item()), float(current_q.detach().mean().item())


    def update_target_network(self) -> None:
        """Synchronize weights from policy_net to target_net."""
        self.target_net.load_state_dict(self.policy_net.state_dict())
        logger.debug("Target network synced from policy network.")

    # ------------------------------------------------------------------
    # Model Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path = DEFAULT_MODEL_PATH) -> None:
        """Save network weights and training state to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "policy_net": self.policy_net.state_dict(),
                "target_net": self.target_net.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "train_step_count": self.train_step_count,
            },
            str(path),
        )
        logger.info(f"DQNAgent checkpoint saved to {path}")

    def load(self, path: Path = DEFAULT_MODEL_PATH) -> None:
        """Load network weights and training state from disk."""
        if not path.exists():
            logger.warning(f"Checkpoint {path} does not exist — skipping load.")
            return
        checkpoint = torch.load(str(path), map_location=self.device)
        self.policy_net.load_state_dict(checkpoint["policy_net"])
        self.target_net.load_state_dict(checkpoint["target_net"])
        self.optimizer.load_state_dict(checkpoint["optimizer"])
        self.train_step_count = checkpoint.get("train_step_count", 0)
        logger.info(f"DQNAgent checkpoint loaded from {path}")
