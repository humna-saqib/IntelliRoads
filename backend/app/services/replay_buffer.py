"""
IntelliRoads – SQLite-backed replay buffer for offline DQN training (Sprint 2).

Reads directly from the existing rl_experiences table (populated by
RLEnvironment during live/mock simulation runs) as the offline replay
buffer source. This is a read-only view over already-collected
transitions — no new storage, no writes.

Uses plain synchronous sqlite3 rather than aiosqlite: training runs as
a standalone script outside the FastAPI event loop, and PyTorch's
forward/backward passes are blocking anyway, so there's no async
benefit here.
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path
from typing import List, NamedTuple

DB_PATH: Path = Path(__file__).resolve().parent.parent.parent / "data" / "intelliroads.db"

# Fixed action <-> index mapping, shared by the replay buffer and DQNAgent.
ACTION_TO_INDEX = {"DECREASE_GREEN": 0, "KEEP_SAME": 1, "INCREASE_GREEN": 2}
INDEX_TO_ACTION = {v: k for k, v in ACTION_TO_INDEX.items()}


class Transition(NamedTuple):
    state: List[float]
    action: int
    reward: float
    next_state: List[float]
    done: bool


class SQLiteReplayBuffer:
    """Read-only view over the rl_experiences table for offline training."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._transitions: List[Transition] = []

    def load(self) -> int:
        """Load every experience currently in the table. Returns the count loaded."""
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"No database found at {self.db_path}. Run the backend simulation "
                f"first so RLEnvironment can populate rl_experiences."
            )
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "SELECT state_json, action, reward, next_state_json, done FROM rl_experiences"
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        transitions: List[Transition] = []
        for state_json, action, reward, next_state_json, done in rows:
            if action not in ACTION_TO_INDEX:
                continue
            transitions.append(
                Transition(
                    state=json.loads(state_json),
                    action=ACTION_TO_INDEX[action],
                    reward=reward,
                    next_state=json.loads(next_state_json),
                    done=bool(done),
                )
            )
        self._transitions = transitions
        return len(self._transitions)

    def __len__(self) -> int:
        return len(self._transitions)

    def sample(self, batch_size: int) -> List[Transition]:
        """Sample a random minibatch (with replacement if buffer < batch_size)."""
        if not self._transitions:
            return []
        if len(self._transitions) >= batch_size:
            return random.sample(self._transitions, batch_size)
        return random.choices(self._transitions, k=batch_size)
