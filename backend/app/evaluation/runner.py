"""Runs controllers on matched seeds, checks every episode, and writes a NEW output directory (Stage 4).

Per episode the runner verifies that the episode ran to its horizon, that the measurement covers the whole window of
all 16 incoming lanes, and that no safety rule was violated.  For the fixed-time baseline it also verifies the *actual*
phase timings against SUMO's configured programme.  No statistical verdicts are produced: the summary reports
descriptive means and paired differences with t-intervals only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import torch

from app.environment.observation import OBS_V1, EnvError
from app.environment.traffic_env import EnvConfig, TrafficSignalEnv
from app.evaluation import seeds as ES
from app.evaluation.controllers import DQNController, EvalController, build_controllers
from app.evaluation.metrics import EpisodeMeasurer, MeasurementError
from app.evaluation.protocol import (
    BACKEND,
    CONTROLLER_ORDER,
    DEFAULT_EVAL_ROOT,
    EvalProtocol,
    ProtocolError,
    append_ledger,
    assert_final_not_repeated,
    assert_final_seeds_unused,
    ledger_lock,
    program_from_net,
    read_ledger,
    verify_fixed_time_timing,
)
from app.training.runs import assert_output_root_allowed, create_run_dir, write_json_atomic

PRIMARY_METRIC = "wait_per_vehicle_all_s"
METRIC_KEYS = [
    "wait_per_vehicle_all_s", "wait_per_vehicle_completed_s", "travel_time_completed_s", "unfinished_age_mean_s",
    "trips_departed", "trips_completed", "trips_unfinished", "unfinished_share", "trips_not_inserted", "trips_scheduled", "departed_after_window", "completion_rate", "arrivals_in_window", "throughput_veh_per_h",
    "mean_queue_per_lane", "max_queue_any_lane", "mean_vehicles_per_lane", "mean_occupancy_pct", "pct_lane_steps_congested",
    "n_lane_obs", "n_steps_measured", "n_steps_total", "teleports",
]
EXTRA_COLUMNS = ["drain_s_used", "drain_exhausted", "vehicles_left_at_end", "decisions", "phases_completed", "actions_keep", "actions_switch", "actions_extend", "actions_reduce", "wall_s"]
BASELINE = "fixed_time"
N_LANES = 16

# two-sided 95 % Student-t critical values, df = 1 .. 30
_T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101,
         2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def t_critical_95(df: int) -> float:
    if df < 1:
        return float("nan")
    if df <= 30:
        return _T975[df - 1]
    z = 1.959964
    return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df ** 2)


def describe(x: Sequence[float]) -> Dict[str, float]:
    """Mean / sample SD (ddof = 1) / min / max over the seeds with a defined value (``n`` says how many; NaN = undefined for that seed)."""
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        nan = float("nan")
        return {"mean": nan, "sd": nan, "n": 0, "min": nan, "max": nan}
    return {"mean": float(a.mean()), "sd": float(a.std(ddof=1)) if len(a) > 1 else float("nan"), "n": int(len(a)),
            "min": float(a.min()), "max": float(a.max())}


def paired_difference(a: Sequence[float], b: Sequence[float]) -> Dict[str, float]:
    """Descriptive paired difference ``a - b`` over matched seeds with a 95 % t-interval (no hypothesis test)."""
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    d = d[np.isfinite(d)]                                   # a pair is used only if the metric is defined for both controllers on that seed
    n = len(d)
    if n == 0:
        nan = float("nan")
        return {"mean_diff": nan, "sd_diff": nan, "median_diff": nan, "n_pairs": 0, "ci95_low": nan, "ci95_high": nan}
    sd = float(d.std(ddof=1)) if n > 1 else float("nan")
    half = t_critical_95(n - 1) * sd / math.sqrt(n) if n > 1 else float("nan")
    return {"mean_diff": float(d.mean()), "sd_diff": sd, "median_diff": float(np.median(d)), "n_pairs": n,
            "ci95_low": float(d.mean() - half), "ci95_high": float(d.mean() + half)}


def summarize(rows: Sequence[Dict[str, Any]], controllers: Sequence[str], seeds: Sequence[int]) -> Dict[str, Any]:
    by = {c: {r["seed"]: r for r in rows if r["controller"] == c} for c in controllers}
    for c in controllers:
        if sorted(by[c]) != sorted(seeds):
            raise ProtocolError(f"controller {c} was not evaluated on exactly the matched seeds")
    out: Dict[str, Any] = {"primary_metric": PRIMARY_METRIC, "seeds": list(seeds), "n_seeds": len(seeds),
                           "controllers": {}, "paired_vs_fixed_time": {},
                           "unit_of_analysis": "one episode (seed) per controller: every metric is first reduced to one network-wide value per seed",
                           "paired_difference": "d_s = x_controller,s - x_fixed_time,s per seed; mean(d), sample SD(d) (ddof=1), 95% CI = mean(d) +/- t(0.975, n-1) * SD(d)/sqrt(n)",
                           "note": "descriptive statistics only; no significance test and no claim of superiority is made"}
    for c in controllers:
        out["controllers"][c] = {m: describe([by[c][s][m] for s in seeds]) for m in METRIC_KEYS}
    if BASELINE in controllers:
        for c in controllers:
            if c != BASELINE:
                out["paired_vs_fixed_time"][c] = {m: paired_difference([by[c][s][m] for s in seeds], [by[BASELINE][s][m] for s in seeds])
                                                  for m in METRIC_KEYS}
    return out


def lanes_of(env: TrafficSignalEnv) -> List[str]:
    lanes = sorted({l for j in env.cfg.junction_ids for l in env.topology[j].lanes})
    if len(lanes) != N_LANES:
        raise ProtocolError(f"expected {N_LANES} incoming lanes, found {len(lanes)}")
    return lanes


def _assert_configured_program(env: TrafficSignalEnv, program: Dict[str, Any]) -> None:
    """The programme SUMO actually runs (via TraCI) must be the one of the network file: same phases, durations and states."""
    for j in env.cfg.junction_ids:
        logics = env.conn.trafficlight.getAllProgramLogics(j)
        active = env.conn.trafficlight.getProgram(j)
        logic = next((lg for lg in logics if lg.programID == active), None)
        if logic is None:
            raise ProtocolError(f"{j}: active programme {active!r} not found")
        got = [(float(p.duration), p.state) for p in logic.phases]
        if got != [(float(d), s) for d, s in program[j]]:
            raise ProtocolError(f"{j}: SUMO runs {got}, the network file configures {program[j]}")


def run_episode(env: TrafficSignalEnv, controller: EvalController, seed: int, protocol: EvalProtocol,
                program: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One matched episode. Raises if it did not run to its horizon, was measured incompletely, or broke a safety rule."""
    t0 = time.time()
    obs = env.reset(seed)
    lanes = lanes_of(env)
    if env.cfg.horizon_s != protocol.horizon_s or env.cfg.demand_end_s != protocol.demand_end_s:
        raise ProtocolError(f"environment horizon/demand end ({env.cfg.horizon_s}/{env.cfg.demand_end_s}) does not match the protocol "
                            f"({protocol.horizon_s}/{protocol.demand_end_s})")
    if controller.name == "fixed_time":
        _assert_configured_program(env, program or program_from_net())
    measurer = EpisodeMeasurer(lanes, protocol.warmup_s, protocol.measure_s)
    env.add_second_hook(measurer)
    controller.start_episode(env)
    masks = env.action_masks()
    counts = np.zeros(4, dtype=int)
    decisions = 0
    while True:
        acts = controller.act(env, obs, masks)
        counts += np.bincount(list(acts.values()), minlength=4)
        res = env.step(acts)
        decisions += 1
        if res.info["coerced_actions"] or res.info["safety_violations"]:
            raise ProtocolError(f"{controller.name}: illegal action or safety violation at t={env.sim_time:g}s (seed {seed})")
        obs, masks = res.obs, res.info["action_masks"]
        if res.terminated or res.truncated:
            break
    end_t = env.sim_time
    if res.terminated and end_t < protocol.demand_end_s:
        raise ProtocolError(f"{controller.name}, seed {seed}: network empty at t={end_t:g}s, before the demand ended at {protocol.demand_end_s}s")
    if res.truncated and end_t != protocol.horizon_s:
        raise ProtocolError(f"{controller.name}, seed {seed}: truncated at t={end_t:g}s instead of the maximum horizon {protocol.horizon_s}s")
    if decisions != end_t / protocol.decision_interval_s or end_t < protocol.demand_end_s:
        raise ProtocolError(f"{controller.name}, seed {seed}: episode did not run through the measured window ({end_t:g}s, {decisions} decisions)")
    left = int(env.conn.simulation.getMinExpectedNumber())
    pending = len(env.conn.simulation.getPendingVehicles())     # read for every ending, so a terminated run with never-inserted trips is caught
    metrics = measurer.finalize(int(end_t), run_end_s=end_t, not_inserted=pending)
    if res.terminated and (metrics["trips_unfinished"] != 0 or pending):
        raise MeasurementError(f"{controller.name}, seed {seed}: network reported empty but {metrics['trips_unfinished']:g} measured trips are "
                               f"unfinished and {pending} vehicles were never inserted")
    if metrics["n_lane_obs"] != N_LANES * protocol.measure_s:
        raise MeasurementError(f"{controller.name}: {metrics['n_lane_obs']:g} lane observations, expected {N_LANES * protocol.measure_s}")
    if math.isnan(metrics[PRIMARY_METRIC]):
        raise MeasurementError(f"seed {seed}: no vehicle departed inside the measurement window")
    timing = None
    if controller.name == "fixed_time":
        timing = verify_fixed_time_timing(env.signal_log, program or program_from_net(), env.cfg.junction_ids)
    row = {"controller": controller.name, "seed": seed, **{k: metrics[k] for k in METRIC_KEYS},
           "drain_s_used": end_t - protocol.demand_end_s, "drain_exhausted": int(res.truncated), "vehicles_left_at_end": left, "decisions": decisions,
           "phases_completed": len(env.signal_log), "actions_keep": int(counts[0]), "actions_switch": int(counts[1]),
           "actions_extend": int(counts[2]), "actions_reduce": int(counts[3]), "wall_s": round(time.time() - t0, 2)}
    return {"row": row, "timing": timing, "lanes": [{"controller": controller.name, "seed": seed, "lane": l,
                                                      "junction": next(j for j in env.cfg.junction_ids if l in env.topology[j].lanes), **d}
                                                     for l, d in zip(lanes, measurer.lane_acc.per_lane())]}


