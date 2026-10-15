"""Two-stage checkpoint selection on trip-based *validation* waiting time (Stage 5).

Why: ``train_dqn.py`` picks ``best.pt`` with a lane proxy (``mean_wait_s``) that ranks controllers differently from the trip waiting time of the
evaluation protocol.  This tool re-ranks the periodic checkpoints of one finished training run with the approved measurement
(``runner.run_episode``: 300 s warm-up, 1800 s window, drain <= 600 s, all 16 lanes) on **fresh validation seeds only**.

Process (fixed *before* anything runs and written, with its hash, to ``plan.json``):

* **Stage A – screening:** every candidate (periodic checkpoint) on the stage-A seeds; candidates that are not *eligible*
  (drain exhausted, unfinished trips, completion < ``MIN_COMPLETION``) are dropped; the ``TOP_K`` eligible challengers with the lowest mean
  trip waiting time advance together with the **incumbent** (the checkpoint ``best.pt`` already is).
* **Stage B – confirmation:** the finalists on *different* seeds.  A challenger replaces the incumbent only if it is eligible and the
  Bonferroni-adjusted (``alpha / k``) two-sided t-interval of its paired difference to the incumbent (challenger - incumbent) lies **entirely below 0**.
  Otherwise the incumbent is kept.  Stage-A numbers never enter the decision (winner's-curse protection).

Safety: only ``ES.selection_seeds`` seeds (3,000,100+) are accepted - training, smoke, final (4,000,000-4,999,999, in particular the reserved
4,000,031-4,000,060) and the proxy-validation seeds are refused.  The module never touches the final-evaluation ledger, never writes into a
training run or ``evaluation_runs/``, and never modifies ``best.json`` / ``best.pt``; its only output is a new ``selection_runs/<run-id>/``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from app.evaluation import seeds as ES
from app.environment.observation import OBS_V1
from app.evaluation.controllers import DQNController
from app.evaluation.protocol import (
    BACKEND,
    DEFAULT_EVAL_ROOT,
    EvalProtocol,
    ProtocolError,
    candidate_checkpoints,
    load_candidate_checkpoint,
    load_validation_selected_checkpoint,
    sha256_file,
)
from app.training.runs import DEFAULT_RUNS_ROOT, create_run_dir, write_json_atomic

DEFAULT_SELECTION_ROOT = BACKEND / "selection_runs"
PRIMARY = "wait_per_vehicle_all_s"
INCUMBENT_EPISODE = 400
STAGE_A_N, STAGE_B_N, TOP_K = 10, 20, 3
ALPHA = 0.05
MIN_COMPLETION = 0.999
EST_SECONDS_PER_EPISODE = 14.5                         # measured: final-evaluation episodes took 14.2-14.9 s
ROW_COLUMNS = ["episode", "seed", PRIMARY, "wait_per_vehicle_completed_s", "travel_time_completed_s", "mean_queue_per_lane", "throughput_veh_per_h",
               "trips_scheduled", "trips_completed", "trips_unfinished", "trips_not_inserted", "completion_rate", "drain_s_used", "drain_exhausted",
               "decisions", "actions_switch", "actions_extend", "actions_reduce", "switch_rate", "phases_completed", "wall_s"]


class SelectionError(RuntimeError):
    """The selection protocol was violated or could not be carried out."""


# ------------------------------------------------------------------ Student-t quantile (no scipy dependency)
def _t_pdf(x: float, df: float) -> float:
    c = math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)) / math.sqrt(df * math.pi)
    return c * (1.0 + x * x / df) ** (-(df + 1) / 2)


def t_cdf(x: float, df: int) -> float:
    """CDF of Student's t by Simpson integration of the density (accurate to ~1e-9 for the arguments used here)."""
    if x == 0:
        return 0.5
    n = 2000
    h = abs(x) / n
    s = _t_pdf(0.0, df) + _t_pdf(abs(x), df)
    for i in range(1, n):
        s += (4 if i % 2 else 2) * _t_pdf(i * h, df)
    half = s * h / 3.0
    return 0.5 + half if x > 0 else 0.5 - half


