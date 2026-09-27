"""
IntelliRoads - Controller Comparison Graph Generator
=====================================================
Reads evaluation_results/eval_summary.csv and generates high-resolution
bar charts comparing Fixed-Time, Rule-Based, and Trained DQN controllers.

Episode Reward is deliberately excluded from all charts here. It is not
a fair head-to-head metric across these three controllers: DQN incurs a
real -1.5 "action changed" penalty (see REWARD_WEIGHT_ACTION_CHANGE in
app/environment/sumo_environment.py) on nearly every one of its ~7,200
per-episode decisions, since it actively chooses an action at every
junction every step. Fixed-Time and Rule-Based are evaluated with
action_changed hardcoded to False in evaluate_controllers.py regardless
of what they actually do, so they never incur this penalty at all - even
though Rule-Based visibly does change signal timings during an episode.
Reward is a meaningful signal for DQN's own training progress, but not a
valid comparison point against the other two controllers here. The four
metrics that ARE directly measured and comparable (waiting time, travel
time, queue length, occupancy/congestion) are used instead.

Outputs saved to comparison_graphs/ directory:
- waiting_time_comparison.png
- travel_time_comparison.png
- queue_length_comparison.png
- throughput_comparison.png
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

DQN_LABEL = "Trained DQN"


def load_summary_data(csv_path: Path):
    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)

    controllers = []
    waiting_times = []
    travel_times = []
    queue_lengths = []
    throughputs = []
    episode_lengths = []

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            controllers.append(row["controller"])
            waiting_times.append(float(row["avg_waiting_time_mean"]))
            travel_times.append(float(row["avg_travel_time_mean"]))
            queue_lengths.append(float(row["avg_queue_length_mean"]))
            throughputs.append(float(row["throughput_mean"]))
            episode_lengths.append(float(row["episode_length_mean"]))

    return {
        "controllers": controllers,
        "waiting_time": waiting_times,
        "travel_time": travel_times,
        "queue_length": queue_lengths,
        "throughput": throughputs,
        "episode_length": episode_lengths,
    }


def set_chart_style():
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#CCCCCC"
    plt.rcParams["axes.linewidth"] = 0.8


def plot_single_metric(controllers, values, title, ylabel, filename, colors, fmt="{:.2f}"):
    fig, ax = plt.subplots(figsize=(8, 5.5))
    bars = ax.bar(controllers, values, color=colors, width=0.45, edgecolor="#333333", linewidth=1.0, alpha=0.9)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel(ylabel, fontsize=11, fontweight="bold")
    ax.set_xlabel("Signal Controller", fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.4, axis="y")

    max_val = max(values)
    ax.set_ylim(0, max_val * 1.18)

    for bar, val in zip(bars, values):
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            h + (max_val if max_val > 0 else 1) * 0.02,
            fmt.format(val),
            ha="center",
            va="bottom",
            fontsize=10.5,
            fontweight="bold",
            color="#111111",
        )

    plt.tight_layout()
    out_path = OUTPUT_DIR / filename
    plt.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"Generated chart -> {out_path.name}")


def _pct_change(dqn_val: float, base_val: float) -> float:
    """% change of DQN relative to a baseline. Negative = DQN is lower."""
    if base_val == 0:
        return 0.0
    return (dqn_val - base_val) / abs(base_val) * 100.0


def _build_summary_text(data: dict) -> str:
    """Compute the takeaways panel text FROM the loaded data, every time -
    never hand-typed, so it can't silently go stale after a re-run."""
    controllers = data["controllers"]
    dqn_idx = controllers.index(DQN_LABEL)
    other_idxs = [i for i in range(len(controllers)) if i != dqn_idx]

    lines = ["Key Performance Takeaways:", "-" * 36]

    metric_defs = [
        ("waiting_time", "Waiting Time", "s", True),
        ("travel_time", "Travel Time", "s", True),
        ("queue_length", "Queue Length", " veh", True),
        ("throughput", "Throughput", " veh", False),
    ]
    for idx, (key, label, unit, lower_is_better) in enumerate(metric_defs, start=1):
        dqn_val = data[key][dqn_idx]
        comparisons = []
        for oi in other_idxs:
            pct = _pct_change(dqn_val, data[key][oi])
            comparisons.append(f"{pct:+.1f}% vs {controllers[oi]}")
        lines.append(f"{idx}. {label}: DQN = {dqn_val:.2f}{unit}")
        lines.append(f"   ({', '.join(comparisons)})")
        lines.append("")

    lines.append(
        "Note: Episode Reward is excluded above - it is\n"
        "not a fair metric across these controllers (see\n"
        "this script's module docstring for why)."
    )
    return "\n".join(lines)


