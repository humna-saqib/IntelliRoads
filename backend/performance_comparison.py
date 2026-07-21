"""
IntelliRoads – Performance Comparison Tables (Sprint 2 - Feature 7).

Aggregates data from SQLite database, summary.json, tuning_results.json,
experiment summaries, and simulation summaries. Generates tabular comparison reports
in JSON, CSV, and SQLite formats, and prints formatted ASCII tables to the terminal.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# Add backend directory to PYTHONPATH
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

# Default file paths
DB_PATH = BACKEND_DIR / "data" / "intelliroads.db"
TUNING_JSON_PATH = BACKEND_DIR / "data" / "tuning_results.json"
EXPERIMENTS_JSON_PATH = BACKEND_DIR / "data" / "experiments" / "summary.json"
SIMULATIONS_JSON_PATH = BACKEND_DIR / "data" / "simulations" / "summary.json"
SUMMARY_JSON_PATH = BACKEND_DIR / "data" / "summary.json"

OUTPUT_JSON_PATH = BACKEND_DIR / "data" / "performance_tables.json"
OUTPUT_CSV_PATH = BACKEND_DIR / "data" / "performance_tables.csv"


def setup_db_tables(conn: sqlite3.Connection) -> None:
    """Create new SQLite tables for comparison summaries if they do not exist."""
    # 1. Training Performance Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dqn_performance_training (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            epoch INTEGER NOT NULL,
            loss REAL NOT NULL,
            avg_reward REAL NOT NULL,
            avg_q_value REAL NOT NULL,
            timestamp REAL NOT NULL
        )
    """)

    # 2. Hyperparameter Tuning Comparison Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dqn_performance_tuning (
            trial_id TEXT PRIMARY KEY,
            learning_rate REAL NOT NULL,
            gamma REAL NOT NULL,
            hidden_size INTEGER NOT NULL,
            avg_reward REAL NOT NULL,
            avg_loss REAL NOT NULL,
            rank INTEGER NOT NULL,
            timestamp REAL NOT NULL
        )
    """)

    # 3. Experiment Comparison Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dqn_performance_experiments (
            experiment_id TEXT PRIMARY KEY,
            learning_rate REAL NOT NULL,
            gamma REAL NOT NULL,
            hidden_size INTEGER NOT NULL,
            epochs INTEGER NOT NULL,
            avg_reward REAL NOT NULL,
            avg_loss REAL NOT NULL,
            is_best INTEGER NOT NULL,
            timestamp REAL NOT NULL
        )
    """)

    # 4. Simulation Comparison Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dqn_performance_simulations (
            simulation_run_id TEXT PRIMARY KEY,
            avg_waiting_time REAL NOT NULL,
            avg_queue_length REAL NOT NULL,
            throughput INTEGER NOT NULL,
            avg_reward REAL NOT NULL,
            is_best INTEGER NOT NULL,
            timestamp REAL NOT NULL
        )
    """)

    # 5. Overall Project Summary Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dqn_performance_overall_summary (
            metric_name TEXT PRIMARY KEY,
            metric_value TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    """)
    conn.commit()


def load_training_metrics(conn: Optional[sqlite3.Connection]) -> List[Dict[str, Any]]:
    """Load and merge training metrics from SQLite and summary.json."""
    db_metrics: List[Dict[str, Any]] = []
    if conn:
        try:
            cursor = conn.execute(
                """
                SELECT epoch, avg_loss, avg_q_value, avg_reward, timestamp
                FROM dqn_training_stats
                ORDER BY timestamp ASC, epoch ASC
                """
            )
            for row in cursor.fetchall():
                db_metrics.append({
                    "epoch": row[0],
                    "avg_loss": round(row[1], 4),
                    "avg_q_value": round(row[2], 4),
                    "avg_reward": round(row[3], 4),
                    "timestamp": row[4]
                })
        except sqlite3.OperationalError as exc:
            logger.warning(f"Failed to read dqn_training_stats from DB: {exc}")

    json_metrics: List[Dict[str, Any]] = []
    if SUMMARY_JSON_PATH.exists():
        try:
            with open(SUMMARY_JSON_PATH, "r") as f:
                data = json.load(f)
                metrics_list = data.get("training_metrics", [])
                for item in metrics_list:
                    json_metrics.append({
                        "epoch": item.get("epoch"),
                        "avg_loss": round(item.get("avg_loss", 0.0), 4),
                        "avg_q_value": round(item.get("avg_q_value", 0.0), 4),
                        "avg_reward": round(item.get("avg_reward", 0.0), 4),
                        "timestamp": item.get("timestamp", time.time())
                    })
        except Exception as exc:
            logger.warning(f"Failed to read training metrics from summary.json: {exc}")

    # Merge based on (epoch, avg_loss, avg_reward)
    merged: Dict[Tuple[int, float, float], Dict[str, Any]] = {}
    for m in db_metrics:
        key = (m["epoch"], m["avg_loss"], m["avg_reward"])
        merged[key] = m
    for m in json_metrics:
        key = (m["epoch"], m["avg_loss"], m["avg_reward"])
        if key not in merged:
            merged[key] = m

    return sorted(merged.values(), key=lambda x: (x.get("timestamp") or 0, x["epoch"]))