def t_quantile(p: float, df: int) -> float:
    """Inverse CDF of Student's t (``0.5 < p < 1``), by bisection."""
    if not 0.5 < p < 1.0 or df < 1:
        raise SelectionError("t_quantile needs 0.5 < p < 1 and df >= 1")
    lo, hi = 0.0, 200.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def paired_interval(challenger: Sequence[float], incumbent: Sequence[float], alpha: float) -> Dict[str, float]:
    """Two-sided ``1 - alpha`` t-interval of mean(challenger - incumbent) over matched seeds."""
    a, b = np.asarray(challenger, dtype=float), np.asarray(incumbent, dtype=float)
    if a.shape != b.shape or a.ndim != 1:
        raise SelectionError("paired comparison needs equally long, seed-aligned score lists")
    d = a - b
    if len(d) < 2 or not np.isfinite(d).all():
        raise SelectionError("paired comparison needs >= 2 finite paired seeds")
    n = len(d)
    mean, sd = float(d.mean()), float(d.std(ddof=1))
    se = sd / math.sqrt(n)
    tcrit = t_quantile(1.0 - alpha / 2.0, n - 1)
    return {"mean_diff": mean, "sd_diff": sd, "n": n, "t_crit": tcrit, "ci_low": mean - tcrit * se, "ci_high": mean + tcrit * se}


# ------------------------------------------------------------------ pure selection logic
def candidate_eligibility(rows: Sequence[Mapping[str, Any]], min_completion: float = MIN_COMPLETION) -> Tuple[bool, List[str]]:
    """A candidate is eligible only if no episode exhausted its drain, no measured trip is unfinished or un-inserted, completion is high
    enough and the primary metric is defined everywhere (unfinished trips would bias the waiting-time mean)."""
    reasons: List[str] = []
    if not rows:
        return False, ["no episodes"]
    if any(float(r["drain_exhausted"]) > 0 for r in rows):
        reasons.append("drain exhausted in at least one episode")
    if sum(float(r["trips_unfinished"]) + float(r["trips_not_inserted"]) for r in rows) > 0:
        reasons.append("unfinished or not-inserted trips")
    comp = float(np.mean([float(r["completion_rate"]) for r in rows]))
    if not comp >= min_completion:
        reasons.append(f"mean completion {comp:.4f} < {min_completion}")
    if any(not math.isfinite(float(r[PRIMARY])) for r in rows):
        reasons.append("primary metric undefined")
    return not reasons, reasons


def rank_stage_a(scores: Mapping[int, Sequence[float]], eligible: Mapping[int, bool], incumbent: int, top_k: int = TOP_K) -> List[int]:
    """Finalists for stage B: up to ``top_k`` eligible *challengers* (lowest mean trip waiting, ties -> earlier episode) plus the incumbent."""
    if incumbent not in scores:
        raise SelectionError("the incumbent must be screened in stage A")
    challengers = [e for e in scores if e != incumbent and eligible.get(e, False)]
    challengers.sort(key=lambda e: (float(np.mean(scores[e])), e))
    return sorted(challengers[:top_k]) + [incumbent]


def decide(stage_b: Mapping[int, Sequence[float]], eligible: Mapping[int, bool], incumbent: int, alpha: float = ALPHA) -> Dict[str, Any]:
    """Final decision on the independent stage-B seeds (rows are seed-aligned).  The incumbent stays unless a challenger is eligible and the
    Bonferroni-adjusted interval of (challenger - incumbent) lies entirely below 0."""
    if incumbent not in stage_b:
        raise SelectionError("the incumbent must be confirmed in stage B")
    challengers = sorted(e for e in stage_b if e != incumbent)
    k = len(challengers)
    out: Dict[str, Any] = {"incumbent_episode": incumbent, "alpha": alpha, "n_challengers": k, "confidence_per_comparison": 1 - alpha / max(k, 1),
                           "rule": "replace the incumbent only if a challenger is eligible and the Bonferroni-adjusted (alpha/k) two-sided t-interval of "
                                   "mean(challenger - incumbent) trip waiting time lies entirely below 0",
                           "incumbent_mean": float(np.mean(stage_b[incumbent])), "challengers": {}}
    supported: List[Tuple[float, int]] = []
    for e in challengers:
        iv = paired_interval(stage_b[e], stage_b[incumbent], alpha / k)
        ok = bool(eligible.get(e, False))
        sup = ok and iv["ci_high"] < 0.0
        out["challengers"][str(e)] = {**iv, "mean": float(np.mean(stage_b[e])), "eligible": ok, "supported_improvement": bool(sup)}
        if sup:
            supported.append((iv["mean_diff"], e))
    if supported:
        supported.sort()
        out.update(selected_episode=supported[0][1], replaced=True)
    else:
        out.update(selected_episode=incumbent, replaced=False)
    return out