def plot_overall_benchmark(data, colors):
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))

    fig.suptitle(
        "IntelliRoads Controller Evaluation Summary",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    metrics = [
        ("waiting_time", "Average Waiting Time (s)", "Seconds (Lower is Better)", "{:.2f}s"),
        ("travel_time", "Average Travel Time (s)", "Seconds (Lower is Better)", "{:.2f}s"),
        ("queue_length", "Average Queue Length (veh)", "Vehicles (Lower is Better)", "{:.2f}"),
        ("throughput", "Vehicle Throughput", "Vehicles (Higher is Better)", "{:,.0f}"),
    ]

    controllers = data["controllers"]

    for idx, (key, title, ylabel, fmt) in enumerate(metrics):
        row, col = divmod(idx, 2)
        ax = axes[row, col]
        values = data[key]

        bars = ax.bar(controllers, values, color=colors, width=0.45, edgecolor="#333333", linewidth=0.8, alpha=0.9)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=9.5)
        ax.grid(True, linestyle="--", alpha=0.4, axis="y")

        max_val = max(values)
        ax.set_ylim(0, max_val * 1.20)

        for bar, val in zip(bars, values):
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                h + (max_val if max_val > 0 else 1) * 0.025,
                fmt.format(val),
                ha="center",
                va="bottom",
                fontsize=9.5,
                fontweight="bold",
            )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = OUTPUT_DIR / "overall_benchmark_comparison.png"
    plt.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"Generated summary dashboard -> {out_path.name}")

    # Takeaways panel as its own separate image (kept out of the 2x2 grid
    # above so the grid stays a clean, uniform layout).
    fig2, ax_summary = plt.subplots(figsize=(6, 6.5))
    ax_summary.axis("off")
    ax_summary.text(
        0.05, 0.95,
        _build_summary_text(data),
        transform=ax_summary.transAxes,
        fontsize=10.5,
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#F8F9FA", edgecolor="#CCCCCC", alpha=0.9),
        fontfamily="monospace",
    )
    out_path2 = OUTPUT_DIR / "key_takeaways.png"
    plt.tight_layout()
    plt.savefig(out_path2, dpi=200)
    plt.close(fig2)
    print(f"Generated takeaways panel -> {out_path2.name}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    set_chart_style()

    data = load_summary_data(EVAL_SUMMARY_CSV)
    controllers = data["controllers"]

    # Distinct, professional color palette
    colors = ["#4C72B0", "#DD8452", "#55A868"]  # Blue (Fixed-Time), Amber (Rule-Based), Emerald Green (DQN)

    print(f"Loaded evaluation summary for controllers: {controllers}")
    print("Generating comparison graphs (Episode Reward excluded - see module docstring)...")

    plot_single_metric(
        controllers, data["waiting_time"],
        "Average Vehicle Waiting Time Comparison", "Waiting Time (seconds)",
        "waiting_time_comparison.png", colors, fmt="{:.2f}s",
    )
    plot_single_metric(
        controllers, data["travel_time"],
        "Average Vehicle Travel Time Comparison", "Travel Time (seconds)",
        "travel_time_comparison.png", colors, fmt="{:.2f}s",
    )
    plot_single_metric(
        controllers, data["queue_length"],
        "Average Queue Length Comparison", "Queue Length (vehicles)",
        "queue_length_comparison.png", colors, fmt="{:.2f} veh",
    )
    plot_single_metric(
        controllers, data["throughput"],
        "Total Vehicle Throughput Comparison", "Throughput (vehicles)",
        "throughput_comparison.png", colors, fmt="{:,.0f}",
    )

    plot_overall_benchmark(data, colors)

    print("All comparison graphs generated successfully in:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
