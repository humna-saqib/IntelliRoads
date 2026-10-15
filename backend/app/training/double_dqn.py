"""Mask-aware Double DQN (Stage 3).

* **Action selection** is epsilon-greedy over the *legal* actions only (``act``).
* **Double-DQN target.**  ``a* = argmax_{a legal in s'} Q_policy(s', a)``;  ``y = r + gamma * Q_target(s', a*)``.
  The legality mask of the **next** state is applied to the *policy* network's argmax, so an illegal action can
  never be selected for bootstrapping (the unmasked rule could pick, say, SWITCH inside a yellow phase, and
  would then bootstrap from a value the policy is never allowed to realise).
* **Terminal vs truncation.**  Only a true terminal transition cuts the bootstrap (``(1 - terminated)``); a
  time-limit truncation still bootstraps from ``s'``.
* No target clamping: the legacy ``clamp(-100, 50)`` hid the reward scale; rewards are scaled instead
  (``TrainConfig.reward_scale``) and logged.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from app.agent.dqn_agent import QNetwork
from app.training.replay import Batch


def double_dqn_targets(policy_net: nn.Module, target_net: nn.Module, next_states: torch.Tensor, next_masks: torch.Tensor,
                       rewards: torch.Tensor, terminated: torch.Tensor, gamma: float) -> torch.Tensor:
    """Mask-aware Double-DQN bootstrap targets (no gradient)."""
    if not bool(next_masks.any(dim=1).all()):
        raise ValueError("a next-state mask has no legal action")
    with torch.no_grad():
        q_policy = policy_net(next_states).masked_fill(~next_masks, float("-inf"))
        best_legal = q_policy.argmax(dim=1, keepdim=True)                 # selection: policy net, legal actions only
        q_next = target_net(next_states).gather(1, best_legal).squeeze(1)  # evaluation: target net
        return rewards + gamma * q_next * (1.0 - terminated)


class MaskedDoubleDQN:
    def __init__(self, state_size: int, n_actions: int = 4, hidden: int = 64, gamma: float = 0.95, lr: float = 5e-4,
                 grad_clip: float = 1.0, seed: int = 0, device: str = "cpu") -> None:
        self.state_size, self.n_actions, self.gamma, self.grad_clip = state_size, n_actions, gamma, grad_clip
        self.device = torch.device(device)
        self.policy_net = QNetwork(state_size, n_actions, hidden_size=hidden).to(self.device)
        self.target_net = QNetwork(state_size, n_actions, hidden_size=hidden).to(self.device)
        self.sync_target()
        self.target_net.eval()
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=lr)
        self.loss_fn = nn.SmoothL1Loss()
        self.rng = np.random.default_rng(seed + 1)               # exploration generator (replay has its own)
        self.grad_steps = 0

    # ------------------------------------------------------------------ acting
    def act(self, state, mask, epsilon: float) -> int:
        legal = np.flatnonzero(np.asarray(mask, np.bool_))
        if legal.size == 0:
            raise ValueError("mask has no legal action")
        if self.rng.random() < epsilon:
            return int(self.rng.choice(legal))
        return self.greedy(state, mask)

    def random_legal(self, mask) -> int:
        legal = np.flatnonzero(np.asarray(mask, np.bool_))
        if legal.size == 0:
            raise ValueError("mask has no legal action")
        return int(self.rng.choice(legal))

    def greedy(self, state, mask) -> int:
        with torch.no_grad():
            q = self.policy_net(torch.as_tensor(np.asarray(state, np.float32), device=self.device).unsqueeze(0))
            q = q.masked_fill(~torch.as_tensor(np.asarray(mask, np.bool_), device=self.device).unsqueeze(0), float("-inf"))
            return int(q.argmax(dim=1).item())

    # ------------------------------------------------------------------ learning
    def train_step(self, batch: Batch) -> Tuple[float, float]:
        q = self.policy_net(batch.states).gather(1, batch.actions).squeeze(1)
        targets = double_dqn_targets(self.policy_net, self.target_net, batch.next_states, batch.next_masks,
                                     batch.rewards, batch.terminated, self.gamma)
        loss = self.loss_fn(q, targets)
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=self.grad_clip)
        self.optimizer.step()
        self.grad_steps += 1
        return float(loss.item()), float(q.detach().mean().item())

    def sync_target(self) -> None:
        self.target_net.load_state_dict(self.policy_net.state_dict())

    def maybe_sync_target(self, every_grad_steps: int) -> bool:
        """Hard target update every ``every_grad_steps`` *gradient steps* (not epochs)."""
        if every_grad_steps < 1:
            raise ValueError("target update interval must be >= 1 gradient step")
        if self.grad_steps > 0 and self.grad_steps % every_grad_steps == 0:
            self.sync_target()
            return True
        return False
