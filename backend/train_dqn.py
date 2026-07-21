"""
IntelliRoads – Offline DQN training entry point (Sprint 2).

Standalone script — NOT part of the live FastAPI backend and NOT wired
into signal control. Trains a DQNAgent purely from historical
(state, action, reward, next_state) transitions already collected in
the rl_experiences table by RLEnvironment during simulation runs.

Usage:
    python train_dqn.py [--epochs 50] [--batch-size 64] [--steps-per-epoch 20]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.dqn_agent import DEFAULT_MODEL_PATH, DQNAgent  # noqa: E402
from app.services.replay_buffer import DB_PATH, SQLiteReplayBuffer  # noqa: E402


def _ensure_training_stats_table(db_path: Path) -> None:
    """
    Defensive schema creation: the live backend (app.core.database)
    owns this table's canonical definition, but this script must also
    work standalone against a DB file created before that table
    existed, or before the backend has been restarted since.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dqn_training_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                epoch INTEGER NOT NULL,
                avg_loss REAL NOT NULL,
                avg_q_value REAL NOT NULL,
                avg_reward REAL NOT NULL,
                epsilon REAL NOT NULL,
                buffer_size INTEGER NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dqn_training_stats_epoch ON dqn_training_stats(epoch)"
        )
        conn.commit()
    finally:
        conn.close()


def _persist_stats(db_path: Path, epoch_stats: List[dict], buffer_size: int) -> None:
    _ensure_training_stats_table(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            "INSERT INTO dqn_training_stats "
            "(epoch, avg_loss, avg_q_value, avg_reward, epsilon, buffer_size, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    s["epoch"], s["avg_loss"], s["avg_q_value"], s["avg_reward"],
                    s["epsilon"], buffer_size, s["timestamp"],
                )
                for s in epoch_stats
            ],
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    from app.core.dqn_config import load_dqn_config
    config = load_dqn_config()

    parser = argparse.ArgumentParser(description="Offline DQN training from collected rl_experiences.")
    parser.add_argument("--epochs", type=int, default=config.offline_epochs, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=config.batch_size_offline, help="Minibatch training size")
    parser.add_argument("--steps-per-epoch", type=int, default=config.offline_steps_per_epoch, help="SGD steps per epoch")
    parser.add_argument("--model-path", type=str, default=str(DEFAULT_MODEL_PATH), help="Path to save trained PyTorch model")
    
    # Custom Hyperparameter overrides
    parser.add_argument("--lr", type=float, default=None, help="Learning rate override")
    parser.add_argument("--gamma", type=float, default=None, help="Gamma (discount factor) override")
    parser.add_argument("--hidden-size", type=int, default=None, help="Hidden layers dimension override")
    parser.add_argument("--target-update", type=int, default=None, help="Target update epoch frequency override")
    parser.add_argument("--epsilon-start", type=float, default=None, help="Starting epsilon override")
    parser.add_argument("--epsilon-end", type=float, default=None, help="Ending epsilon override")
    parser.add_argument("--epsilon-decay", type=int, default=None, help="Epsilon decay duration in epochs override")
    args = parser.parse_args()

    buffer = SQLiteReplayBuffer()
    n = buffer.load()
    print(f"Loaded {n} transitions from {DB_PATH}")
    if n == 0:
        print("No experiences found. Run the backend simulation first so RLEnvironment can populate rl_experiences.")
        return

    agent = DQNAgent(
        gamma=args.gamma,
        learning_rate=args.lr,
        hidden_size=args.hidden_size,
        target_update_frequency_epochs=args.target_update,
        epsilon_start=args.epsilon_start,
        epsilon_end=args.epsilon_end,
        epsilon_decay_epochs=args.epsilon_decay,
    )
    epoch_stats = agent.train_offline(
        buffer,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        steps_per_epoch=args.steps_per_epoch,
    )

    _persist_stats(DB_PATH, epoch_stats, buffer_size=n)

    model_path = Path(args.model_path)
    agent.save(model_path)
    print(f"Training complete. Model saved to {model_path}")

    first, last = epoch_stats[0], epoch_stats[-1]
    print(f"Loss:              {first['avg_loss']:.4f} -> {last['avg_loss']:.4f}")
    print(f"Avg Q-value:       {first['avg_q_value']:.4f} -> {last['avg_q_value']:.4f}")
    print(f"Avg reward/batch:  {first['avg_reward']:.4f} -> {last['avg_reward']:.4f}")


if __name__ == "__main__":
    main()