def load_tuning_results(conn: Optional[sqlite3.Connection]) -> List[Dict[str, Any]]:
    """Load and merge tuning results from SQLite, tuning_results.json, and summary.json."""
    db_tuning: List[Dict[str, Any]] = []
    if conn:
        try:
            cursor = conn.execute(
                """
                SELECT run_id, learning_rate, gamma, hidden_size, epochs, avg_loss, avg_q_value, avg_reward, timestamp
                FROM dqn_tuning_runs
                """
            )
            for row in cursor.fetchall():
                db_tuning.append({
                    "run_id": row[0],
                    "learning_rate": row[1],
                    "gamma": row[2],
                    "hidden_size": row[3],
                    "epochs": row[4],
                    "avg_loss": round(row[5], 4),
                    "avg_q_value": round(row[6], 4),
                    "avg_reward": round(row[7], 4),
                    "timestamp": row[8]
                })
        except sqlite3.OperationalError as exc:
            logger.warning(f"Failed to read dqn_tuning_runs from DB: {exc}")

    json_tuning: List[Dict[str, Any]] = []
    # Read from tuning_results.json
    if TUNING_JSON_PATH.exists():
        try:
            with open(TUNING_JSON_PATH, "r") as f:
                data = json.load(f)
                for item in data:
                    run_id = item.get("run_id")
                    if run_id:
                        json_tuning.append({
                            "run_id": run_id,
                            "learning_rate": item.get("learning_rate"),
                            "gamma": item.get("gamma"),
                            "hidden_size": item.get("hidden_size"),
                            "epochs": item.get("epochs", 1),
                            "avg_loss": round(item.get("avg_loss", 0.0), 4),
                            "avg_q_value": round(item.get("avg_q_value", 0.0), 4),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "timestamp": item.get("timestamp", time.time())
                        })
        except Exception as exc:
            logger.warning(f"Failed to read tuning results from tuning_results.json: {exc}")

    # Read from summary.json -> tuning_results
    if SUMMARY_JSON_PATH.exists():
        try:
            with open(SUMMARY_JSON_PATH, "r") as f:
                data = json.load(f)
                metrics_list = data.get("tuning_results", [])
                for item in metrics_list:
                    run_id = item.get("run_id")
                    if run_id:
                        json_tuning.append({
                            "run_id": run_id,
                            "learning_rate": item.get("learning_rate"),
                            "gamma": item.get("gamma"),
                            "hidden_size": item.get("hidden_size"),
                            "epochs": item.get("epochs", 1),
                            "avg_loss": round(item.get("avg_loss", 0.0), 4),
                            "avg_q_value": round(item.get("avg_q_value", 0.0), 4),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "timestamp": item.get("timestamp", time.time())
                        })
        except Exception as exc:
            logger.warning(f"Failed to read tuning results from summary.json: {exc}")

    merged: Dict[str, Dict[str, Any]] = {}
    for t in db_tuning:
        merged[t["run_id"]] = t
    for t in json_tuning:
        merged[t["run_id"]] = t

    return list(merged.values())


