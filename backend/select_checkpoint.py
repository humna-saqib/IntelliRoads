"""Two-stage checkpoint selection on trip-based VALIDATION waiting time (Stage 5).

    python select_checkpoint.py --run-dir training_runs/fyp_s0 --plan                                     # print the plan, simulate nothing
    python select_checkpoint.py --run-dir training_runs/fyp_s0 --run-id sel_fyp_s0 --confirm-selection     # run it (hundreds of SUMO episodes)

Only validation seeds 3,000,100+ are used (stage A: 3,000,101..; stage B: 3,000,201..).  Final-evaluation seeds (4,000,000-4,999,999, in particular the
reserved 4,000,031-4,000,060), smoke, training and proxy-validation seeds are refused.  The final-evaluation ledger, ``best.json`` / ``best.pt`` and every
training-run file stay untouched; the output is a new ``selection_runs/<run-id>/``.  See EVALUATION_PROTOCOL.md, section 9.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.evaluation import selection as sel  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Two-stage checkpoint selection on trip-based validation waiting time.")
    p.add_argument("--run-dir", type=Path, required=True, help="finished training run (e.g. training_runs/fyp_s0)")
    p.add_argument("--run-id", default=None, help="name of the NEW output directory (required unless --plan)")
    p.add_argument("--out-root", type=Path, default=sel.DEFAULT_SELECTION_ROOT, help=f"parent directory (default {sel.DEFAULT_SELECTION_ROOT})")
    p.add_argument("--stage-a-n", type=int, default=sel.STAGE_A_N)
    p.add_argument("--stage-b-n", type=int, default=sel.STAGE_B_N)
    p.add_argument("--top-k", type=int, default=sel.TOP_K)
    p.add_argument("--plan", action="store_true", help="print the plan and the runtime estimate; simulate nothing")
    p.add_argument("--confirm-selection", action="store_true", help="required to run the selection")
    return p


def print_plan(plan: sel.SelectionPlan) -> None:
    a, b = plan.n_episodes()
    print("CHECKPOINT-SELECTION PLAN (validation seeds only)")
    print(f"  run            : {plan.run_dir}   incumbent: episode {plan.incumbent_episode} (current best.pt)")
    print(f"  candidates     : {len(plan.candidates)} periodic checkpoints, episodes {plan.candidates[0][0]}..{plan.candidates[-1][0]}")
    print(f"  stage A        : {len(plan.stage_a_seeds)} seeds {plan.stage_a_seeds[0]:,}..{plan.stage_a_seeds[-1]:,}  -> {a} episodes (screening, not used in the decision)")
    print(f"  stage B        : {len(plan.stage_b_seeds)} seeds {plan.stage_b_seeds[0]:,}..{plan.stage_b_seeds[-1]:,}  -> at most {b} episodes ({plan.top_k} best eligible challengers + incumbent)")
    print(f"  measurement    : {dict(plan.protocol)} ; primary metric {sel.PRIMARY}")
    print(f"  rule           : replace the incumbent only if a challenger is eligible and its Bonferroni-adjusted (alpha {plan.alpha}/k) paired interval vs the incumbent is entirely below 0")
    print(f"  eligibility    : no drain exhausted, no unfinished/not-inserted trips, mean completion >= {plan.min_completion}")
    print(f"  reserved       : final seeds 4,000,031-4,000,060 and every 4,xxx,xxx seed are refused; ledger untouched")
    print(f"  plan sha256    : {plan.sha256()}")
    print(f"  expected time  : about {(a + b) * sel.EST_SECONDS_PER_EPISODE / 60:.0f} min at {sel.EST_SECONDS_PER_EPISODE} s per episode (upper bound)")


def main(argv: Optional[Sequence[str]] = None):
    a = build_parser().parse_args(argv)
    plan = sel.build_plan(a.run_dir, a.stage_a_n, a.stage_b_n, a.top_k)
    if a.plan:
        print_plan(plan)
        return None
    if not a.run_id:
        raise SystemExit("--run-id is required (a new output directory is created)")
    print_plan(plan)
    res = sel.run_selection(plan, a.out_root, a.run_id, confirm=a.confirm_selection)
    d = res["decision"]
    print(f"[VALIDATION-SEED SELECTION] selected episode {d['selected_episode']} (replaced incumbent: {d['replaced']}) -> {res['out_dir']}")
    return res


if __name__ == "__main__":
    main()
