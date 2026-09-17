"""
Statistical significance testing for IntelliRoads controller evaluation.

Runs an unpaired (Welch's) t-test comparing the Trained DQN controller
against Fixed-Time (the stronger of the two baselines) across the
per-episode results in evaluation_results/eval_raw.csv.

Why Welch's t-test, not a paired test: evaluate_controllers.py runs
each controller's N_EPISODES sequentially with its own seed range
(Fixed-Time gets seeds 1..30, Rule-Based 31..60, DQN 61..90 - see
ep_counter in evaluate_controllers.py). Episodes are NOT matched
across controllers, so a paired test would be methodologically
invalid here. Welch's test (rather than a standard independent t-test)
is used because it does not assume equal variance between groups,
which matters here since DQN's variance is visibly smaller than the
baselines' in the raw data.

Usage:
    python significance_test.py [path/to/eval_raw.csv]
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from statistics import mean, variance

METRICS = ["avg_waiting_time", "avg_travel_time", "avg_queue_length", "episode_reward"]
COMPARE_AGAINST = "Fixed-Time"  # the stronger of the two baselines
TARGET = "Trained DQN"


def welch_ttest(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """Returns (mean_diff, t_statistic, degrees_of_freedom)."""
    n1, n2 = len(a), len(b)
    m1, m2 = mean(a), mean(b)
    v1, v2 = variance(a), variance(b)
    se = (v1 / n1 + v2 / n2) ** 0.5
    t_stat = (m1 - m2) / se
    df = (v1 / n1 + v2 / n2) ** 2 / (
        (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    )
    return m1 - m2, t_stat, df


def significance_label(t_stat: float, df: float) -> str:
    """Coarse significance banding without requiring scipy. These t-values
    are checked against standard critical-value tables for two-tailed tests
    at df >= 30 (critical values change little for df in the 30-60 range)."""
    t_abs = abs(t_stat)
    if t_abs > 3.65:
        return "p < 0.001"
    if t_abs > 2.75:
        return "p < 0.01"
    if t_abs > 2.02:
        return "p < 0.05"
    return "not significant at p < 0.05"


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("evaluation_results/eval_raw.csv")
    rows = list(csv.DictReader(open(csv_path)))

    data: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        c = r["controller"]
        data.setdefault(c, {m: [] for m in METRICS})
        for m in METRICS:
            data[c][m].append(float(r[m]))

    print(f"Unpaired Welch's t-test: {TARGET} vs {COMPARE_AGAINST} (independent samples, n=30 each)\n")
    print(f"{'Metric':<20} {TARGET+' mean':>14} {COMPARE_AGAINST+' mean':>14} {'diff':>10} {'t-stat':>8} {'df':>6} {'significance':>16}")
    for m in METRICS:
        target_vals = data[TARGET][m]
        base_vals = data[COMPARE_AGAINST][m]
        diff, t_stat, df = welch_ttest(target_vals, base_vals)
        sig = significance_label(t_stat, df)
        print(f"{m:<20} {mean(target_vals):>14.3f} {mean(base_vals):>14.3f} {diff:>10.3f} {t_stat:>8.3f} {df:>6.1f} {sig:>16}")


if __name__ == "__main__":
    main()
