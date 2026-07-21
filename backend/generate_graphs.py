"""
IntelliRoads – Graph Generation (Sprint 2 - Feature 6).

Generates 8 diagnostic and comparison graphs from summary data and database records,
saving them as PNG files under backend/data/graphs/.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

# Set backend directory and paths
BACKEND_DIR = Path(__file__).resolve().parent
DB_PATH = BACKEND_DIR / "data" / "intelliroads.db"
SUMMARY_JSON_PATH = BACKEND_DIR / "data" / "summary.json"
GRAPHS_DIR = BACKEND_DIR / "data" / "graphs"


def load_data(db_path: Path, summary_path: Path) -> Dict[str, Any]:
    """
    Loads data from summary.json if available.
    Otherwise, attempts to fetch from the SQLite database.
    """
    data = {
        "training_metrics": [],
        "tuning_results": [],
        "experiment_results": [],
        "simulation_results": []
    }

    # Try loading from summary.json first
    if summary_path.exists():
        try:
            print(f"Loading data from summary JSON: {summary_path}")
            with open(summary_path, "r") as f:
                loaded = json.load(f)
                for key in data:
                    if key in loaded:
                        data[key] = loaded[key]
            return data
        except Exception as exc:
            print(f"[Warning] Failed to load {summary_path}: {exc}. Falling back to SQLite.")

    # Fallback to database
    if db_path.exists():
        print(f"Loading data from SQLite database: {db_path}")
        conn = sqlite3.connect(str(db_path))
        try:
            # 1. Training metrics
            try:
                cursor = conn.execute(
                    "SELECT epoch, avg_loss, avg_q_value, avg_reward, epsilon, buffer_size, timestamp FROM dqn_training_stats ORDER BY timestamp ASC, epoch ASC"
                )
                for row in cursor.fetchall():
                    data["training_metrics"].append({
                        "epoch": row[0], "avg_loss": row[1], "avg_q_value": row[2], "avg_reward": row[3],
                        "epsilon": row[4], "buffer_size": row[5], "timestamp": row[6]
                    })
            except Exception as exc:
                print(f"[Warning] Failed to query dqn_training_stats: {exc}")

            # 2. Tuning results
            try:
                cursor = conn.execute(
                    "SELECT run_id, learning_rate, gamma, hidden_size, epochs, avg_loss, avg_q_value, avg_reward, timestamp FROM dqn_tuning_runs"
                )
                for row in cursor.fetchall():
                    data["tuning_results"].append({
                        "run_id": row[0], "learning_rate": row[1], "gamma": row[2], "hidden_size": row[3],
                        "epochs": row[4], "avg_loss": row[5], "avg_q_value": row[6], "avg_reward": row[7],
                        "timestamp": row[8]
                    })
            except Exception as exc:
                print(f"[Warning] Failed to query dqn_tuning_runs: {exc}")

            # 3. Experiment results
            try:
                cursor = conn.execute(
                    "SELECT experiment_id, timestamp, learning_rate, gamma, hidden_size, epochs, avg_reward, avg_loss, model_path FROM dqn_experiments"
                )
                for row in cursor.fetchall():
                    data["experiment_results"].append({
                        "experiment_id": row[0], "timestamp": row[1], "learning_rate": row[2], "gamma": row[3],
                        "hidden_size": row[4], "epochs": row[5], "avg_reward": row[6], "avg_loss": row[7],
                        "model_path": row[8]
                    })
            except Exception as exc:
                print(f"[Warning] Failed to query dqn_experiments: {exc}")

            # 4. Simulation results
            try:
                cursor = conn.execute(
                    "SELECT run_id, start_time, end_time, duration, avg_waiting_time, avg_queue_length, throughput, avg_reward, timestamp FROM sumo_simulation_runs"
                )
                for row in cursor.fetchall():
                    data["simulation_results"].append({
                        "run_id": row[0], "start_time": row[1], "end_time": row[2], "duration": row[3],
                        "avg_waiting_time": row[4], "avg_queue_length": row[5], "throughput": row[6],
                        "avg_reward": row[7], "timestamp": row[8]
                    })
            except Exception as exc:
                print(f"[Warning] Failed to query sumo_simulation_runs: {exc}")

        finally:
            conn.close()
    else:
        print(f"[Error] No database found at {db_path} and no summary JSON found at {summary_path}.")
        sys.exit(1)

    return data


def generate_plots(data: Dict[str, Any], graphs_dir: Path) -> List[str]:
    """Generates all 8 required graphs and saves them to graphs_dir as PNGs."""
    import matplotlib.pyplot as plt
    import numpy as np

    graphs_dir.mkdir(parents=True, exist_ok=True)
    generated_files = []

    # Common style setups
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['axes.edgecolor'] = '#CCCCCC'
    plt.rcParams['axes.linewidth'] = 0.8

    training = data.get("training_metrics", [])
    tuning = data.get("tuning_results", [])
    experiments = data.get("experiment_results", [])
    simulations = data.get("simulation_results", [])

    # 1. Training Loss vs Epoch
    if training:
        epochs = [t["epoch"] for t in training]
        losses = [t["avg_loss"] for t in training]
        
        plt.figure(figsize=(8, 5))
        plt.plot(epochs, losses, marker='o', color='#d9534f', linewidth=2.0, markersize=6, label='Training Loss')
        plt.title('DQN Training Loss vs Epoch', fontsize=13, fontweight='bold', pad=15)
        plt.xlabel('Epoch', fontsize=11)
        plt.ylabel('Average Loss', fontsize=11)
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.legend(frameon=True, facecolor='white', edgecolor='none')
        
        # force integer x-axis ticks
        plt.xticks(epochs)
        
        out_path = graphs_dir / "training_loss_vs_epoch.png"
        plt.savefig(out_path, bbox_inches='tight', dpi=150)
        plt.close()
        generated_files.append(out_path.name)
        print(f"Generated: {out_path.name}")
    else:
        print("Skipping graph 1: No training metrics available.")

    # 2. Average Reward vs Epoch
    if training:
        epochs = [t["epoch"] for t in training]
        rewards = [t["avg_reward"] for t in training]
        
        plt.figure(figsize=(8, 5))
        plt.plot(epochs, rewards, marker='s', color='#5cb85c', linewidth=2.0, markersize=6, label='Average Reward')
        plt.title('DQN Training Average Reward vs Epoch', fontsize=13, fontweight='bold', pad=15)
        plt.xlabel('Epoch', fontsize=11)
        plt.ylabel('Average Reward', fontsize=11)
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.legend(frameon=True, facecolor='white', edgecolor='none')
        plt.xticks(epochs)
        
        out_path = graphs_dir / "average_reward_vs_epoch.png"
        plt.savefig(out_path, bbox_inches='tight', dpi=150)
        plt.close()
        generated_files.append(out_path.name)
        print(f"Generated: {out_path.name}")
    else:
        print("Skipping graph 2: No training metrics available.")

    # 3. Hyperparameter Tuning Comparison (Top 10 configurations)
    if tuning:
        # Sort by reward descending, take top 10
        top_tuning = sorted(tuning, key=lambda x: x.get("avg_reward", -9999.0), reverse=True)[:10]
        
        labels = []
        for t in top_tuning:
            # Short hyperparameter labels
            labels.append(f"LR:{t['learning_rate']}\nG:{t['gamma']}\nH:{t['hidden_size']}")
        rewards = [t["avg_reward"] for t in top_tuning]
        
        plt.figure(figsize=(10, 6))
        bars = plt.bar(range(len(rewards)), rewards, color='#0275d8', alpha=0.8, width=0.55, edgecolor='#01549C')
        
        # Add labels on top of bars
        for bar in bars:
            yval = bar.get_height()
            offset = 0.05 if yval >= 0 else -0.15
            va_align = 'bottom' if yval >= 0 else 'top'
            plt.text(bar.get_x() + bar.get_width()/2.0, yval + offset, f"{yval:.2f}", ha='center', va=va_align, fontsize=8.5, fontweight='bold')
            
        plt.title('Top 10 Hyperparameter Tuning Runs (by Avg Reward)', fontsize=13, fontweight='bold', pad=15)
        plt.xlabel('Configuration Parameters', fontsize=11)
        plt.ylabel('Average Reward', fontsize=11)
        plt.xticks(range(len(labels)), labels, fontsize=9)
        plt.grid(True, linestyle='--', alpha=0.4, axis='y')
        
        out_path = graphs_dir / "hyperparameter_tuning_comparison.png"
        plt.savefig(out_path, bbox_inches='tight', dpi=150)
        plt.close()
        generated_files.append(out_path.name)
        print(f"Generated: {out_path.name}")
    else:
        print("Skipping graph 3: No tuning metrics available.")

    # 4. Experiment Comparison (Grouped Bar chart)
    if experiments:
        exp_ids = [e["experiment_id"] for e in experiments]
        rewards = [e["avg_reward"] for e in experiments]
        losses = [e["avg_loss"] for e in experiments]
        
        x = np.arange(len(exp_ids))
        width = 0.35
        
        fig, ax1 = plt.subplots(figsize=(8, 5))
        
        color = '#5cb85c'
        ax1.set_xlabel('Experiment ID', fontsize=11)
        ax1.set_ylabel('Average Reward', color=color, fontsize=11)
        rects1 = ax1.bar(x - width/2, rewards, width, label='Avg Reward', color=color, alpha=0.75, edgecolor='#419641')
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.grid(True, linestyle='--', alpha=0.3)
        
        # Add labels to reward bars
        for rect in rects1:
            h = rect.get_height()
            va = 'bottom' if h >= 0 else 'top'
            offset = 0.05 if h >= 0 else -0.15
            ax1.text(rect.get_x() + rect.get_width()/2.0, h + offset, f"{h:.2f}", ha='center', va=va, fontsize=8.5, color='#333333', fontweight='bold')
            
        ax2 = ax1.twinx()  
        color = '#d9534f'
        ax2.set_ylabel('Average Loss', color=color, fontsize=11)
        rects2 = ax2.bar(x + width/2, losses, width, label='Avg Loss', color=color, alpha=0.75, edgecolor='#B83C3C')
        ax2.tick_params(axis='y', labelcolor=color)
        
        # Add labels to loss bars
        for rect in rects2:
            h = rect.get_height()
            va = 'bottom' if h >= 0 else 'top'
            offset = 0.05 if h >= 0 else -0.15
            ax2.text(rect.get_x() + rect.get_width()/2.0, h + offset, f"{h:.2f}", ha='center', va=va, fontsize=8.5, color='#333333', fontweight='bold')
            
        plt.title('DQN Evaluation Experiments: Reward & Loss Comparison', fontsize=13, fontweight='bold', pad=15)
        ax1.set_xticks(x)
        ax1.set_xticklabels(exp_ids, rotation=10, fontsize=9.5)
        
        # Combine legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', frameon=True, facecolor='white', edgecolor='none')
        
        fig.tight_layout()
        out_path = graphs_dir / "experiment_comparison.png"
        plt.savefig(out_path, bbox_inches='tight', dpi=150)
        plt.close()
        generated_files.append(out_path.name)
        print(f"Generated: {out_path.name}")
    else:
        print("Skipping graph 4: No experiment metrics available.")

    # Simulation plots setup
    if simulations:
        run_ids = [s["run_id"] for s in simulations]
        short_ids = [r[:15] + '...' if len(r) > 15 else r for r in run_ids]
        
        # 5. Simulation Comparison (Average Reward)
        rewards = [s["avg_reward"] for s in simulations]
        plt.figure(figsize=(9, 5))
        bars = plt.bar(short_ids, rewards, color='#f0ad4e', alpha=0.8, width=0.5, edgecolor='#D68910')
        
        for bar in bars:
            yval = bar.get_height()
            va = 'bottom' if yval >= 0 else 'top'
            offset = 0.05 if yval >= 0 else -0.2
            plt.text(bar.get_x() + bar.get_width()/2.0, yval + offset, f"{yval:.2f}", ha='center', va=va, fontsize=9, fontweight='bold')
            
        plt.title('Simulation Runs: Average Reward Comparison', fontsize=13, fontweight='bold', pad=15)
        plt.xlabel('Simulation Run ID', fontsize=11)
        plt.ylabel('Average Reward', fontsize=11)
        plt.xticks(rotation=15, fontsize=9)
        plt.grid(True, linestyle='--', alpha=0.4, axis='y')
        plt.tight_layout()
        out_path = graphs_dir / "simulation_comparison.png"
        plt.savefig(out_path, bbox_inches='tight', dpi=150)
        plt.close()
        generated_files.append(out_path.name)
        print(f"Generated: {out_path.name}")

        # 6. Throughput Comparison
        throughputs = [s["throughput"] for s in simulations]
        plt.figure(figsize=(9, 5))
        bars = plt.bar(short_ids, throughputs, color='#5bc0de', alpha=0.8, width=0.5, edgecolor='#3A94AD')
        
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, yval + 0.05, f"{int(yval)}", ha='center', va='bottom', fontsize=9, fontweight='bold')
            
        plt.title('Simulation Runs: Total Vehicle Throughput', fontsize=13, fontweight='bold', pad=15)
        plt.xlabel('Simulation Run ID', fontsize=11)
        plt.ylabel('Throughput (Vehicles)', fontsize=11)
        plt.xticks(rotation=15, fontsize=9)
        plt.grid(True, linestyle='--', alpha=0.4, axis='y')
        plt.tight_layout()
        out_path = graphs_dir / "throughput_comparison.png"
        plt.savefig(out_path, bbox_inches='tight', dpi=150)
        plt.close()
        generated_files.append(out_path.name)
        print(f"Generated: {out_path.name}")

        # 7. Waiting Time Comparison
        wait_times = [s["avg_waiting_time"] for s in simulations]
        plt.figure(figsize=(9, 5))
        bars = plt.bar(short_ids, wait_times, color='#d9534f', alpha=0.8, width=0.5, edgecolor='#B83C3C')
        
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, yval + 0.02, f"{yval:.2f}s", ha='center', va='bottom', fontsize=9, fontweight='bold')
            
        plt.title('Simulation Runs: Average Waiting Time Comparison', fontsize=13, fontweight='bold', pad=15)
        plt.xlabel('Simulation Run ID', fontsize=11)
        plt.ylabel('Average Waiting Time (seconds)', fontsize=11)
        plt.xticks(rotation=15, fontsize=9)
        plt.grid(True, linestyle='--', alpha=0.4, axis='y')
        plt.tight_layout()
        out_path = graphs_dir / "waiting_time_comparison.png"
        plt.savefig(out_path, bbox_inches='tight', dpi=150)
        plt.close()
        generated_files.append(out_path.name)
        print(f"Generated: {out_path.name}")

        # 8. Queue Length Comparison
        queues = [s["avg_queue_length"] for s in simulations]
        plt.figure(figsize=(9, 5))
        bars = plt.bar(short_ids, queues, color='#373a3c', alpha=0.8, width=0.5, edgecolor='#252729')
        
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, yval + 0.01, f"{yval:.3f}", ha='center', va='bottom', fontsize=9, fontweight='bold')
            
        plt.title('Simulation Runs: Average Queue Length Comparison', fontsize=13, fontweight='bold', pad=15)
        plt.xlabel('Simulation Run ID', fontsize=11)
        plt.ylabel('Average Queue Length (Vehicles)', fontsize=11)
        plt.xticks(rotation=15, fontsize=9)
        plt.grid(True, linestyle='--', alpha=0.4, axis='y')
        plt.tight_layout()
        out_path = graphs_dir / "queue_length_comparison.png"
        plt.savefig(out_path, bbox_inches='tight', dpi=150)
        plt.close()
        generated_files.append(out_path.name)
        print(f"Generated: {out_path.name}")

    else:
        print("Skipping simulation graphs (5, 6, 7, 8): No simulation metrics available.")

    return generated_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate diagnostics and comparison graphs.")
    parser.add_argument("--db-path", type=str, default=str(DB_PATH), help="Path to SQLite database")
    parser.add_argument("--summary-json", type=str, default=str(SUMMARY_JSON_PATH), help="Path to summary.json")
    parser.add_argument("--out-dir", type=str, default=str(GRAPHS_DIR), help="Output folder to save PNGs")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    summary_path = Path(args.summary_json)
    out_dir = Path(args.out_dir)

    # 1. Load data
    data = load_data(db_path, summary_path)

    # 2. Generate plots
    print(f"\nGenerating charts and saving to: {out_dir}")
    generated = generate_plots(data, out_dir)

    print(f"\nGraph Generation Complete! Total graphs generated: {len(generated)}/8")
    for f in generated:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