# ------------------------------------------------------------------ plan
@dataclass(frozen=True)
class SelectionPlan:
    run_dir: str
    candidates: Tuple[Tuple[int, str, str], ...]          # (episode, file, sha256)
    incumbent_episode: int
    stage_a_seeds: Tuple[int, ...]
    stage_b_seeds: Tuple[int, ...]
    top_k: int = TOP_K
    alpha: float = ALPHA
    min_completion: float = MIN_COMPLETION
    protocol: Tuple[Tuple[str, Any], ...] = (("warmup_s", 300), ("measure_s", 1800), ("drain_max_s", 600), ("decision_interval_s", 5))

    def to_dict(self) -> Dict[str, Any]:
        return {"run_dir": self.run_dir, "candidates": [list(c) for c in self.candidates], "incumbent_episode": self.incumbent_episode,
                "stage_a_seeds": list(self.stage_a_seeds), "stage_b_seeds": list(self.stage_b_seeds), "top_k": self.top_k, "alpha": self.alpha,
                "min_completion": self.min_completion, "protocol": dict(self.protocol), "primary_metric": PRIMARY,
                "multiplicity": "Bonferroni over the stage-B challengers", "reserved_final_seeds": list(ES.FRESH_FINAL_RESERVED),
                "uses_final_seeds": False, "uses_ledger": False}

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()

    def protocol_for(self, seeds: Sequence[int]) -> EvalProtocol:
        p = dict(self.protocol)
        return EvalProtocol(warmup_s=p["warmup_s"], measure_s=p["measure_s"], drain_max_s=p["drain_max_s"], decision_interval_s=p["decision_interval_s"],
                            n_seeds=len(seeds), mode="validation")

    def n_episodes(self) -> Tuple[int, int]:
        """(stage A episodes, upper bound of stage B episodes)."""
        return len(self.candidates) * len(self.stage_a_seeds), (self.top_k + 1) * len(self.stage_b_seeds)


SEED_SETS = ("v1", "obs-v2")


def build_plan(run_dir: Path, stage_a_n: int = STAGE_A_N, stage_b_n: int = STAGE_B_N, top_k: int = TOP_K,
               incumbent_episode: int = INCUMBENT_EPISODE, seed_set: str = "v1") -> SelectionPlan:
    """Read-only: list the candidates (file names and SHA-256 only, no model is loaded), check that the incumbent is the run's current
    ``best.pt`` selection, and fix the seeds."""
    run_dir = Path(run_dir)
    cands = candidate_checkpoints(run_dir)
    if len(cands) < 2:
        raise SelectionError(f"{run_dir} holds fewer than two periodic checkpoints")
    best_json = run_dir / "best.json"
    if not best_json.is_file():
        raise SelectionError(f"{run_dir} has no best.json")
    best_ep = int(json.loads(best_json.read_text())["episode"])
    if best_ep != incumbent_episode:
        raise SelectionError(f"the run's best.json selects episode {best_ep}, not the incumbent {incumbent_episode}")
    if incumbent_episode not in {e for e, _ in cands}:
        raise SelectionError(f"incumbent episode {incumbent_episode} has no periodic checkpoint")
    if top_k < 1:
        raise SelectionError("top_k must be >= 1")
    if seed_set == "v1":                                            # established behaviour (fyp_s0), unchanged
        a, b = ES.selection_seeds("A", stage_a_n), ES.selection_seeds("B", stage_b_n)
    elif seed_set == "obs-v2":                                      # Stage 7: the approved fresh obs-v2 ranges, fixed sizes
        cfg_path = run_dir / "config.json"
        obs = json.loads(cfg_path.read_text()).get("obs_version") if cfg_path.is_file() else None
        if obs != "fyp-obs-v2":
            raise SelectionError(f"the obs-v2 seed set is reserved for fyp-obs-v2 training runs; {run_dir} records {obs!r}")
        ES.assert_v2_selection_identity(run_dir.resolve().name, incumbent_episode,
                                        {e: sha256_file(p) for e, p in cands})   # consumed seeds: only the recorded experiment itself
        a, b = ES.v2_seeds("stage_A"), ES.v2_seeds("stage_B")      # its exact recorded ranges (reconstruction)
        if (stage_a_n, stage_b_n) != (len(a), len(b)):
            raise SelectionError(f"the obs-v2 seed set fixes {len(a)} stage-A and {len(b)} stage-B seeds, got {stage_a_n}/{stage_b_n}")
        ES.assert_v2_seed_plan()                                    # pairwise disjoint and disjoint from the reserved final seeds
    else:
        raise SelectionError(f"unknown seed set {seed_set!r}; known: {SEED_SETS}")
    ES.assert_selection_seeds(a, b)
    return SelectionPlan(str(run_dir), tuple((e, p.name, sha256_file(p)) for e, p in cands), incumbent_episode, tuple(a), tuple(b), top_k)


