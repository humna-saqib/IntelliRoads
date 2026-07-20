"""
IntelliRoads – DQN Agent for adaptive signal timing (Sprint 2).

Offline-only at this stage: trains purely from historical (state,
action, reward, next_state) transitions already collected in
rl_experiences by RLEnvironment. NOT connected to live signal control —
SignalController and EmergencyPriorityController remain fully in
charge of the running simulation. The goal here is to verify training
mechanics (loss convergence, action selection, reward trend) before
any live-deployment decision is made.

select_action() (epsilon-greedy) exists for future online/live use; the
offline training loop below samples straight from the fixed historical
buffer and does not call it — there's no environment to explore, only
already-collected data to learn from.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import List, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim

from app.services.replay_buffer import INDEX_TO_ACTION, SQLiteReplayBuffer, Transition
from app.utils.logger import get_logger

logger = get_logger(__name__)

STATE_SIZE = 5
ACTION_SIZE = 3
HIDDEN_SIZE = 64

# Approximate observed ranges per state feature — density, queue_length,
# avg_waiting_time, occupancy_percent, current_signal_duration (see
# app.models.rl.STATE_FEATURE_NAMES for the authoritative order). Used
# for fixed min-max normalisation before feeding the network. Not fit
# on data — deliberately simple for this first training pass; revisit
# if real traffic pushes values outside these bounds.
_FEATURE_MIN = [0.0, 0.0, 0.0, 0.0, 0.0]
_FEATURE_MAX = [80.0, 30.0, 120.0, 100.0, 90.0]

# ---------------------------------------------------------------------------
# Hyperparameters – tunable defaults, not final/tuned values.
# ---------------------------------------------------------------------------
GAMMA: float = 0.99
LEARNING_RATE: float = 1e-3
TARGET_UPDATE_FREQUENCY_EPOCHS: int = 10
EPSILON_START: float = 1.0
EPSILON_END: float = 0.05
EPSILON_DECAY_EPOCHS: int = 50

DEFAULT_MODEL_PATH: Path = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "dqn_agent.pt"


def normalize_state(state: List[float]) -> List[float]:
    """Fixed min-max normalisation to roughly [0, 1] per feature."""
    return [
        (v - lo) / (hi - lo) if hi > lo else 0.0
        for v, lo, hi in zip(state, _FEATURE_MIN, _FEATURE_MAX)
    ]


class QNetwork(nn.Module):
    """Small MLP: 5-feature state -> one Q-value per discrete action."""

    def __init__(
        self, state_size: int = STATE_SIZE, action_size: int = ACTION_SIZE, hidden_size: int = HIDDEN_SIZE
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
    DQN agent: policy network + target network, epsilon-greedy action
    selection, and offline experience-replay training from a
    SQLiteReplayBuffer.
    """

    def __init__(self, device: Optional[str] = None) -> None:
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.policy_net = QNetwork().to(self.device)
        self.target_net = QNetwork().to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=LEARNING_RATE)
        self.loss_fn = nn.SmoothL1Loss()
        self.train_step_count = 0
        logger.info(f"DQNAgent initialised on device={self.device}.")

    # ------------------------------------------------------------------
    # Action selection – for future live/online use only (see module
    # docstring). Not used by train_offline().
    # ------------------------------------------------------------------

    def select_action(self, state: List[float], epsilon: float) -> str:
        """Epsilon-greedy action selection. Returns the action name."""
        if random.random() < epsilon:
            action_index = random.randrange(ACTION_SIZE)
        else:
            with torch.no_grad():
                state_tensor = torch.tensor(
                    [normalize_state(state)], dtype=torch.float32, device=self.device
                )
                q_values = self.policy_net(state_tensor)
                action_index = int(torch.argmax(q_values, dim=1).item())
        return INDEX_TO_ACTION[action_index]

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train_step(self, batch: List[Transition]) -> Tuple[float, float]:
        """
        One gradient step on a sampled batch.

        Returns
        -------
        tuple[float, float]
            (loss, mean Q-value for the taken actions) for logging.
        """
        states = torch.tensor(
            [normalize_state(t.state) for t in batch], dtype=torch.float32, device=self.device
        )
        actions = torch.tensor(
            [t.action for t in batch], dtype=torch.int64, device=self.device
        ).unsqueeze(1)
        rewards = torch.tensor([t.reward for t in batch], dtype=torch.float32, device=self.device)
        next_states = torch.tensor(
            [normalize_state(t.next_state) for t in batch], dtype=torch.float32, device=self.device
        )
        dones = torch.tensor([float(t.done) for t in batch], dtype=torch.float32, device=self.device)

        current_q = self.policy_net(states).gather(1, actions).squeeze(1)

        with torch.no_grad():
            next_q_max = self.target_net(next_states).max(dim=1).values
            target_q = rewards + GAMMA * next_q_max * (1.0 - dones)

        loss = self.loss_fn(current_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.train_step_count += 1

        return float(loss.item()), float(current_q.detach().mean().item())

    def update_target_network(self) -> None:
        self.target_net.load_state_dict(self.policy_net.state_dict())
        logger.debug("Target network synced from policy network.")

    def train_offline(
        self,
        buffer: SQLiteReplayBuffer,
        num_epochs: int = 50,
        batch_size: int = 64,
        steps_per_epoch: int = 20,
    ) -> List[dict]:
        """
        Train entirely from the historical replay buffer — no live
        environment interaction, no exploration.

        Returns
        -------
        list[dict]
            Per-epoch stats: epoch, avg_loss, avg_q_value, avg_reward,
            epsilon (logged schedule value, not used for sampling), timestamp.
        """
        n = len(buffer)
        if n == 0:
            raise ValueError(
                "Replay buffer is empty — run the simulation first so RLEnvironment "
                "can populate rl_experiences."
            )
        logger.info(f"Starting offline DQN training: {n} transitions, {num_epochs} epochs.")

        epoch_stats: List[dict] = []
        for epoch in range(1, num_epochs + 1):
            losses: List[float] = []
            q_values: List[float] = []
            rewards_seen: List[float] = []

            for _ in range(steps_per_epoch):
                batch = buffer.sample(batch_size)
                if not batch:
                    break
                loss, mean_q = self.train_step(batch)
                losses.append(loss)
                q_values.append(mean_q)
                rewards_seen.extend(t.reward for t in batch)

            if epoch % TARGET_UPDATE_FREQUENCY_EPOCHS == 0:
                self.update_target_network()

            epsilon = max(
                EPSILON_END,
                EPSILON_START - (EPSILON_START - EPSILON_END) * (epoch / EPSILON_DECAY_EPOCHS),
            )

            stats = {
                "epoch": epoch,
                "avg_loss": sum(losses) / len(losses) if losses else 0.0,
                "avg_q_value": sum(q_values) / len(q_values) if q_values else 0.0,
                "avg_reward": sum(rewards_seen) / len(rewards_seen) if rewards_seen else 0.0,
                "epsilon": epsilon,
                "timestamp": time.time(),
            }
            epoch_stats.append(stats)
            logger.info(
                f"Epoch {epoch}/{num_epochs}: loss={stats['avg_loss']:.4f} "
                f"avg_q={stats['avg_q_value']:.4f} avg_reward={stats['avg_reward']:.4f} "
                f"epsilon={epsilon:.3f}"
            )

        return epoch_stats

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path = DEFAULT_MODEL_PATH) -> None:
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
        checkpoint = torch.load(str(path), map_location=self.device)
        self.policy_net.load_state_dict(checkpoint["policy_net"])
        self.target_net.load_state_dict(checkpoint["target_net"])
        self.optimizer.load_state_dict(checkpoint["optimizer"])
        self.train_step_count = checkpoint.get("train_step_count", 0)
        logger.info(f"DQNAgent checkpoint loaded from {path}")
