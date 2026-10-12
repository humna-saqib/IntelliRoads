# Evaluation v2 (corrected measurement) — current checkpoint, unchanged
Files: evaluate_v2.py, stats_v2.py, config_v2.json, eval_raw_v2.csv (per-seed), eval_summary_v2.csv,
paired_tests_v2.csv, measurement_counts_v2.csv, stats_v2_output.txt, run_v2.log.
Original results (../evaluation_results) and checkpoint (sha256 17ec9ead...) are untouched.
Fix: legacy DQN loop stopped measuring junctions B-D after sim second 900 (env done flag, counts calls) but still divided by 4.
All controllers now share one runner/measurer; 1800 steps x 4 junctions = 7200 observations per episode (asserted).
Result: Trained DQN took action KEEP in 216,000/216,000 decisions and is identical to Always-Keep on all 30 seeds.
Legacy code rerun on seed 1 matches v2 but not the stored legacy CSV (see report): stored CSV likely produced in a different environment/SUMO build.
