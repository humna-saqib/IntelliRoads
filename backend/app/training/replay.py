"""Replay buffer that keeps the action masks of both the current and the next state (Stage 3).

The Double DQN target needs the legal actions of the *next* state (so an illegal action can never be
selected for bootstrapping) and the policy needs those of the *current* state, so both are stored with
every transition.  ``terminated`` (a true terminal state – no bootstrap) and ``truncated`` (time limit –
bootstrap) are stored separately; only ``terminated`` enters the target.

Sampling uses a NumPy ``Generator`` owned by the buffer, so a seeded run samples the same minibatches.
The buffer is intentionally *not* part of routine checkpoints (it is large and rebuilt in a few
episodes); see ``runs.save_checkpoint``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch

N_ACTIONS = 4


@dataclass
class Batch:
    states: torch.Tensor          # float32 [B, S]
    actions: torch.Tensor         # int64   [B, 1]
    rewards: torch.Tensor         # float32 [B]
    next_states: torch.Tensor     # float32 [B, S]
    terminated: torch.Tensor      # float32 [B]  1.0 = true terminal (no bootstrap)
    masks: torch.Tensor           # bool    [B, A]
    next_masks: torch.Tensor      # bool    [B, A]


class MaskedReplayBuffer:
    def __init__(self, capacity: int, state_size: int, seed: int, n_actions: int = N_ACTIONS) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity, self.state_size, self.n_actions = capacity, state_size, n_actions
        self.rng = np.random.default_rng(seed)
        self.states = np.zeros((capacity, state_size), np.float32)
        self.next_states = np.zeros((capacity, state_size), np.float32)
        self.actions = np.zeros(capacity, np.int64)
        self.rewards = np.zeros(capacity, np.float32)
        self.terminated = np.zeros(capacity, np.bool_)
        self.truncated = np.zeros(capacity, np.bool_)
        self.masks = np.zeros((capacity, n_actions), np.bool_)
        self.next_masks = np.zeros((capacity, n_actions), np.bool_)
        self._next = 0
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def push(self, state, action: int, reward: float, next_state, terminated: bool, truncated: bool, mask, next_mask) -> None:
        state, next_state = np.asarray(state, np.float32), np.asarray(next_state, np.float32)
        mask, next_mask = np.asarray(mask, np.bool_), np.asarray(next_mask, np.bool_)
        if state.shape != (self.state_size,) or next_state.shape != (self.state_size,):
            raise ValueError(f"states must have shape ({self.state_size},)")
        for name, m in (("mask", mask), ("next_mask", next_mask)):
            if m.shape != (self.n_actions,):
                raise ValueError(f"{name} must have shape ({self.n_actions},)")
            if not m.any():
                raise ValueError(f"{name} has no legal action")
        if not 0 <= int(action) < self.n_actions:
            raise ValueError(f"invalid action {action}")
        if not mask[int(action)]:
            raise ValueError(f"stored action {action} is not legal under its own mask {mask.tolist()}")
        if not np.isfinite(reward) or not np.isfinite(state).all() or not np.isfinite(next_state).all():
            raise ValueError("non-finite value in transition")
        i = self._next
        self.states[i], self.next_states[i], self.actions[i], self.rewards[i] = state, next_state, int(action), float(reward)
        self.terminated[i], self.truncated[i] = bool(terminated), bool(truncated)
        self.masks[i], self.next_masks[i] = mask, next_mask
        self._next = (i + 1) % self.capacity
        self._size = min(self._size + 1, self.capacity)

    def sample(self, batch_size: int, device: Optional[torch.device] = None) -> Batch:
        if batch_size > self._size:
            raise ValueError(f"cannot sample {batch_size} transitions from a buffer of {self._size}")
        idx = self.rng.choice(self._size, size=batch_size, replace=False)
        t = lambda a, dt: torch.as_tensor(a[idx], dtype=dt, device=device)
        return Batch(t(self.states, torch.float32), t(self.actions, torch.int64).unsqueeze(1), t(self.rewards, torch.float32),
                     t(self.next_states, torch.float32), t(self.terminated, torch.float32),
                     t(self.masks, torch.bool), t(self.next_masks, torch.bool))