def weights_equal(agent_a: Any, agent_b: Any) -> bool:
    import torch
    sa, sb = agent_a.policy_net.state_dict(), agent_b.policy_net.state_dict()
    return sa.keys() == sb.keys() and all(torch.equal(sa[k], sb[k]) for k in sa)


# ------------------------------------------------------------------ execution
class EpisodeRunner:
    """Real SUMO episodes through the approved ``run_episode`` (one environment per stage)."""

    def __init__(self, protocol: EvalProtocol) -> None:
        from app.environment.traffic_env import EnvConfig, TrafficSignalEnv
        self.protocol = protocol
        self.env = TrafficSignalEnv(EnvConfig(horizon_s=protocol.horizon_s, decision_interval_s=protocol.decision_interval_s,
                                              demand_end_s=protocol.demand_end_s))

    def run(self, controller: DQNController, seed: int) -> Dict[str, Any]:
        from app.environment.traffic_env import EnvConfig, TrafficSignalEnv
        from app.evaluation import runner
        want = runner._obs_kwargs(controller)
        have = {} if self.env.cfg.obs_version == OBS_V1 else {"obs_version": self.env.cfg.obs_version, "detector_range_m": self.env.cfg.detector_range_m}
        if want != have:                                   # the candidate's own observation schema (v1 runs never get here)
            self.env.close()
            self.env = TrafficSignalEnv(EnvConfig(horizon_s=self.protocol.horizon_s, decision_interval_s=self.protocol.decision_interval_s,
                                                  demand_end_s=self.protocol.demand_end_s, **want))
        return runner.run_episode(self.env, controller, seed, self.protocol)["row"]

    def close(self) -> None:
        self.env.close()


def _assert_out_root(out_root: Path) -> Path:
    root = Path(out_root).resolve()
    for forbidden in (DEFAULT_EVAL_ROOT, DEFAULT_RUNS_ROOT):
        f = Path(forbidden).resolve()
        if root == f or f in root.parents:
            raise SelectionError(f"selection output must not be written into {f} (final-evaluation / training outputs stay untouched)")
    return root


def _row_out(episode: int, seed: int, row: Mapping[str, Any]) -> Dict[str, Any]:
    out = {"episode": episode, "seed": seed, **{k: row[k] for k in ROW_COLUMNS if k in row and k not in ("episode", "seed", "switch_rate")}}
    out["switch_rate"] = float(row["actions_switch"]) / (float(row["decisions"]) * 4.0)
    return out


