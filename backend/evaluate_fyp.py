"""
IntelliRoads FYP – fair evaluation protocol CLI (Stage 4).

Compares fixed-time (SUMO's own programme), rule-based, actuated-style and (optionally) the validation-selected DQN on
matched seeds, measuring all 16 incoming lanes and every trip identically for every controller.  Output goes to a NEW
directory; tracked route files, existing models/checkpoints and existing evaluation results are never touched.

    python evaluate_fyp.py --plan                                   # print the (smoke) protocol, seeds and runtime estimate – no simulation
    python evaluate_fyp.py --mode final --plan                      # the same for the final protocol
    python evaluate_fyp.py --mode smoke --run-id check              # tiny protocol check (smoke seeds 5,000,001+, never reported)
    python evaluate_fyp.py --mode final --run-id fyp_eval --dqn-run training_runs/fyp_s0 --confirm-final   # the reported evaluation

``--mode`` defaults to ``smoke``: a final evaluation needs both ``--mode final`` and ``--confirm-final`` and is simulated only after
explicit authorisation.  Final seeds already recorded in the ledger are refused; choose fresh ones with ``--seed-base``.  See EVALUATION_PROTOCOL.md.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.evaluation import seeds as ES  # noqa: E402
from app.evaluation.controllers import DQNController  # noqa: E402
from app.evaluation.protocol import (  # noqa: E402
    CONTROLLER_ORDER,
    DEFAULT_EVAL_ROOT,
    EvalProtocol,
    load_validation_selected_checkpoint,
)
from app.evaluation.runner import METRIC_KEYS, PRIMARY_METRIC, evaluate  # noqa: E402

#: wall-clock seconds per 2300 s episode (2100 s + about 200 s drain) on the development container (see EVALUATION_PROTOCOL.md); used only for --plan
EST_SECONDS_PER_EPISODE = {"fixed_time": 14.5, "rule_based": 14.5, "actuated_style": 15.0, "dqn": 15.0}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fair evaluation protocol for the corrected FYP environment.")
    p.add_argument("--mode", choices=["final", "smoke"], default="smoke",
                   help="smoke (default; plumbing check on smoke seeds) or final (the reported evaluation; also needs --confirm-final)")
    p.add_argument("--run-id", default=None, help="name of the NEW output directory (required unless --plan)")
    p.add_argument("--out-root", type=Path, default=None, help=f"parent directory (default {DEFAULT_EVAL_ROOT}; smoke: system temp)")
    p.add_argument("--controllers", nargs="+", choices=list(CONTROLLER_ORDER), default=None)
    p.add_argument("--dqn-run", type=Path, default=None, help="finished training run directory; its validation-selected best.pt is evaluated")
    p.add_argument("--n-seeds", type=int, default=None)
    p.add_argument("--seed-base", type=int, default=None)
    p.add_argument("--warmup-s", type=int, default=None)
    p.add_argument("--measure-s", type=int, default=None)
    p.add_argument("--drain-max-s", type=int, default=None, help="maximum drain after the measured window (default 600; smoke 60)")
    p.add_argument("--decision-interval-s", type=int, default=5)
    p.add_argument("--plan", action="store_true", help="print the protocol and the runtime estimate; simulate nothing")
    p.add_argument("--confirm-final", action="store_true", help="required for --mode final")
    p.add_argument("--allow-repeat-final", action="store_true", help="allow a second final evaluation of the same checkpoint (recorded as a repeat)")
    return p


def resolve(a: argparse.Namespace):
    smoke = a.mode == "smoke"
    protocol = EvalProtocol(warmup_s=a.warmup_s if a.warmup_s is not None else (60 if smoke else 300),
                            measure_s=a.measure_s if a.measure_s is not None else (120 if smoke else 1800),
                            decision_interval_s=a.decision_interval_s, drain_max_s=a.drain_max_s if a.drain_max_s is not None else (60 if smoke else 600),
                            n_seeds=a.n_seeds if a.n_seeds is not None else (2 if smoke else 30), mode=a.mode)
    names = a.controllers or (list(CONTROLLER_ORDER) if a.dqn_run else [c for c in CONTROLLER_ORDER if c != "dqn"])
    seeds = ES.eval_seeds(protocol.n_seeds, a.mode, a.seed_base)
    return protocol, names, seeds


def print_plan(protocol: EvalProtocol, names, seeds) -> None:
    episodes = len(names) * len(seeds)
    scale = (protocol.demand_end_s + min(protocol.drain_max_s, 200)) / 2300.0      # the drain used 160-205 s in the calibration run
    est = sum(EST_SECONDS_PER_EPISODE[n] for n in names) * len(seeds) * scale
    print(f"PROTOCOL ({protocol.mode})")
    print(f"  episode      : {protocol.warmup_s} s warm-up (not measured) + {protocol.measure_s} s measured (new demand stops here, t = {protocol.demand_end_s} s) + drain of at most {protocol.drain_max_s} s (ends earlier when the network is empty; lane metrics not collected), decisions every {protocol.decision_interval_s} s")
    print(f"  seeds        : {len(seeds)} matched seeds {seeds[0]:,}..{seeds[-1]:,} (every controller sees each seed's traffic)")
    print(f"  controllers  : {', '.join(names)}")
    print(f"  measured     : all 16 incoming lanes every second + every trip; primary metric {PRIMARY_METRIC}")
    print(f"  metrics      : {', '.join(METRIC_KEYS[:15])}")
    print(f"  episodes     : {episodes}; estimated wall-clock about {est / 60:.0f} min on the development container (rough; --plan simulates nothing)")


def main(argv: Optional[Sequence[str]] = None) -> Optional[dict]:
    a = build_parser().parse_args(argv)
    protocol, names, seeds = resolve(a)
    if a.plan:
        print_plan(protocol, names, seeds)
        return None
    if not a.run_id:
        raise SystemExit("--run-id is required (a new output directory is created)")
    if a.mode == "final" and not a.confirm_final:
        raise SystemExit("a final evaluation needs --confirm-final (it is the reported result); nothing was loaded or simulated")
    if a.mode == "final" and a.out_root is not None and Path(a.out_root).resolve() != Path(DEFAULT_EVAL_ROOT).resolve():
        raise SystemExit(f"a final evaluation always writes to {DEFAULT_EVAL_ROOT} (its ledger guards repeats and seed reuse); "
                         f"--out-root {a.out_root} is refused; nothing was loaded or simulated")
    dqn = None
    if "dqn" in names:
        if not a.dqn_run:
            raise SystemExit("the dqn controller needs --dqn-run <training run directory>")
        agent, info = load_validation_selected_checkpoint(a.dqn_run)
        dqn = DQNController(agent, info)
    out_root = a.out_root or (Path(tempfile.gettempdir()) / "intelliroads_eval_smoke" if a.mode == "smoke" else DEFAULT_EVAL_ROOT)
    banner = "SMOKE PROTOCOL CHECK (results are meaningless)" if a.mode == "smoke" else "FINAL EVALUATION"
    print(f"[{banner}] run '{a.run_id}' -> {out_root / a.run_id}")
    print_plan(protocol, names, seeds)
    res = evaluate(protocol, names, seeds, out_root, a.run_id, dqn=dqn, confirm_final=a.confirm_final, allow_repeat_final=a.allow_repeat_final,
                   argv=list(argv) if argv is not None else sys.argv)
    print(f"[{banner}] done -> {res['run_dir']}")
    return res


if __name__ == "__main__":
    main()
