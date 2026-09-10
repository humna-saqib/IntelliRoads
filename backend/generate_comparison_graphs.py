"""
IntelliRoads - Controller Comparison Graph Generator
=====================================================
Reads evaluation_results/eval_summary.csv and generates high-resolution
bar charts comparing Fixed-Time, Rule-Based, and Trained DQN controllers.

Outputs saved to comparison_graphs/ directory:
- waiting_time_comparison.png
- travel_time_comparison.png
- queue_length_comparison.png
- throughput_comparison.png
- reward_comparison.png
- overall_benchmark_comparison.png
"""

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_BACKEND_DIR = Path(__file__).resolve().parent
EVAL_SUMMARY_CSV = _BACKEND_DIR / "evaluation_results" / "eval_summary.csv"
OUTPUT_DIR = _BACKEND_DIR / "comparison_graphs"


def load_summary_data(csv_path: Path):
    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)

    controllers = []
    waiting_times = []
    travel_times = []
    queue_lengths = []
    throughputs = []
    rewards = []

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ctrl = row["controller"]
            controllers.append(ctrl)
            waiting_times.append(float(row["avg_waiting_time_mean"]))
            travel_times.append(float(row["avg_travel_time_mean"]))
            queue_lengths.append(float(row["avg_queue_length_mean"]))
            throughputs.append(float(row["throughput_mean"]))
            rewards.append(float(row["episode_reward_mean"]))

    return {
        "controllers": controllers,
        "waiting_time": waiting_times,
        "travel_time": travel_times,
        "queue_length": queue_lengths,
        "throughput": throughputs,
        "reward": rewards,
    }


def set_chart_style():
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#CCCCCC"
    plt.rcParams["axes.linewidth"] = 0.8


def plot_single_metric(controllers, values, title, ylabel, filename, colors, fmt="{:.2f}", is_reward=False):
    fig, ax = plt.subplots(figsize=(8, 5.5))
    bars = ax.bar(controllers, values, color=colors, width=0.45, edgecolor="#333333", linewidth=1.0, alpha=0.9)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel(ylabel, fontsize=11, fontweight="bold")
    ax.set_xlabel("Signal Controller", fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.4, axis="y")

    # Dynamic y-axis padding
    min_val, max_val = min(values), max(values)
    if is_reward:
        ax.axhline(0, color="#666666", linewidth=1.0, linestyle="-")
        y_margin = (max_val - min_val) * 0.15
        ax.set_ylim(min_val - y_margin, max_val + y_margin)
    else:
        ax.set_ylim(0, max_val * 1.18)

    # Bar annotations
    for bar, val in zip(bars, values):
        h = bar.get_height()
        if is_reward and h < 0:
            va = "top"
            offset = - (max_val - min_val) * 0.03
        else:
            va = "bottom"
            offset = (max_val if max_val > 0 else 1) * 0.02

        text_val = fmt.format(val)
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            h + offset,
            text_val,
            ha="center",
            va=va,
            fontsize=10.5,
            fontweight="bold",
            color="#111111",
        )

    plt.tight_layout()
    out_path = OUTPUT_DIR / filename
    plt.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"Generated chart -> {out_path.name}")


