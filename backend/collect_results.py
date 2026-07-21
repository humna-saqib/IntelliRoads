"""
IntelliRoads – Centralized Results Collection System (Sprint 2 - Feature 5).

Aggregates training metrics, tuning results, experiment comparisons, and simulation runs.
Computes summary statistics, generates backend/data/summary.json, and persists results to SQLite.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Define paths
BACKEND_DIR = Path(__file__).resolve().parent
DB_PATH = BACKEND_DIR / "data" / "intelliroads.db"
TUNING_JSON_PATH = BACKEND_DIR / "data" / "tuning_results.json"
EXPERIMENTS_JSON_PATH = BACKEND_DIR / "data" / "experiments" / "summary.json"
SIMULATIONS_JSON_PATH = BACKEND_DIR / "data" / "simulations" / "summary.json"
OUTPUT_JSON_PATH = BACKEND_DIR / "data" / "summary.json"


def _ensure_summary_tables(conn: sqlite3.Connection) -> None:
    """Ensure that the centralized summary tables exist in the database."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dqn_centralized_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            summary_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dqn_centralized_summary_timestamp ON dqn_centralized_summary(timestamp)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dqn_summary_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value TEXT NOT NULL,
            source_id TEXT,
            source_type TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dqn_summary_statistics_metric ON dqn_summary_statistics(metric_name)"
    )
    conn.commit()