def load_experiment_results(conn: Optional[sqlite3.Connection]) -> List[Dict[str, Any]]:
    """Load and merge experiment results from SQLite, experiments/summary.json, and summary.json."""
    db_experiments: List[Dict[str, Any]] = []
    if conn:
        try:
            cursor = conn.execute(
                """
                SELECT experiment_id, timestamp, learning_rate, gamma, hidden_size, epochs, avg_reward, avg_loss
                FROM dqn_experiments
                """
            )
            for row in cursor.fetchall():
                db_experiments.append({
                    "experiment_id": row[0],
                    "timestamp": row[1],
                    "learning_rate": row[2],
                    "gamma": row[3],
                    "hidden_size": row[4],
                    "epochs": row[5],
                    "avg_reward": round(row[6], 4),
                    "avg_loss": round(row[7], 4)
                })
        except sqlite3.OperationalError as exc:
            logger.warning(f"Failed to read dqn_experiments from DB: {exc}")

    json_experiments: List[Dict[str, Any]] = []
    # Read from experiments/summary.json
    if EXPERIMENTS_JSON_PATH.exists():
        try:
            with open(EXPERIMENTS_JSON_PATH, "r") as f:
                data = json.load(f)
                for item in data:
                    exp_id = item.get("experiment_id")
                    if exp_id:
                        json_experiments.append({
                            "experiment_id": exp_id,
                            "timestamp": item.get("timestamp", time.time()),
                            "learning_rate": item.get("learning_rate"),
                            "gamma": item.get("gamma"),
                            "hidden_size": item.get("hidden_size"),
                            "epochs": item.get("epochs"),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "avg_loss": round(item.get("avg_loss", 0.0), 4)
                        })
        except Exception as exc:
            logger.warning(f"Failed to read experiments/summary.json: {exc}")

    # Read from summary.json -> experiment_results
    if SUMMARY_JSON_PATH.exists():
        try:
            with open(SUMMARY_JSON_PATH, "r") as f:
                data = json.load(f)
                metrics_list = data.get("experiment_results", [])
                for item in metrics_list:
                    exp_id = item.get("experiment_id")
                    if exp_id:
                        json_experiments.append({
                            "experiment_id": exp_id,
                            "timestamp": item.get("timestamp", time.time()),
                            "learning_rate": item.get("learning_rate"),
                            "gamma": item.get("gamma"),
                            "hidden_size": item.get("hidden_size"),
                            "epochs": item.get("epochs"),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "avg_loss": round(item.get("avg_loss", 0.0), 4)
                        })
        except Exception as exc:
            logger.warning(f"Failed to read experiment results from summary.json: {exc}")

    merged: Dict[str, Dict[str, Any]] = {}
    for e in db_experiments:
        merged[e["experiment_id"]] = e
    for e in json_experiments:
        merged[e["experiment_id"]] = e

    return list(merged.values())


def load_simulation_results(conn: Optional[sqlite3.Connection]) -> List[Dict[str, Any]]:
    """Load and merge simulation runs from SQLite, simulations/summary.json, and summary.json."""
    db_sims: List[Dict[str, Any]] = []
    if conn:
        try:
            cursor = conn.execute(
                """
                SELECT run_id, avg_waiting_time, avg_queue_length, throughput, avg_reward, timestamp
                FROM sumo_simulation_runs
                """
            )
            for row in cursor.fetchall():
                db_sims.append({
                    "run_id": row[0],
                    "avg_waiting_time": round(row[1], 4),
                    "avg_queue_length": round(row[2], 4),
                    "throughput": row[3],
                    "avg_reward": round(row[4], 4),
                    "timestamp": row[5]
                })
        except sqlite3.OperationalError as exc:
            logger.warning(f"Failed to read sumo_simulation_runs from DB: {exc}")

    json_sims: List[Dict[str, Any]] = []
    # Read from simulations/summary.json
    if SIMULATIONS_JSON_PATH.exists():
        try:
            with open(SIMULATIONS_JSON_PATH, "r") as f:
                data = json.load(f)
                for item in data:
                    run_id = item.get("run_id")
                    if run_id:
                        json_sims.append({
                            "run_id": run_id,
                            "avg_waiting_time": round(item.get("avg_waiting_time", 0.0), 4),
                            "avg_queue_length": round(item.get("avg_queue_length", 0.0), 4),
                            "throughput": item.get("throughput", 0),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "timestamp": item.get("timestamp", time.time())
                        })
        except Exception as exc:
            logger.warning(f"Failed to read simulations/summary.json: {exc}")

    # Read from summary.json -> simulation_results
    if SUMMARY_JSON_PATH.exists():
        try:
            with open(SUMMARY_JSON_PATH, "r") as f:
                data = json.load(f)
                metrics_list = data.get("simulation_results", [])
                for item in metrics_list:
                    run_id = item.get("run_id")
                    if run_id:
                        json_sims.append({
                            "run_id": run_id,
                            "avg_waiting_time": round(item.get("avg_waiting_time", 0.0), 4),
                            "avg_queue_length": round(item.get("avg_queue_length", 0.0), 4),
                            "throughput": item.get("throughput", 0),
                            "avg_reward": round(item.get("avg_reward", 0.0), 4),
                            "timestamp": item.get("timestamp", time.time())
                        })
        except Exception as exc:
            logger.warning(f"Failed to read simulation results from summary.json: {exc}")

    merged: Dict[str, Dict[str, Any]] = {}
    for s in db_sims:
        merged[s["run_id"]] = s
    for s in json_sims:
        merged[s["run_id"]] = s

    return list(merged.values())