def _source_hashes() -> Dict[str, str]:
    files = sorted((BACKEND / "app" / "evaluation").glob("*.py")) + sorted((BACKEND / "app" / "environment").glob("*.py")) + sorted(
        (BACKEND / "app" / "training").glob("*.py")) + [BACKEND / "evaluate_fyp.py", BACKEND / "app" / "sumo_tools" / "route_generator.py",
                                                         BACKEND / "sumo" / "network" / "intelliroads.net.xml", BACKEND / "sumo" / "config" / "intelliroads.sumocfg"]
    return {str(f.relative_to(BACKEND)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.exists()}


def _git(*args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", *args], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _obs_kwargs(dqn: Optional[DQNController]) -> Dict[str, Any]:
    """Environment observation settings of the evaluated checkpoint (v1 default; baselines ignore the observation)."""
    if dqn is None or dqn.info.get("obs_version") in (None, OBS_V1):
        return {}
    return {"obs_version": dqn.info["obs_version"], "detector_range_m": dqn.info["detector_range_m"]}


def assert_final_seed_list(seeds: Sequence[int]) -> None:
    """Final seeds must be sorted, unique and contiguous, so the ledger range ``[first, last]`` is exactly the evaluated set."""
    s = [int(x) for x in seeds]
    if not s:
        raise ProtocolError("a final evaluation needs at least one seed")
    if s != list(range(s[0], s[0] + len(s))):
        raise ProtocolError(f"final seeds must be sorted, unique and contiguous (e.g. from --seed-base / --n-seeds); got {s[:5]}{'...' if len(s) > 5 else ''}")


def evaluate(protocol: EvalProtocol, controller_names: Sequence[str], seeds: Sequence[int], out_root: Path, run_id: str,
             dqn: Optional[DQNController] = None, confirm_final: bool = False, allow_repeat_final: bool = False,
             argv: Optional[Sequence[str]] = None, progress: Callable[[str], None] = print) -> Dict[str, Any]:
    """Evaluate ``controller_names`` on the matched ``seeds`` into a new directory ``<out_root>/<run_id>/``."""
    if protocol.mode == "validation":
        raise ProtocolError("validation mode belongs to the checkpoint-selection tool (select_checkpoint.py); evaluate() is for final and smoke runs only")
    ES.assert_seeds_for_mode(list(seeds), protocol.mode)
    if len(seeds) != protocol.n_seeds:
        raise ProtocolError(f"protocol asks for {protocol.n_seeds} seeds, got {len(seeds)}")
    names = [n for n in CONTROLLER_ORDER if n in controller_names]
    if sorted(names) != sorted(controller_names) or len(set(controller_names)) != len(controller_names):
        raise ProtocolError(f"unknown or duplicate controller in {list(controller_names)}")
    if protocol.mode == "final":
        if not confirm_final:
            raise ProtocolError("a final evaluation must be confirmed explicitly (--confirm-final) – it is the reported result")
        if dqn is not None and dqn.info.get("smoke_training_run"):
            raise ProtocolError("a checkpoint from a --smoke training run cannot be used for a final evaluation")
        assert_final_seed_list(seeds)
        if Path(out_root).resolve() != Path(DEFAULT_EVAL_ROOT).resolve():
            raise ProtocolError(f"a final evaluation must write to {DEFAULT_EVAL_ROOT} so that its ledger "
                                f"({Path(DEFAULT_EVAL_ROOT) / 'ledger.jsonl'}) guards repeats and seed reuse; got --out-root {out_root}")
    controllers = build_controllers(names, dqn)
    root = Path(out_root)
    ledger_path = root / "ledger.jsonl"
    ck_sha = dqn.info.get("sha256") if dqn is not None else None
    policy_sha = dqn.info.get("policy_sha256") if dqn is not None else None
    entry = {"run_id": run_id, "mode": protocol.mode, "checkpoint_sha256": ck_sha, "policy_sha256": policy_sha, "seeds": [min(seeds), max(seeds)],
             "controllers": names, "repeat": bool(protocol.mode == "final" and ck_sha and allow_repeat_final)}
    root = assert_output_root_allowed(root)
    root.mkdir(parents=True, exist_ok=True)
    with ledger_lock(ledger_path):                               # check and record under one exclusive lock
        if protocol.mode == "final":
            ledger = read_ledger(ledger_path)
            assert_final_seeds_unused(ledger, seeds)
            if ck_sha:
                assert_final_not_repeated(ledger, ck_sha, allow_repeat_final, policy_sha)
        run_dir = create_run_dir(root, run_id)
        append_ledger(ledger_path, {**entry, "status": "started", "time": time.strftime("%Y-%m-%dT%H:%M:%S")})
    program = program_from_net()
    meta = {"protocol": {"warmup_s": protocol.warmup_s, "measure_s": protocol.measure_s, "horizon_s": protocol.horizon_s,
                         "decision_interval_s": protocol.decision_interval_s, "n_seeds": protocol.n_seeds, "mode": protocol.mode,
                         "demand_end_s": protocol.demand_end_s, "drain_max_s": protocol.drain_max_s},
            "seeds": list(seeds), "controllers": {c.name: c.params for c in controllers}, "primary_metric": PRIMARY_METRIC,
            "metrics": METRIC_KEYS, "lanes_measured": N_LANES, "dqn_checkpoint": dqn.info if dqn is not None else None,
            "configured_programme": {j: [d for d, _ in program[j]] for j in program}, "smoke": protocol.mode == "smoke",
            "argv": list(argv) if argv is not None else None, "git_commit": _git("rev-parse", "HEAD"),
            "git_dirty": bool(_git("status", "--porcelain", "--", str(BACKEND))), "source_sha256": _source_hashes(),
            "versions": {"python": platform.python_version(), "numpy": np.__version__, "torch": torch.__version__}}
    write_json_atomic(run_dir / "protocol.json", meta)
    env = TrafficSignalEnv(EnvConfig(horizon_s=protocol.horizon_s, decision_interval_s=protocol.decision_interval_s,
                                     demand_end_s=protocol.demand_end_s, **_obs_kwargs(dqn)))
    rows: List[Dict[str, Any]] = []
    timing_checks: List[Dict[str, Any]] = []
    csv_path = run_dir / "episodes.csv"
    lane_rows: List[Dict[str, Any]] = []
    header = ["controller", "seed", *METRIC_KEYS, *EXTRA_COLUMNS]
    t_start = time.time()
    try:
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            for k, seed in enumerate(seeds, 1):                                  # matched: every controller sees seed k's traffic
                for c in controllers:
                    res = run_episode(env, c, seed, protocol, program)
                    rows.append(res["row"])
                    lane_rows.extend(res["lanes"])
                    w.writerow([res["row"][h] for h in header]); f.flush()
                    if res["timing"] is not None:
                        timing_checks.append({"seed": seed, **res["timing"]})
                    progress(f"[{protocol.mode}] seed {seed} ({k}/{len(seeds)}) {c.name:15s} {PRIMARY_METRIC}={res['row'][PRIMARY_METRIC]:.3f} "
                             f"({res['row']['wall_s']:.1f}s)")
    finally:
        env.close()
    summary = summarize(rows, names, list(seeds))
    write_json_atomic(run_dir / "summary.json", summary)
    lane_header = ["controller", "seed", "junction", "lane", "mean_vehicles", "mean_queue", "mean_occupancy_pct", "pct_steps_congested"]
    with open(run_dir / "lanes.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(lane_header)
        w.writerows([[r[h] for h in lane_header] for r in lane_rows])
    write_json_atomic(run_dir / "timing_check.json", {"checked": bool(timing_checks), "per_seed": timing_checks})
    write_json_atomic(run_dir / "timing.json", {"wall_seconds": round(time.time() - t_start, 2)})
    with ledger_lock(ledger_path):
        append_ledger(ledger_path, {**entry, "status": "completed", "time": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"run_dir": run_dir, "summary": summary, "rows": rows, "protocol": meta}