def _run_stage(name: str, plan: SelectionPlan, run_dir: Path, episodes: Sequence[int], seeds: Sequence[int], out_dir: Path,
               make_runner: Callable[[EvalProtocol], Any], progress: Callable[[str], None]) -> Dict[int, List[Dict[str, Any]]]:
    ES.assert_seeds_for_mode(list(seeds), "validation")
    for sd in seeds:
        ES.assert_selection_seed(sd)
    files = {e: (f, sha) for e, f, sha in plan.candidates}
    runner_obj = make_runner(plan.protocol_for(seeds))
    rows: Dict[int, List[Dict[str, Any]]] = {e: [] for e in episodes}
    path = out_dir / f"stage_{name.lower()}.csv"
    try:
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(ROW_COLUMNS)
            for e in episodes:
                fname, sha = files[e]
                if sha256_file(Path(run_dir) / fname) != sha:
                    raise SelectionError(f"{fname} changed after the plan was written")
                agent, info = load_candidate_checkpoint(run_dir, fname)
                ctrl = DQNController(agent, info)
                for seed in seeds:
                    row = _row_out(e, seed, runner_obj.run(ctrl, seed))
                    rows[e].append(row)
                    w.writerow([row.get(c, "") for c in ROW_COLUMNS]); fh.flush()
                    progress(f"[selection stage {name}] ep {e:4d} seed {seed} {PRIMARY}={float(row[PRIMARY]):.3f}")
    finally:
        runner_obj.close()
    return rows


def run_selection(plan: SelectionPlan, out_root: Path, run_id: str, confirm: bool = False,
                  make_runner: Callable[[EvalProtocol], Any] = EpisodeRunner, progress: Callable[[str], None] = print) -> Dict[str, Any]:
    """Execute the two-stage selection into a NEW directory ``<out_root>/<run_id>/``.  Requires ``confirm=True``."""
    if not confirm:
        raise SelectionError("running the selection simulates hundreds of episodes; confirm it explicitly (--confirm-selection)")
    ES.assert_selection_seeds(list(plan.stage_a_seeds), list(plan.stage_b_seeds))
    root = _assert_out_root(out_root)
    run_dir = Path(plan.run_dir)
    out_dir = create_run_dir(root, run_id)
    write_json_atomic(out_dir / "plan.json", {**plan.to_dict(), "plan_sha256": plan.sha256(), "written_before_any_episode": True})
    incumbent = plan.incumbent_episode
    inc_file = {e: f for e, f, _ in plan.candidates}[incumbent]
    inc_agent, _ = load_candidate_checkpoint(run_dir, inc_file)
    best_agent, best_info = load_validation_selected_checkpoint(run_dir)
    if not weights_equal(inc_agent, best_agent):
        raise SelectionError(f"periodic checkpoint of episode {incumbent} does not hold the weights of best.pt - refusing to treat it as the incumbent")
    t0 = time.time()
    all_eps = [e for e, _, _ in plan.candidates]
    a_rows = _run_stage("A", plan, run_dir, all_eps, plan.stage_a_seeds, out_dir, make_runner, progress)
    a_scores = {e: [float(r[PRIMARY]) for r in rows] for e, rows in a_rows.items()}
    a_elig = {e: candidate_eligibility(rows, plan.min_completion)[0] for e, rows in a_rows.items()}
    finalists = rank_stage_a(a_scores, a_elig, incumbent, plan.top_k)
    b_rows = _run_stage("B", plan, run_dir, finalists, plan.stage_b_seeds, out_dir, make_runner, progress)
    b_scores = {e: [float(r[PRIMARY]) for r in rows] for e, rows in b_rows.items()}
    b_elig = {e: candidate_eligibility(rows, plan.min_completion)[0] for e, rows in b_rows.items()}
    decision = decide(b_scores, b_elig, incumbent, plan.alpha)
    files = {e: (f, sha) for e, f, sha in plan.candidates}
    decision.update({
        "stage_a": {str(e): {"mean": float(np.mean(a_scores[e])), "eligible": a_elig[e], "eligibility_reasons": candidate_eligibility(a_rows[e], plan.min_completion)[1]}
                    for e in all_eps},
        "finalists": finalists, "selected_file": files[decision["selected_episode"]][0], "selected_sha256": files[decision["selected_episode"]][1],
        "plan_sha256": plan.sha256(), "uses_final_seeds": False, "ledger_touched": False, "best_pt_sha256": best_info["sha256"],
        "label": "VALIDATION-SEED checkpoint selection (not a final evaluation; no superiority claim)", "wall_seconds": round(time.time() - t0, 1)})
    write_json_atomic(out_dir / "decision.json", decision)
    return {"out_dir": out_dir, "decision": decision, "stage_a_rows": a_rows, "stage_b_rows": b_rows}
