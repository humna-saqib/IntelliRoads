"""
IntelliRoads – Systematic Hyperparameter Tuning for DQN (Sprint 2).

Runs offline training experiments over combinations of hyperparameters (grid search),
evaluates metrics (loss, reward, Q-value), persists runs to the DB, and reports the best configurations.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.dqn_agent import DQNAgent
from app.services.replay_buffer import DB_PATH, SQLiteReplayBuffer


def _ensure_tuning_runs_table(db_path: Path) -> None:
    """Ensure the dqn_tuning_runs table exists in SQLite database."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dqn_tuning_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                learning_rate REAL NOT NULL,
                gamma REAL NOT NULL,
                hidden_size INTEGER NOT NULL,
                epochs INTEGER NOT NULL,
                avg_loss REAL NOT NULL,
                avg_q_value REAL NOT NULL,
                avg_reward REAL NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dqn_tuning_runs_run_id ON dqn_tuning_runs(run_id)"
        )
        conn.commit()
    finally:
        conn.close()


def _persist_run(db_path: Path, run_info: Dict[str, Any]) -> None:
    """Insert tuning trial metrics into database."""
    _ensure_tuning_runs_table(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO dqn_tuning_runs 
            (run_id, learning_rate, gamma, hidden_size, epochs, avg_loss, avg_q_value, avg_reward, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_info["run_id"],
                run_info["learning_rate"],
                run_info["gamma"],
                run_info["hidden_size"],
                run_info["epochs"],
                run_info["avg_loss"],
                run_info["avg_q_value"],
                run_info["avg_reward"],
                run_info["timestamp"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid search hyperparameter tuning for DQN.")
    parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs per configuration trial")
    parser.add_argument("--batch-size", type=int, default=64, help="Minibatch size per training step")
    parser.add_argument("--steps-per-epoch", type=int, default=20, help="Gradient updates per epoch")
    parser.add_argument("--results-json", type=str, default="data/tuning_results.json", help="Path to save search JSON report")
    args = parser.parse_args()

    results_json_path = Path(args.results_json)
    results_json_path.parent.mkdir(parents=True, exist_ok=True)

    buffer = SQLiteReplayBuffer()
    try:
        n = buffer.load()
        print(f"Loaded {n} transitions from {DB_PATH}")
    except FileNotFoundError:
        print(f"Database not found at {DB_PATH}. Please run the simulation first.")
        return
    except Exception as exc:
        print(f"Error loading transitions from database: {exc}")
        return

    if n == 0:
        print("Replay buffer contains no transitions. Populate database first.")
        return

    # Define hyperparameter grid search candidates
    learning_rates = [1e-4, 5e-4, 1e-3]
    gammas = [0.9, 0.95, 0.99]
    hidden_sizes = [32, 64, 128]

    trials: List[Dict[str, Any]] = []
    total_runs = len(learning_rates) * len(gammas) * len(hidden_sizes)
    current_run = 0

    print(f"\nStarting Grid Search: running {total_runs} tuning trials.")
    print("=" * 70)

    for lr in learning_rates:
        for gamma in gammas:
            for hidden in hidden_sizes:
                current_run += 1
                run_id = f"trial_{current_run}_{uuid.uuid4().hex[:6]}"
                print(f"\nTrial {current_run}/{total_runs} | ID: {run_id}")
                print(f"LR: {lr} | Gamma: {gamma} | Hidden: {hidden} | Epochs: {args.epochs}")
                
                try:
                    # Initialize agent with current parameter configuration
                    agent = DQNAgent(
                        learning_rate=lr,
                        gamma=gamma,
                        hidden_size=hidden,
                    )
                    
                    # Train model offline
                    stats = agent.train_offline(
                        buffer=buffer,
                        num_epochs=args.epochs,
                        batch_size=args.batch_size,
                        steps_per_epoch=args.steps_per_epoch,
                    )

                    # Compute final average training metrics from the last 20% of epochs
                    metric_window = max(1, args.epochs // 5)
                    recent_epochs = stats[-metric_window:]
                    avg_loss = sum(e["avg_loss"] for e in recent_epochs) / len(recent_epochs)
                    avg_q = sum(e["avg_q_value"] for e in recent_epochs) / len(recent_epochs)
                    avg_reward = sum(e["avg_reward"] for e in recent_epochs) / len(recent_epochs)

                    trial_result = {
                        "run_id": run_id,
                        "learning_rate": lr,
                        "gamma": gamma,
                        "hidden_size": hidden,
                        "epochs": args.epochs,
                        "avg_loss": round(avg_loss, 4),
                        "avg_q_value": round(avg_q, 4),
                        "avg_reward": round(avg_reward, 4),
                        "timestamp": time.time(),
                    }
                    trials.append(trial_result)

                    # Persist run details in DB
                    _persist_run(DB_PATH, trial_result)

                    print(f"Trial Result -> Loss: {avg_loss:.4f} | Q-Val: {avg_q:.4f} | Reward: {avg_reward:.4f}")

                except Exception as exc:
                    print(f"Trial failed with error: {exc}")

    # Sort trials by reward (descending) and loss (ascending)
    trials.sort(key=lambda x: (x["avg_reward"], -x["avg_loss"]), reverse=True)

    # Save search report to JSON
    with open(results_json_path, "w") as f:
        json.dump(trials, f, indent=2)

    # Print final hyperparameter optimization report
    print("\n" + "=" * 80)
    print("HYPERPARAMETER TUNING OPTIMIZATION REPORT (Ranked by Avg Reward)")
    print("=" * 80)
    print(f"{'Rank':<5} | {'Trial ID':<12} | {'LR':<8} | {'Gamma':<5} | {'Hidden':<6} | {'Avg Loss':<9} | {'Avg Reward':<10}")
    print("-" * 80)
    for rank, t in enumerate(trials, start=1):
        print(
            f"{rank:<5} | {t['run_id']:<12} | {t['learning_rate']:<8} | {t['gamma']:<5} | "
            f"{t['hidden_size']:<6} | {t['avg_loss']:<9.4f} | {t['avg_reward']:<10.4f}"
        )
    print("=" * 80)
    if trials:
        best = trials[0]
        print(f"BEST CONFIGURATION: LR={best['learning_rate']}, Gamma={best['gamma']}, Hidden={best['hidden_size']}")
        print(f"Metrics: Avg Reward={best['avg_reward']:.4f}, Avg Loss={best['avg_loss']:.4f}")
    print("=" * 80)
    print(f"Tuning results report saved to {results_json_path}")


if __name__ == "__main__":
    main()