def print_table(title: str, headers: List[str], rows: List[List[Any]]) -> None:
    """Print standard ASCII boxed tables in terminal."""
    print(f"\n>>> {title}")
    if not rows:
        print("No data available.")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    # Print top border
    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(border)

    # Print header line
    header_line = "|" + "|".join(f" {h:<{widths[i]}} " for i, h in enumerate(headers)) + "|"
    print(header_line)
    print(border)

    # Print rows
    for row in rows:
        row_line = "|" + "|".join(f" {str(val):<{widths[i]}} " for i, val in enumerate(row)) + "|"
        print(row_line)

    # Print bottom border
    print(border)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate IntelliRoads Performance Comparison Tables.")
    parser.add_argument("--db-path", type=str, default=str(DB_PATH), help="Path to SQLite database")
    args = parser.parse_args()

    db_file_path = Path(args.db_path)
    logger.info(f"Loading and processing metrics with database path: {db_file_path}")

    conn: Optional[sqlite3.Connection] = None
    if db_file_path.exists():
        conn = sqlite3.connect(str(db_file_path))
    else:
        logger.warning(f"Database file not found at {db_file_path}. Using fallback JSON files only.")

    try:
        # 1. Load Data
        training = load_training_metrics(conn)
        tuning = load_tuning_results(conn)
        experiments = load_experiment_results(conn)
        simulations = load_simulation_results(conn)

        logger.info(f"Collected raw counts: {len(training)} training epochs, {len(tuning)} tuning trials, {len(experiments)} experiments, {len(simulations)} simulations.")

        # 2. Process Tables

        # Training Performance Table (chronological order)
        training_table: List[Dict[str, Any]] = []
        for item in training:
            training_table.append({
                "epoch": item["epoch"],
                "loss": item["avg_loss"],
                "avg_reward": item["avg_reward"],
                "avg_q_value": item["avg_q_value"],
                "timestamp": item.get("timestamp", time.time())
            })

        # Hyperparameter Tuning Comparison (Rank best to worst: highest average reward first)
        tuning_sorted = sorted(tuning, key=lambda x: (x["avg_reward"], -x["avg_loss"]), reverse=True)
        tuning_table: List[Dict[str, Any]] = []
        for idx, item in enumerate(tuning_sorted):
            tuning_table.append({
                "rank": idx + 1,
                "trial_id": item["run_id"],
                "learning_rate": item["learning_rate"],
                "gamma": item["gamma"],
                "hidden_size": item["hidden_size"],
                "avg_reward": item["avg_reward"],
                "avg_loss": item["avg_loss"],
                "timestamp": item.get("timestamp", time.time())
            })

        # Experiment Comparison (Highlight best experiment by avg_reward)
        best_exp_id = "None"
        best_exp_reward = -float("inf")
        for exp in experiments:
            if exp["avg_reward"] > best_exp_reward:
                best_exp_reward = exp["avg_reward"]
                best_exp_id = exp["experiment_id"]

        experiment_table: List[Dict[str, Any]] = []
        for exp in sorted(experiments, key=lambda x: x.get("timestamp", 0)):
            experiment_table.append({
                "experiment_id": exp["experiment_id"],
                "learning_rate": exp["learning_rate"],
                "gamma": exp["gamma"],
                "hidden_size": exp["hidden_size"],
                "epochs": exp["epochs"],
                "avg_reward": exp["avg_reward"],
                "avg_loss": exp["avg_loss"],
                "is_best": 1 if exp["experiment_id"] == best_exp_id else 0,
                "timestamp": exp.get("timestamp", time.time())
            })

        # Simulation Comparison (Highlight best simulation by avg_reward)
        best_sim_id = "None"
        best_sim_reward = -float("inf")
        for sim in simulations:
            if sim["avg_reward"] > best_sim_reward:
                best_sim_reward = sim["avg_reward"]
                best_sim_id = sim["run_id"]

        simulation_table: List[Dict[str, Any]] = []
        for sim in sorted(simulations, key=lambda x: x.get("timestamp", 0)):
            simulation_table.append({
                "simulation_run_id": sim["run_id"],
                "avg_waiting_time": sim["avg_waiting_time"],
                "avg_queue_length": sim["avg_queue_length"],
                "throughput": sim["throughput"],
                "avg_reward": sim["avg_reward"],
                "is_best": 1 if sim["run_id"] == best_sim_id else 0,
                "timestamp": sim.get("timestamp", time.time())
            })

        # Compute Overall Summary
        total_training_epochs = len(training_table)
        total_tuning_trials = len(tuning_table)
        total_experiments = len(experiment_table)
        total_simulations = len(simulation_table)

        # Best Average Reward (Global search)
        best_reward_val = -float("inf")
        best_reward_src = "None"
        best_reward_id = "None"

        for tr in training_table:
            if tr["avg_reward"] > best_reward_val:
                best_reward_val = tr["avg_reward"]
                best_reward_src = "training"
                best_reward_id = f"epoch_{tr['epoch']}"
        for tu in tuning_table:
            if tu["avg_reward"] > best_reward_val:
                best_reward_val = tu["avg_reward"]
                best_reward_src = "tuning"
                best_reward_id = tu["trial_id"]
        for ex in experiment_table:
            if ex["avg_reward"] > best_reward_val:
                best_reward_val = ex["avg_reward"]
                best_reward_src = "experiments"
                best_reward_id = ex["experiment_id"]
        for si in simulation_table:
            if si["avg_reward"] > best_reward_val:
                best_reward_val = si["avg_reward"]
                best_reward_src = "simulations"
                best_reward_id = si["simulation_run_id"]

        # Lowest Loss (Global search)
        lowest_loss_val = float("inf")
        lowest_loss_src = "None"
        lowest_loss_id = "None"

        for tr in training_table:
            if tr["loss"] < lowest_loss_val:
                lowest_loss_val = tr["loss"]
                lowest_loss_src = "training"
                lowest_loss_id = f"epoch_{tr['epoch']}"
        for tu in tuning_table:
            if tu["avg_loss"] < lowest_loss_val:
                lowest_loss_val = tu["avg_loss"]
                lowest_loss_src = "tuning"
                lowest_loss_id = tu["trial_id"]
        for ex in experiment_table:
            if ex["avg_loss"] < lowest_loss_val:
                lowest_loss_val = ex["avg_loss"]
                lowest_loss_src = "experiments"
                lowest_loss_id = ex["experiment_id"]

        # Best Hyperparameter Configuration
        best_lr, best_gamma, best_hidden = "None", "None", "None"
        best_config_reward = -float("inf")
        for tu in tuning_table:
            if tu["avg_reward"] > best_config_reward:
                best_config_reward = tu["avg_reward"]
                best_lr = tu["learning_rate"]
                best_gamma = tu["gamma"]
                best_hidden = tu["hidden_size"]
        for ex in experiment_table:
            if ex["avg_reward"] > best_config_reward:
                best_config_reward = ex["avg_reward"]
                best_lr = ex["learning_rate"]
                best_gamma = ex["gamma"]
                best_hidden = ex["hidden_size"]

        best_hyperparameter_config = f"LR: {best_lr}, Gamma: {best_gamma}, Hidden Size: {best_hidden}"

        # Best Experiment Info
        best_experiment_info = "None"
        for ex in experiment_table:
            if ex["is_best"] == 1:
                best_experiment_info = f"{ex['experiment_id']} (Reward: {ex['avg_reward']:.4f})"
                break

        # Best Simulation Info
        best_simulation_info = "None"
        for si in simulation_table:
            if si["is_best"] == 1:
                best_simulation_info = f"{si['simulation_run_id']} (Reward: {si['avg_reward']:.4f})"
                break

        # Averages across all simulations
        avg_throughput = sum(si["throughput"] for si in simulation_table) / total_simulations if total_simulations else 0.0
        avg_waiting_time = sum(si["avg_waiting_time"] for si in simulation_table) / total_simulations if total_simulations else 0.0
        avg_queue_length = sum(si["avg_queue_length"] for si in simulation_table) / total_simulations if total_simulations else 0.0

        overall_summary = {
            "total_training_epochs": total_training_epochs,
            "total_tuning_trials": total_tuning_trials,
            "total_experiments": total_experiments,
            "total_simulations": total_simulations,
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
            "best_hyperparameter_configuration": best_hyperparameter_config,
            "best_experiment": best_experiment_info,
            "best_simulation": best_simulation_info,
            "average_throughput": round(avg_throughput, 2),
            "average_waiting_time": round(avg_waiting_time, 4),
            "average_queue_length": round(avg_queue_length, 4)
        }

        # 3. Print Terminal Tables
        print("\n" + "=" * 80)
        print("               INTELLIROADS PERFORMANCE COMPARISON REPORT")
        print("=" * 80)

        # Table 1: Training Performance
        training_headers = ["Epoch", "Loss", "Average Reward", "Average Q Value"]
        training_rows = [[tr["epoch"], f"{tr['loss']:.4f}", f"{tr['avg_reward']:.4f}", f"{tr['avg_q_value']:.4f}"] for tr in training_table]
        print_table("Training Performance Table", training_headers, training_rows)

        # Table 2: Hyperparameter Tuning Comparison
        tuning_headers = ["Rank", "Trial ID", "Learning Rate", "Gamma", "Hidden Size", "Average Reward", "Average Loss"]
        tuning_rows = [[
            tu["rank"],
            tu["trial_id"],
            tu["learning_rate"],
            tu["gamma"],
            tu["hidden_size"],
            f"{tu['avg_reward']:.4f}",
            f"{tu['avg_loss']:.4f}"
        ] for tu in tuning_table]
        print_table("Hyperparameter Tuning Comparison (Best to Worst)", tuning_headers, tuning_rows)

        # Table 3: Experiment Comparison
        experiment_headers = ["Experiment ID", "Learning Rate", "Gamma", "Hidden Size", "Epochs", "Average Reward", "Average Loss"]
        experiment_rows = []
        for ex in experiment_table:
            exp_id_str = f"{ex['experiment_id']} * (Best)" if ex["is_best"] == 1 else ex["experiment_id"]
            experiment_rows.append([
                exp_id_str,
                ex["learning_rate"],
                ex["gamma"],
                ex["hidden_size"],
                ex["epochs"],
                f"{ex['avg_reward']:.4f}",
                f"{ex['avg_loss']:.4f}"
            ])
        print_table("Experiment Comparison", experiment_headers, experiment_rows)

        # Table 4: Simulation Comparison
        simulation_headers = ["Simulation Run ID", "Average Waiting Time", "Average Queue Length", "Throughput", "Average Reward"]
        simulation_rows = []
        for si in simulation_table:
            sim_id_str = f"{si['simulation_run_id']} * (Best)" if si["is_best"] == 1 else si["simulation_run_id"]
            simulation_rows.append([
                sim_id_str,
                f"{si['avg_waiting_time']:.4f}",
                f"{si['avg_queue_length']:.4f}",
                si["throughput"],
                f"{si['avg_reward']:.4f}"
            ])
        print_table("Simulation Comparison", simulation_headers, simulation_rows)

        # Table 5: Overall Project Summary
        summary_headers = ["Metric Name", "Metric Value"]
        summary_rows = [
            ["Total Training Epochs", total_training_epochs],
            ["Total Tuning Trials", total_tuning_trials],
            ["Total Experiments", total_experiments],
            ["Total Simulations", total_simulations],
            ["Best Average Reward", f"{overall_summary['best_average_reward']['value']} ({overall_summary['best_average_reward']['source']}: {overall_summary['best_average_reward']['id']})"],
            ["Lowest Loss", f"{overall_summary['lowest_loss']['value']} ({overall_summary['lowest_loss']['source']}: {overall_summary['lowest_loss']['id']})"],
            ["Best Hyperparameter Configuration", overall_summary["best_hyperparameter_configuration"]],
            ["Best Experiment", overall_summary["best_experiment"]],
            ["Best Simulation", overall_summary["best_simulation"]],
            ["Average Throughput", f"{overall_summary['average_throughput']:.2f}"],
            ["Average Waiting Time", f"{overall_summary['average_waiting_time']:.4f}"],
            ["Average Queue Length", f"{overall_summary['average_queue_length']:.4f}"]
        ]
        print_table("Overall Project Summary", summary_headers, summary_rows)

        # 4. Write JSON
        output_data = {
            "training_performance": training_table,
            "hyperparameter_tuning": tuning_table,
            "experiment_comparison": experiment_table,
            "simulation_comparison": simulation_table,
            "overall_project_summary": overall_summary
        }
        OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Successfully generated JSON: {OUTPUT_JSON_PATH}")

        # 5. Write CSV (separated by section headers)
        with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Section 1
            writer.writerow(["1. Training Performance Table"])
            writer.writerow(training_headers)
            for row in training_rows:
                writer.writerow(row)
            writer.writerow([])

            # Section 2
            writer.writerow(["2. Hyperparameter Tuning Comparison (Best to Worst)"])
            writer.writerow(tuning_headers)
            for row in tuning_rows:
                writer.writerow(row)
            writer.writerow([])

            # Section 3
            writer.writerow(["3. Experiment Comparison"])
            writer.writerow(experiment_headers)
            for row in experiment_rows:
                writer.writerow(row)
            writer.writerow([])

            # Section 4
            writer.writerow(["4. Simulation Comparison"])
            writer.writerow(simulation_headers)
            for row in simulation_rows:
                writer.writerow(row)
            writer.writerow([])

            # Section 5
            writer.writerow(["5. Overall Project Summary"])
            writer.writerow(summary_headers)
            for row in summary_rows:
                writer.writerow(row)

        logger.info(f"Successfully generated CSV: {OUTPUT_CSV_PATH}")

        # 6. Save/update SQLite tables
        # Re-establish connection to DB if it existed or we create a new one
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        db_conn = sqlite3.connect(str(db_file_path))
        try:
            setup_db_tables(db_conn)

            # Clear old performance summaries
            db_conn.execute("DELETE FROM dqn_performance_training")
            db_conn.execute("DELETE FROM dqn_performance_tuning")
            db_conn.execute("DELETE FROM dqn_performance_experiments")
            db_conn.execute("DELETE FROM dqn_performance_simulations")
            db_conn.execute("DELETE FROM dqn_performance_overall_summary")
            db_conn.commit()

            # Insert training performance
            current_time = time.time()
            db_conn.executemany(
                """
                INSERT INTO dqn_performance_training (epoch, loss, avg_reward, avg_q_value, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(t["epoch"], t["loss"], t["avg_reward"], t["avg_q_value"], t["timestamp"]) for t in training_table]
            )

            # Insert hyperparameter tuning
            db_conn.executemany(
                """
                INSERT INTO dqn_performance_tuning (trial_id, learning_rate, gamma, hidden_size, avg_reward, avg_loss, rank, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(t["trial_id"], t["learning_rate"], t["gamma"], t["hidden_size"], t["avg_reward"], t["avg_loss"], t["rank"], t["timestamp"]) for t in tuning_table]
            )

            # Insert experiments
            db_conn.executemany(
                """
                INSERT INTO dqn_performance_experiments (experiment_id, learning_rate, gamma, hidden_size, epochs, avg_reward, avg_loss, is_best, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(e["experiment_id"], e["learning_rate"], e["gamma"], e["hidden_size"], e["epochs"], e["avg_reward"], e["avg_loss"], e["is_best"], e["timestamp"]) for e in experiment_table]
            )

            # Insert simulations
            db_conn.executemany(
                """
                INSERT INTO dqn_performance_simulations (simulation_run_id, avg_waiting_time, avg_queue_length, throughput, avg_reward, is_best, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(s["simulation_run_id"], s["avg_waiting_time"], s["avg_queue_length"], s["throughput"], s["avg_reward"], s["is_best"], s["timestamp"]) for s in simulation_table]
            )

            # Insert overall project summary
            # We convert everything to strings to keep metric_value consistent
            summary_db_rows = []
            for item in summary_rows:
                summary_db_rows.append((item[0], str(item[1]), current_time))

            db_conn.executemany(
                """
                INSERT INTO dqn_performance_overall_summary (metric_name, metric_value, timestamp)
                VALUES (?, ?, ?)
                """,
                summary_db_rows
            )

            db_conn.commit()
            logger.info("SQLite database performance comparison tables updated successfully.")

        finally:
            db_conn.close()

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