def fetch_training_metrics(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Fetch training metrics from SQLite dqn_training_stats table."""
    metrics = []
    try:
        cursor = conn.execute(
            """
            SELECT epoch, avg_loss, avg_q_value, avg_reward, epsilon, buffer_size, timestamp 
            FROM dqn_training_stats 
            ORDER BY timestamp ASC, epoch ASC
            """
        )
        for row in cursor.fetchall():
            metrics.append({
                "epoch": row[0],
                "avg_loss": round(row[1], 4),
                "avg_q_value": round(row[2], 4),
                "avg_reward": round(row[3], 4),
                "epsilon": round(row[4], 3),
                "buffer_size": row[5],
                "timestamp": row[6]
            })
    except sqlite3.OperationalError as exc:
        print(f"[Warning] Failed to read dqn_training_stats table: {exc}")
    return metrics


def fetch_tuning_results(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Fetch tuning results from SQLite dqn_tuning_runs and/or fallback JSON."""
    results = {}
    
    # 1. Try fetching from database
    try:
        cursor = conn.execute(
            """
            SELECT run_id, learning_rate, gamma, hidden_size, epochs, avg_loss, avg_q_value, avg_reward, timestamp
            FROM dqn_tuning_runs
            """
        )
        for row in cursor.fetchall():
            results[row[0]] = {
                "run_id": row[0],
                "learning_rate": row[1],
                "gamma": row[2],
                "hidden_size": row[3],
                "epochs": row[4],
                "avg_loss": round(row[5], 4),
                "avg_q_value": round(row[6], 4),
                "avg_reward": round(row[7], 4),
                "timestamp": row[8]
            }
    except sqlite3.OperationalError as exc:
        print(f"[Warning] Failed to read dqn_tuning_runs table: {exc}")

    # 2. Try merging with JSON file
    if TUNING_JSON_PATH.exists():
        try:
            with open(TUNING_JSON_PATH, "r") as f:
                json_data = json.load(f)
                for item in json_data:
                    run_id = item.get("run_id")
                    if run_id:
                        # Normalize values
                        results[run_id] = {
                            "run_id": run_id,
                            "learning_rate": item.get("learning_rate"),
                            "gamma": item.get("gamma"),
                            "hidden_size": item.get("hidden_size"),
                            "epochs": item.get("epochs"),
                            "avg_loss": round(item.get("avg_loss", 0.0), 4),
                            "avg_q_value": round(item.get("avg_q_value", 0.0), 4),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "timestamp": item.get("timestamp", time.time())
                        }
        except Exception as exc:
            print(f"[Warning] Failed to read tuning results JSON: {exc}")

    return list(results.values())


def fetch_experiment_results(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Fetch experiment results from SQLite dqn_experiments and/or fallback JSON."""
    results = {}

    # 1. Try database
    try:
        cursor = conn.execute(
            """
            SELECT experiment_id, timestamp, learning_rate, gamma, hidden_size, epochs, avg_reward, avg_loss, model_path
            FROM dqn_experiments
            """
        )
        for row in cursor.fetchall():
            results[row[0]] = {
                "experiment_id": row[0],
                "timestamp": row[1],
                "learning_rate": row[2],
                "gamma": row[3],
                "hidden_size": row[4],
                "epochs": row[5],
                "avg_reward": round(row[6], 4),
                "avg_loss": round(row[7], 4),
                "model_path": row[8]
            }
    except sqlite3.OperationalError as exc:
        print(f"[Warning] Failed to read dqn_experiments table: {exc}")

    # 2. Try JSON
    if EXPERIMENTS_JSON_PATH.exists():
        try:
            with open(EXPERIMENTS_JSON_PATH, "r") as f:
                json_data = json.load(f)
                for item in json_data:
                    exp_id = item.get("experiment_id")
                    if exp_id:
                        results[exp_id] = {
                            "experiment_id": exp_id,
                            "timestamp": item.get("timestamp", time.time()),
                            "learning_rate": item.get("learning_rate"),
                            "gamma": item.get("gamma"),
                            "hidden_size": item.get("hidden_size"),
                            "epochs": item.get("epochs"),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "avg_loss": round(item.get("avg_loss", 0.0), 4),
                            "model_path": item.get("model_path", "")
                        }
        except Exception as exc:
            print(f"[Warning] Failed to read experiments summary JSON: {exc}")

    return list(results.values())


def fetch_simulation_results(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Fetch simulation runs from SQLite sumo_simulation_runs and/or fallback JSON."""
    results = {}

    # 1. Try database
    try:
        cursor = conn.execute(
            """
            SELECT run_id, start_time, end_time, duration, avg_waiting_time, avg_queue_length, throughput, avg_reward, timestamp
            FROM sumo_simulation_runs
            """
        )
        for row in cursor.fetchall():
            results[row[0]] = {
                "run_id": row[0],
                "start_time": row[1],
                "end_time": row[2],
                "duration": round(row[3], 2),
                "avg_waiting_time": round(row[4], 4),
                "avg_queue_length": round(row[5], 4),
                "throughput": row[6],
                "avg_reward": round(row[7], 4),
                "timestamp": row[8]
            }
    except sqlite3.OperationalError as exc:
        print(f"[Warning] Failed to read sumo_simulation_runs table: {exc}")

    # 2. Try JSON
    if SIMULATIONS_JSON_PATH.exists():
        try:
            with open(SIMULATIONS_JSON_PATH, "r") as f:
                json_data = json.load(f)
                for item in json_data:
                    run_id = item.get("run_id")
                    if run_id:
                        results[run_id] = {
                            "run_id": run_id,
                            "start_time": item.get("start_time"),
                            "end_time": item.get("end_time"),
                            "duration": round(item.get("duration", 0.0), 2),
                            "avg_waiting_time": round(item.get("avg_waiting_time", 0.0), 4),
                            "avg_queue_length": round(item.get("avg_queue_length", 0.0), 4),
                            "throughput": item.get("throughput", 0),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "timestamp": item.get("timestamp", time.time())
                        }
        except Exception as exc:
            print(f"[Warning] Failed to read simulations summary JSON: {exc}")

    return list(results.values())


def compute_summary_statistics(
    training: List[Dict[str, Any]],
    tuning: List[Dict[str, Any]],
    experiments: List[Dict[str, Any]],
    simulations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute summary metrics and choose best performing settings/runs."""
    # Initialize defaults
    best_reward_val = -float("inf")
    best_reward_src = "None"
    best_reward_id = "None"

    lowest_loss_val = float("inf")
    lowest_loss_src = "None"
    lowest_loss_id = "None"

    # Evaluate Training for best reward / lowest loss
    for t in training:
        if t["avg_reward"] > best_reward_val:
            best_reward_val = t["avg_reward"]
            best_reward_src = "training"
            best_reward_id = f"epoch_{t['epoch']}"
        if t["avg_loss"] < lowest_loss_val:
            lowest_loss_val = t["avg_loss"]
            lowest_loss_src = "training"
            lowest_loss_id = f"epoch_{t['epoch']}"

    # Evaluate Tuning for best reward / lowest loss
    for t in tuning:
        if t["avg_reward"] > best_reward_val:
            best_reward_val = t["avg_reward"]
            best_reward_src = "tuning"
            best_reward_id = t["run_id"]
        if t["avg_loss"] < lowest_loss_val:
            lowest_loss_val = t["avg_loss"]
            lowest_loss_src = "tuning"
            lowest_loss_id = t["run_id"]

    # Evaluate Experiments for best reward / lowest loss
    best_exp_item = None
    best_exp_reward = -float("inf")
    for e in experiments:
        if e["avg_reward"] > best_reward_val:
            best_reward_val = e["avg_reward"]
            best_reward_src = "experiments"
            best_reward_id = e["experiment_id"]
        if e["avg_loss"] < lowest_loss_val:
            lowest_loss_val = e["avg_loss"]
            lowest_loss_src = "experiments"
            lowest_loss_id = e["experiment_id"]
        
        # Track best experiment specifically
        if e["avg_reward"] > best_exp_reward:
            best_exp_reward = e["avg_reward"]
            best_exp_item = {
                "experiment_id": e["experiment_id"],
                "avg_reward": e["avg_reward"],
                "avg_loss": e["avg_loss"]
            }

    # Evaluate Simulations for best reward and averages
    best_sim_item = None
    best_sim_reward = -float("inf")
    sim_throughputs = []
    sim_waiting_times = []
    sim_queue_lengths = []

    for s in simulations:
        sim_throughputs.append(s["throughput"])
        sim_waiting_times.append(s["avg_waiting_time"])
        sim_queue_lengths.append(s["avg_queue_length"])

        if s["avg_reward"] > best_reward_val:
            best_reward_val = s["avg_reward"]
            best_reward_src = "simulations"
            best_reward_id = s["run_id"]
            
        if s["avg_reward"] > best_sim_reward:
            best_sim_reward = s["avg_reward"]
            best_sim_item = {
                "run_id": s["run_id"],
                "avg_reward": s["avg_reward"],
                "avg_waiting_time": s["avg_waiting_time"],
                "avg_queue_length": s["avg_queue_length"],
                "throughput": s["throughput"]
            }

    # Compute averages across simulations
    avg_throughput = sum(sim_throughputs) / len(sim_throughputs) if sim_throughputs else 0.0
    avg_waiting_time = sum(sim_waiting_times) / len(sim_waiting_times) if sim_waiting_times else 0.0
    avg_queue_length = sum(sim_queue_lengths) / len(sim_queue_lengths) if sim_queue_lengths else 0.0

    return {
        "best_average_reward": {
            "value": round(best_reward_val, 4) if best_reward_val != -float("inf") else 0.0,
            "source": best_reward_src,
            "id": best_reward_id
        },
        "lowest_loss": {
            "value": round(lowest_loss_val, 4) if lowest_loss_val != float("inf") else 0.0,
            "source": lowest_loss_src,
            "id": lowest_loss_id
        },
        "best_experiment": best_exp_item,
        "best_simulation": best_sim_item,
        "number_of_runs": {
            "training_epochs": len(training),
            "tuning_trials": len(tuning),
            "experiments": len(experiments),
            "simulations": len(simulations),
            "total_runs": len(training) + len(tuning) + len(experiments) + len(simulations)
        },
        "average_throughput": round(avg_throughput, 2),
        "average_waiting_time": round(avg_waiting_time, 4),
        "average_queue_length": round(avg_queue_length, 4)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and aggregate DQN and SUMO results.")
    parser.add_argument("--db-path", type=str, default=str(DB_PATH), help="Path to SQLite database")
    parser.add_argument("--output", type=str, default=str(OUTPUT_JSON_PATH), help="Path to write summary.json")
    args = parser.parse_args()

    db_file_path = Path(args.db_path)
    output_file_path = Path(args.output)

    # 1. Connect to DB and gather stats
    if not db_file_path.exists():
        print(f"Database not found at {db_file_path}. Creating clean summary tables on a new DB.")
    
    db_file_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file_path))
    
    try:
        # Ensure our centralized schema is loaded
        _ensure_summary_tables(conn)

        print("\nAggregating results from all sources...")
        training_metrics = fetch_training_metrics(conn)
        tuning_results = fetch_tuning_results(conn)
        experiment_results = fetch_experiment_results(conn)
        simulation_results = fetch_simulation_results(conn)

        print(f"  Training epochs: {len(training_metrics)}")
        print(f"  Tuning trials:   {len(tuning_results)}")
        print(f"  Experiments:     {len(experiment_results)}")
        print(f"  Simulations:     {len(simulation_results)}")

        # 2. Compute statistics
        summary_stats = compute_summary_statistics(
            training_metrics, tuning_results, experiment_results, simulation_results
        )

        aggregated_results = {
            "summary_statistics": summary_stats,
            "training_metrics": training_metrics,
            "tuning_results": tuning_results,
            "experiment_results": experiment_results,
            "simulation_results": simulation_results
        }

        # 3. Store aggregated metrics in JSON file
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file_path, "w") as f:
            json.dump(aggregated_results, f, indent=2)
        print(f"\nCentralized JSON summary report written to {output_file_path}")

        # 4. Store aggregated metrics in SQLite
        current_time = time.time()
        
        # Store full json stringified
        conn.execute(
            "INSERT INTO dqn_centralized_summary (timestamp, summary_json) VALUES (?, ?)",
            (current_time, json.dumps(aggregated_results)),
        )

        # Store relational summary statistics
        stats_rows = [
            ("best_average_reward", str(summary_stats["best_average_reward"]["value"]), summary_stats["best_average_reward"]["id"], summary_stats["best_average_reward"]["source"], current_time),
            ("lowest_loss", str(summary_stats["lowest_loss"]["value"]), summary_stats["lowest_loss"]["id"], summary_stats["lowest_loss"]["source"], current_time),
            ("total_runs", str(summary_stats["number_of_runs"]["total_runs"]), None, "all", current_time),
            ("training_epochs_count", str(summary_stats["number_of_runs"]["training_epochs"]), None, "training", current_time),
            ("tuning_trials_count", str(summary_stats["number_of_runs"]["tuning_trials"]), None, "tuning", current_time),
            ("experiments_count", str(summary_stats["number_of_runs"]["experiments"]), None, "experiments", current_time),
            ("simulations_count", str(summary_stats["number_of_runs"]["simulations"]), None, "simulations", current_time),
            ("average_throughput", str(summary_stats["average_throughput"]), None, "simulations", current_time),
            ("average_waiting_time", str(summary_stats["average_waiting_time"]), None, "simulations", current_time),
            ("average_queue_length", str(summary_stats["average_queue_length"]), None, "simulations", current_time),
        ]
        
        if summary_stats["best_experiment"]:
            stats_rows.append((
                "best_experiment_id",
                summary_stats["best_experiment"]["experiment_id"],
                summary_stats["best_experiment"]["experiment_id"],
                "experiments",
                current_time
            ))
            stats_rows.append((
                "best_experiment_reward",
                str(summary_stats["best_experiment"]["avg_reward"]),
                summary_stats["best_experiment"]["experiment_id"],
                "experiments",
                current_time
            ))
            
        if summary_stats["best_simulation"]:
            stats_rows.append((
                "best_simulation_id",
                summary_stats["best_simulation"]["run_id"],
                summary_stats["best_simulation"]["run_id"],
                "simulations",
                current_time
            ))
            stats_rows.append((
                "best_simulation_reward",
                str(summary_stats["best_simulation"]["avg_reward"]),
                summary_stats["best_simulation"]["run_id"],
                "simulations",
                current_time
            ))

        conn.executemany(
            """
            INSERT INTO dqn_summary_statistics (metric_name, metric_value, source_id, source_type, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            stats_rows
        )
        conn.commit()
        print("Centralized metrics successfully persisted to SQLite database tables.")

        # 5. Print a summary optimization report table
        print("\n" + "=" * 60)
        print(" INTELLIROADS CENTRALIZED METRICS SUMMARY REPORT")
        print("=" * 60)
        print(f"  Total Runs Processed:      {summary_stats['number_of_runs']['total_runs']}")
        print(f"    - Training Epochs:        {summary_stats['number_of_runs']['training_epochs']}")
        print(f"    - Tuning Trials:          {summary_stats['number_of_runs']['tuning_trials']}")
        print(f"    - Evaluation Experiments: {summary_stats['number_of_runs']['experiments']}")
        print(f"    - Simulation Runs:        {summary_stats['number_of_runs']['simulations']}")
        print("-" * 60)
        best_rew = summary_stats["best_average_reward"]
        print(f"  Best Average Reward:       {best_rew['value']} (Source: {best_rew['source']}, ID: {best_rew['id']})")
        low_loss = summary_stats["lowest_loss"]
        print(f"  Lowest Training Loss:      {low_loss['value']} (Source: {low_loss['source']}, ID: {low_loss['id']})")
        
        if summary_stats["best_experiment"]:
            be = summary_stats["best_experiment"]
            print(f"  Best Experiment:           {be['experiment_id']} (Reward: {be['avg_reward']:.4f}, Loss: {be['avg_loss']:.4f})")
            
        if summary_stats["best_simulation"]:
            bs = summary_stats["best_simulation"]
            print(f"  Best Simulation:           {bs['run_id']} (Reward: {bs['avg_reward']:.4f}, Wait: {bs['avg_waiting_time']:.2f}s, Throughput: {bs['throughput']})")
            
        print("-" * 60)
        print(f"  Average Simulation Metrics:")
        print(f"    - Throughput:            {summary_stats['average_throughput']}")
        print(f"    - Waiting Time (s):      {summary_stats['average_waiting_time']:.4f}")
        print(f"    - Queue Length:          {summary_stats['average_queue_length']:.4f}")
        print("=" * 60 + "\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