def plot_overall_benchmark(data, colors):
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle(
        "IntelliRoads Controller Evaluation Summary (30 Episodes x 200 Steps)",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    metrics = [
        ("waiting_time", "Average Waiting Time (s)", "Seconds (Lower is Better)", "{:.2f}s", False),
        ("travel_time", "Average Travel Time (s)", "Seconds (Lower is Better)", "{:.2f}s", False),
        ("queue_length", "Average Queue Length (veh)", "Vehicles (Lower is Better)", "{:.2f}", False),
        ("throughput", "Vehicle Throughput", "Vehicles (Higher is Better)", "{:,.0f}", False),
        ("reward", "Cumulative Episode Reward", "Reward Points (Higher is Better)", "{:,.2f}", True),
    ]

    controllers = data["controllers"]

    for idx, (key, title, ylabel, fmt, is_reward) in enumerate(metrics):
        row, col = divmod(idx, 3)
        ax = axes[row, col]
        values = data[key]

        bars = ax.bar(controllers, values, color=colors, width=0.45, edgecolor="#333333", linewidth=0.8, alpha=0.9)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=9.5)
        ax.grid(True, linestyle="--", alpha=0.4, axis="y")

        min_val, max_val = min(values), max(values)
        if is_reward:
            ax.axhline(0, color="#666666", linewidth=0.8, linestyle="-")
            y_margin = (max_val - min_val) * 0.18
            ax.set_ylim(min_val - y_margin, max_val + y_margin)
        else:
            ax.set_ylim(0, max_val * 1.20)

        for bar, val in zip(bars, values):
            h = bar.get_height()
            if is_reward and h < 0:
                va = "top"
                offset = - (max_val - min_val) * 0.03
            else:
                va = "bottom"
                offset = (max_val if max_val > 0 else 1) * 0.025

            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                h + offset,
                fmt.format(val),
                ha="center",
                va=va,
                fontsize=9.5,
                fontweight="bold",
            )

    # Use the 6th subplot slot for a summary key takeaway panel
    ax_summary = axes[1, 2]
    ax_summary.axis("off")
    summary_text = (
        "Key Performance Takeaways:\n"
        "------------------------------------\n"
        "1. Waiting Time: DQN achieves 3.37s\n"
        "   (-32.0% vs Fixed-Time, -50.3% vs Rule)\n\n"
        "2. Travel Time: DQN achieves 14.38s\n"
        "   (-12.5% vs Fixed-Time, -23.6% vs Rule)\n\n"
        "3. Queue Length: DQN achieves 10.78 veh\n"
        "   (-13.9% vs Fixed-Time, -16.9% vs Rule)\n\n"
        "4. Reward: DQN achieves +1,701.36\n"
        "   (Positive vs deeply negative baselines)\n\n"
        "5. Throughput: 524 veh (DQN optimized for\n"
        "   congestion & delay reduction)"
    )
    ax_summary.text(
        0.05,
        0.95,
        summary_text,
        transform=ax_summary.transAxes,
        fontsize=10.5,
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#F8F9FA", edgecolor="#CCCCCC", alpha=0.9),
        fontfamily="monospace",
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = OUTPUT_DIR / "overall_benchmark_comparison.png"
    plt.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"Generated summary dashboard -> {out_path.name}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    set_chart_style()

    data = load_summary_data(EVAL_SUMMARY_CSV)
    controllers = data["controllers"]

    # Distinct, professional color palette
    colors = ["#4C72B0", "#DD8452", "#55A868"]  # Blue (Fixed-Time), Amber (Rule-Based), Emerald Green (DQN)

    print(f"Loaded evaluation summary for controllers: {controllers}")
    print("Generating comparison graphs...")

    plot_single_metric(
        controllers,
        data["waiting_time"],
        "Average Vehicle Waiting Time Comparison",
        "Waiting Time (seconds)",
        "waiting_time_comparison.png",
        colors,
        fmt="{:.2f}s",
    )

    plot_single_metric(
        controllers,
        data["travel_time"],
        "Average Vehicle Travel Time Comparison",
        "Travel Time (seconds)",
        "travel_time_comparison.png",
        colors,
        fmt="{:.2f}s",
    )

    plot_single_metric(
        controllers,
        data["queue_length"],
        "Average Queue Length Comparison",
        "Queue Length (vehicles)",
        "queue_length_comparison.png",
        colors,
        fmt="{:.2f} veh",
    )

    plot_single_metric(
        controllers,
        data["throughput"],
        "Total Vehicle Throughput Comparison",
        "Throughput (vehicles)",
        "throughput_comparison.png",
        colors,
        fmt="{:,.0f}",
    )

    plot_single_metric(
        controllers,
        data["reward"],
        "Cumulative Episode Reward Comparison",
        "Episode Reward",
        "reward_comparison.png",
        colors,
        fmt="{:,.2f}",
        is_reward=True,
    )

    plot_overall_benchmark(data, colors)

    print("All comparison graphs generated successfully in:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
