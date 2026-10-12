"""Aggregate + paired tests for eval_raw_v2.csv (run from evaluation_v2/ or anywhere)."""
from pathlib import Path
import itertools
import numpy as np
import pandas as pd
from scipy import stats

D = Path(__file__).resolve().parent
df = pd.read_csv(D / "eval_raw_v2.csv")
METRICS = ["avg_waiting_time", "avg_travel_time", "avg_queue_length", "avg_occupancy",
           "pct_congested", "throughput_arrived", "throughput_departed"]
ORDER = ["Fixed-Time", "Rule-Based", "Always-Keep", "Trained DQN"]

# ---- measurement-count verification ----
cnt = df.groupby("controller")[["n_steps_measured", "n_junction_obs", "n_travel_time_obs"]].agg(["min", "max"])
cnt.to_csv(D / "measurement_counts_v2.csv")
assert (df.n_steps_measured == 1800).all() and (df.n_junction_obs == 7200).all()
print("MEASUREMENT COUNTS (min/max over episodes)\n", cnt, "\n")
print("episodes per controller:", df.groupby("controller").size().to_dict())

# ---- aggregates ----
rows = []
for c in ORDER:
    s = df[df.controller == c]
    r = {"controller": c, "n": len(s)}
    for m in METRICS:
        r[f"{m}_mean"] = s[m].mean(); r[f"{m}_sd"] = s[m].std(ddof=1)
    rows.append(r)
summ = pd.DataFrame(rows); summ.to_csv(D / "eval_summary_v2.csv", index=False)
print(summ.set_index("controller").T.round(3).to_string(), "\n")

# ---- paired tests (matched seeds) ----
out = []
for a, b in [("Trained DQN", "Always-Keep"), ("Trained DQN", "Fixed-Time"), ("Trained DQN", "Rule-Based"),
             ("Always-Keep", "Fixed-Time"), ("Always-Keep", "Rule-Based"), ("Rule-Based", "Fixed-Time")]:
    x = df[df.controller == a].sort_values("seed").reset_index(drop=True)
    y = df[df.controller == b].sort_values("seed").reset_index(drop=True)
    assert (x.seed.values == y.seed.values).all()
    for m in METRICS:
        d = (x[m] - y[m]).to_numpy(); n = len(d); mu = d.mean(); sd = d.std(ddof=1)
        if sd == 0:
            out.append(dict(a=a, b=b, metric=m, mean_diff=mu, pct=100 * mu / y[m].mean() if y[m].mean() else np.nan,
                            ci_lo=mu, ci_hi=mu, t=np.nan, p=np.nan, n_identical=int((d == 0).sum()))); continue
        se = sd / np.sqrt(n); h = stats.t.ppf(.975, n - 1) * se
        t, p = stats.ttest_rel(x[m], y[m])
        out.append(dict(a=a, b=b, metric=m, mean_diff=mu, pct=100 * mu / y[m].mean() if y[m].mean() else np.nan,
                        ci_lo=mu - h, ci_hi=mu + h, t=t, p=p, n_identical=int((np.abs(d) < 1e-12).sum())))
pt = pd.DataFrame(out); pt.to_csv(D / "paired_tests_v2.csv", index=False)
pd.set_option("display.width", 200)
print(pt[pt.metric.isin(METRICS[:5])].round(4).to_string(index=False))
