"""
IntelliRoads – Training Experiment Framework (Sprint 2 - Feature 3).

Orchestrates running multiple independent offline DQN training experiments,
logs detailed epoch results to files and database, and outputs comparison tables.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# Add backend directory to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.dqn_agent import DQNAgent
from app.services.replay_buffer import DB_PATH, SQLiteReplayBuffer

EXPERIMENTS_DIR = Path(__file__).resolve().parent / "data" / "experiments"


def _ensure_experiment_tables(db_path: Path) -> None:
    """Ensure table structures exist in SQLite for experiments tracking."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dqn_experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL UNIQUE,
                timestamp REAL NOT NULL,
                learning_rate REAL NOT NULL,
                gamma REAL NOT NULL,
                hidden_size INTEGER NOT NULL,
                epochs INTEGER NOT NULL,
                avg_reward REAL NOT NULL,
                avg_loss REAL NOT NULL,
                model_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dqn_experiment_epoch_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                avg_loss REAL NOT NULL,
                avg_q_value REAL NOT NULL,
                avg_reward REAL NOT NULL,
                epsilon REAL NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY(experiment_id) REFERENCES dqn_experiments(experiment_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dqn_experiments_id ON dqn_experiments(experiment_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dqn_experiment_epoch_stats_id ON dqn_experiment_epoch_stats(experiment_id)"
        )
        conn.commit()
    finally:
        conn.close()


def _persist_experiment_to_db(db_path: Path, metadata: Dict[str, Any], epoch_stats: List[Dict[str, Any]]) -> None:
    """Save experiment metadata and epoch details into the database, clearing any duplicate ID first."""
    _ensure_experiment_tables(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        # Cascade deletes matching experiment_id to keep databases clean
        conn.execute("DELETE FROM dqn_experiments WHERE experiment_id = ?", (metadata["experiment_id"],))
        
        conn.execute(
            """
            INSERT INTO dqn_experiments 
            (experiment_id, timestamp, learning_rate, gamma, hidden_size, epochs, avg_reward, avg_loss, model_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata["experiment_id"],
                metadata["timestamp"],
                metadata["learning_rate"],
                metadata["gamma"],
                metadata["hidden_size"],
                metadata["epochs"],
                metadata["avg_reward"],
                metadata["avg_loss"],
                metadata["model_path"],
            ),
        )

        conn.executemany(
            """
            INSERT INTO dqn_experiment_epoch_stats
            (experiment_id, epoch, avg_loss, avg_q_value, avg_reward, epsilon, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    metadata["experiment_id"],
                    epoch["epoch"],
                    epoch["avg_loss"],
                    epoch["avg_q_value"],
                    epoch["avg_reward"],
                    epoch["epsilon"],
                    epoch["timestamp"],
                )
                for epoch in epoch_stats
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _update_master_summary(summary_file: Path, new_runs: List[Dict[str, Any]]) -> None:
    """Read existing summary JSON, merge runs, and overwrite file."""
    existing_runs: List[Dict[str, Any]] = []
    if summary_file.exists():
        try:
            with open(summary_file, "r") as f:
                existing_runs = json.load(f)
        except Exception:
            pass

    # Map existing runs by ID
    run_map = {run["experiment_id"]: run for run in existing_runs}
    for run in new_runs:
        run_map[run["experiment_id"]] = run

    with open(summary_file, "w") as f:
        json.dump(list(run_map.values()), f, indent=2)


def get_default_experiments() -> List[Dict[str, Any]]:
    """Return default set of independent training experiments."""
    return [
        {
            "experiment_id": "exp_baseline",
            "learning_rate": 0.001,
            "gamma": 0.99,
            "hidden_size": 64,
        },
        {
            "experiment_id": "exp_low_lr",
            "learning_rate": 0.0001,
            "gamma": 0.99,
            "hidden_size": 64,
        },
        {
            "experiment_id": "exp_high_gamma",
            "learning_rate": 0.001,
            "gamma": 0.95,
            "hidden_size": 64,
        },
        {
            "experiment_id": "exp_hidden_large",
            "learning_rate": 0.001,
            "gamma": 0.99,
            "hidden_size": 128,
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="DQN Offline Training Experiment Framework.")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON file specifying configuration of experiments list to run",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=10,
        help="Global default epochs per experiment run",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Global default batch size per gradient step",
    )
    parser.add_argument(
        "--steps-per-epoch",
        type=int,
        default=20,
        help="Global default steps per training epoch",
    )
    args = parser.parse_args()

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_json_path = EXPERIMENTS_DIR / "summary.json"

    # 1. Load transition buffer
    buffer = SQLiteReplayBuffer()
    try:
        n = buffer.load()
        logger.info(f"Loaded {n} transitions from database file: {DB_PATH}")
    except Exception as exc:
        logger.error(f"Failed to load SQLite replay buffer from {DB_PATH}: {exc}")
        sys.exit(1)

    if n == 0:
        logger.error("Replay buffer has no transitions. Run SUMO simulations to collect data first.")
        sys.exit(1)

    # 2. Determine experiments definitions list
    experiments: List[Dict[str, Any]] = []
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            logger.error(f"Provided config file not found at: {config_path}")
            sys.exit(1)
        try:
            with open(config_path, "r") as f:
                experiments = json.load(f)
            logger.info(f"Loaded {len(experiments)} experiment configurations from: {config_path}")
        except Exception as exc:
            logger.error(f"Failed to parse config JSON file: {exc}")
            sys.exit(1)
    else:
        experiments = get_default_experiments()
        logger.info(f"No config provided. Running default suite of {len(experiments)} experiments.")

    # Validate experiment configurations
    for idx, exp in enumerate(experiments):
        if "experiment_id" not in exp:
            exp["experiment_id"] = f"exp_{idx + 1}_{int(time.time())}"

    completed_runs: List[Dict[str, Any]] = []

    logger.info(f"Starting experiments execution suite. Results will save under {EXPERIMENTS_DIR}")
    print("=" * 80)

    for idx, exp in enumerate(experiments):
        exp_id = exp["experiment_id"]
        lr = exp.get("learning_rate", 0.001)
        gamma = exp.get("gamma", 0.99)
        hidden = exp.get("hidden_size", 64)
        
        # Determine local runtime limits, falling back to global cli limits
        exp_epochs = exp.get("epochs", args.epochs)
        exp_batch_size = exp.get("batch_size", args.batch_size)
        exp_steps_per_epoch = exp.get("steps_per_epoch", args.steps_per_epoch)

        exp_dir = EXPERIMENTS_DIR / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        log_file = exp_dir / "experiment.log"

        # Start capturing logs for this trial to a dedicated file handler
        handler_id = logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO",
            encoding="utf-8",
        )

        logger.info(f"[{idx + 1}/{len(experiments)}] STARTING EXPERIMENT: {exp_id}")
        logger.info(f"Parameters: LR={lr} | Gamma={gamma} | Hidden={hidden} | Epochs={exp_epochs}")

        trial_start_time = time.time()
        try:
            # Initialize clean agent
            agent = DQNAgent(
                learning_rate=lr,
                gamma=gamma,
                hidden_size=hidden,
            )

            # Train agent offline
            stats = agent.train_offline(
                buffer=buffer,
                num_epochs=exp_epochs,
                batch_size=exp_batch_size,
                steps_per_epoch=exp_steps_per_epoch,
            )

            # Save PyTorch weights
            model_path = exp_dir / "model.pt"
            agent.save(model_path)
            logger.info(f"Model checkpoint saved successfully to {model_path}")

            # Save detailed per-epoch JSON stats
            stats_json_path = exp_dir / "stats.json"
            with open(stats_json_path, "w") as f:
                json.dump(stats, f, indent=2)
            logger.info(f"Epoch statistics report saved successfully to {stats_json_path}")

            # Calculate final metrics over the last 20% epochs window
            window_size = max(1, exp_epochs // 5)
            recent_epochs = stats[-window_size:]
            avg_loss = sum(epoch["avg_loss"] for epoch in recent_epochs) / len(recent_epochs)
            avg_reward = sum(epoch["avg_reward"] for epoch in recent_epochs) / len(recent_epochs)

            metadata = {
                "experiment_id": exp_id,
                "timestamp": trial_start_time,
                "learning_rate": lr,
                "gamma": gamma,
                "hidden_size": hidden,
                "epochs": exp_epochs,
                "avg_reward": round(avg_reward, 4),
                "avg_loss": round(avg_loss, 4),
                "model_path": str(model_path),
            }

            # Persist metadata and detailed trajectories into SQLite DB
            _persist_experiment_to_db(DB_PATH, metadata, stats)
            completed_runs.append(metadata)

            logger.info(f"Finished Experiment: {exp_id} in {time.time() - trial_start_time:.2f}s")
            logger.info(f"Metrics: Avg Loss={avg_loss:.4f} | Avg Reward={avg_reward:.4f}")

        except Exception as exc:
            logger.exception(f"Experiment {exp_id} failed with exception: {exc}")
        finally:
            # Stop file logging for this experiment
            logger.remove(handler_id)

    # 3. Post-run master summary generation
    if completed_runs:
        _update_master_summary(summary_json_path, completed_runs)

        # Print final comparison table
        print("\n" + "=" * 90)
        print("EXPERIMENT RUNS COMPARISON TABLE")
        print("=" * 90)
        print(f"{'Experiment ID':<18} | {'LR':<8} | {'Gamma':<5} | {'Hidden':<6} | {'Epochs':<6} | {'Avg Loss':<9} | {'Avg Reward':<10}")
        print("-" * 90)
        
        # Sort comparisons by reward (descending)
        completed_runs.sort(key=lambda x: (x["avg_reward"], -x["avg_loss"]), reverse=True)
        for r in completed_runs:
            print(
                f"{r['experiment_id']:<18} | {r['learning_rate']:<8} | {r['gamma']:<5} | "
                f"{r['hidden_size']:<6} | {r['epochs']:<6} | {r['avg_loss']:<9.4f} | {r['avg_reward']:<10.4f}"
            )
        print("=" * 90)
        logger.info(f"Master summary file saved at: {summary_json_path}")
    else:
        logger.warning("No experiments were completed successfully.")


if __name__ == "__main__":
    main()
