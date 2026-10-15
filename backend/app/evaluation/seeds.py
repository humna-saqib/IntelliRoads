"""Matched evaluation seeds (Stage 4).

Ranges (all disjoint; see ``app.training.seeds`` for training / validation):

* training                  ``2,000,001 ...``
* validation                ``3,000,001 ...``   (checkpoint selection only)
* **final evaluation**      ``4,000,001 ... 4,999,999``   – reported results, simulated only after explicit authorisation
* protocol smoke checks     ``5,000,001 ... 5,999,999``   – plumbing / unit tests; results are never reported
* legacy evaluation         ``1,000,001 ... 1,999,999``   (old ``evaluate_controllers.py``; refused by the new protocol)

*Matched seeds*: seed ``k`` defines both the generated demand and SUMO's own random seed, so every controller is
evaluated on the identical traffic of seed ``k`` (paired design).  Final-evaluation seeds are not used by training,
validation or checkpoint selection; the runner refuses a final run on any other range and a smoke run on the final range.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

FINAL_EVAL_RANGE = (4_000_000, 4_999_999)
SMOKE_RANGE = (5_000_000, 5_999_999)
FINAL_EVAL_BASE = 4_000_000
SMOKE_BASE = 5_000_000

# ---- checkpoint-selection seeds (second-stage, trip-based validation; see EVALUATION_PROTOCOL.md section 9) -------------
#: Seeds of the selection tool: validation territory (3,xxx,xxx) *above* the 99 seeds that ``train_dqn.py`` validation may use
#: (3,000,001 ... 3,000,099), so the 20 proxy-validation checkpoints are re-ranked on traffic nobody selected on before.
SELECTION_RANGE = (3_000_100, 3_999_999)
STAGE_A_BASE = 3_000_100          # screening seeds   3,000,101 ... 3,000,199  (at most 99)
STAGE_B_BASE = 3_000_200          # confirmation seeds 3,000,201 ... 3,000,299 (at most 99), disjoint from stage A
SELECTION_STAGES = {"A": STAGE_A_BASE, "B": STAGE_B_BASE}
MAX_STAGE_SEEDS = 99
#: fresh final-evaluation seeds kept back for a later final evaluation of a (possibly new) checkpoint: never used for selection
FRESH_FINAL_RESERVED = (4_000_031, 4_000_060)


class EvalSeedError(ValueError):
    pass


def _check(seed: int, rng, what: str) -> int:
    if not rng[0] <= seed <= rng[1]:
        raise EvalSeedError(f"seed {seed} is outside the {what} range {rng[0]:,}-{rng[1]:,}")
    return seed


def eval_seeds(n: int, mode: str, base: int | None = None) -> List[int]:
    """``n`` consecutive matched seeds of the given ``mode`` ('final' or 'smoke')."""
    if n < 1:
        raise EvalSeedError("need at least one evaluation seed")
    if mode == "final":
        rng, default = FINAL_EVAL_RANGE, FINAL_EVAL_BASE
    elif mode == "smoke":
        rng, default = SMOKE_RANGE, SMOKE_BASE
    else:
        raise EvalSeedError("mode must be 'final' or 'smoke'")
    start = default if base is None else base
    return [_check(start + i, rng, f"{mode}-evaluation") for i in range(1, n + 1)]


def assert_seeds_for_mode(seeds: List[int], mode: str) -> None:
    rng = FINAL_EVAL_RANGE if mode == "final" else SMOKE_RANGE if mode == "smoke" else SELECTION_RANGE if mode == "validation" else None
    if rng is None:
        raise EvalSeedError("mode must be 'final', 'smoke' or 'validation'")
    if len(set(seeds)) != len(seeds):
        raise EvalSeedError("duplicate evaluation seeds")
    for s in seeds:
        _check(int(s), rng, f"{mode}-evaluation")


# ------------------------------------------------------------------ checkpoint-selection seeds
def selection_seeds(stage: str, n: int) -> List[int]:
    """``n`` consecutive seeds of selection stage ``'A'`` (screening) or ``'B'`` (confirmation); the two stages never overlap."""
    if stage not in SELECTION_STAGES:
        raise EvalSeedError("selection stage must be 'A' or 'B'")
    if not 1 <= n <= MAX_STAGE_SEEDS:
        raise EvalSeedError(f"a selection stage uses between 1 and {MAX_STAGE_SEEDS} seeds, got {n}")
    base = SELECTION_STAGES[stage]
    return [assert_selection_seed(base + i) for i in range(1, n + 1)]


def assert_selection_seed(seed: int) -> int:
    """Refuse every seed that is not a fresh selection seed, saying *why* (training / smoke / final / legacy / proxy-validation)."""
    seed = int(seed)
    if SELECTION_RANGE[0] <= seed <= SELECTION_RANGE[1]:
        return seed
    if FINAL_EVAL_RANGE[0] <= seed <= FINAL_EVAL_RANGE[1]:
        raise EvalSeedError(f"seed {seed} is a FINAL-evaluation seed ({FINAL_EVAL_RANGE[0]:,}-{FINAL_EVAL_RANGE[1]:,}); never used for selection"
                            f" (4,000,031-4,000,060 are reserved for the next final evaluation)")
    if SMOKE_RANGE[0] <= seed <= SMOKE_RANGE[1]:
        raise EvalSeedError(f"seed {seed} is a SMOKE seed ({SMOKE_RANGE[0]:,}-{SMOKE_RANGE[1]:,}); not a selection seed")
    if 2_000_000 <= seed <= 2_999_999:
        raise EvalSeedError(f"seed {seed} is a TRAINING seed (2,000,000-2,999,999); not a selection seed")
    if 3_000_000 <= seed < SELECTION_RANGE[0]:
        raise EvalSeedError(f"seed {seed} belongs to the proxy-validation seeds of train_dqn.py (3,000,000-3,000,099) already used for "
                            f"checkpoint selection; selection seeds start at {SELECTION_RANGE[0]:,}")
    raise EvalSeedError(f"seed {seed} is outside the selection range {SELECTION_RANGE[0]:,}-{SELECTION_RANGE[1]:,}")


def assert_selection_seeds(stage_a: List[int], stage_b: List[int]) -> None:
    """Both stages must consist of selection seeds only, without duplicates, and must not overlap each other."""
    for name, seeds in (("A", stage_a), ("B", stage_b)):
        if not seeds:
            raise EvalSeedError(f"stage {name} has no seeds")
        if len(set(seeds)) != len(seeds):
            raise EvalSeedError(f"stage {name} has duplicate seeds")
        for sd in seeds:
            assert_selection_seed(sd)
    if set(stage_a) & set(stage_b):
        raise EvalSeedError("stage A and stage B seeds overlap; the confirmation stage needs independent seeds")


# ------------------------------------------------------------------ Stage 6: seed plan for the obs-v2 workflow (configuration only)
#: validation-territory seed ranges already consumed by earlier work (never reused for a new selection or comparison)
CONSUMED_VALIDATION_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (3_000_001, 3_000_099, "train_dqn.py proxy validation (fyp_s0 used 3,000,001-3,000,005) and validation diagnostic"),
    (3_000_101, 3_000_110, "fyp_s0 selection stage A (+ integration check 3,000,101)"),
    (3_000_201, 3_000_220, "fyp_s0 selection stage B (+ integration check 3,000,201)"),
    (3_000_301, 3_000_310, "minimum-green sweep diagnostic"),
    (3_000_311, 3_000_320, "decision-logging diagnostic"),
    # Stage 8.5 bookkeeping: completed obs-v2 experiments, verified against their stored outputs.  "[v2:<name>]" is the identity
    # under which ``v2_seeds(<name>)`` may reconstruct exactly this range (and nothing else may use it).
    (3_000_401, 3_000_410, "[v2:stage_A] obs-v2 selection stage A (screening) of fyp_s0_obs_v2; selection_runs/sel_fyp_s0_obs_v2/ "
                           "(plan.json sha256 2ba6441c287e3e04..., stage_a.csv 00fe5a82f947d25c..., decision.json 752622976319b6ec...)"),
    (3_000_501, 3_000_520, "[v2:stage_B] obs-v2 selection stage B (confirmation) of fyp_s0_obs_v2; selection_runs/sel_fyp_s0_obs_v2/ "
                           "(plan.json sha256 2ba6441c287e3e04..., stage_b.csv c0ed03dc1f0cb846..., decision.json 752622976319b6ec...)"),
    (3_000_601, 3_000_630, "[v2:head_to_head] v1 ep400 vs obs-v2 ep240 head-to-head; evaluation_runs/h2h_v1ep400_vs_v2ep240_s0/ "
                           "(protocol.json sha256 9dfdc027a42b268d..., episodes.csv 39aeb4989b3eb2d9..., summary.json caff6a450ac10889...)"),
)
#: fresh ranges for the obs-v2 workflow (inclusive); they are additionally refused by training (app.training.seeds.PROTECTED_RANGES)
V2_STAGE_A_RANGE = (3_000_401, 3_000_410)
V2_STAGE_B_RANGE = (3_000_501, 3_000_520)
V2_HEAD_TO_HEAD_RANGE = (3_000_601, 3_000_630)
V2_SEED_PLAN: Dict[str, Tuple[int, int]] = {"stage_A": V2_STAGE_A_RANGE, "stage_B": V2_STAGE_B_RANGE, "head_to_head": V2_HEAD_TO_HEAD_RANGE}

#: identity of the recorded obs-v2 selection (selection_runs/sel_fyp_s0_obs_v2/plan.json, plan hash 4d2d68cb...): the consumed stage-A/B
#: seeds may be re-derived only for exactly this run - same run directory name, incumbent and periodic checkpoint SHA-256s.
V2_SELECTION_RECORD: Dict[str, object] = {
    "run_name": "fyp_s0_obs_v2",
    "incumbent_episode": 240,
    "plan_sha256": "4d2d68cb0809dde01a57a72ad2646a6487808fb728aaec4f8a02c53db1b118d0",
    "candidate_sha256": {
        20: "f743ee2ad4ec9aeda362b332a970a27fb5bc4a1fe671d8473a5787d1a2d65263",
        40: "6edb25c495d77336a6be18e0f03c5fcc13159f4ba7d1bf037b0c0ef129ef505c",
        60: "199103721aa68db6c95f817872065e999e67e35342a03b368a680d12314c034c",
        80: "0871819839886de3d101a7a9f92691b5ee28541b841aa32dcce6fc7df82e0109",
        100: "bdee89142505f323c9dfd63fefd64bc4e337b63a20247cc7139046b9a5ef238c",
        120: "08418a34746129bc9f3552188e35848b5d5a07b5478aa649baadd68ed6fc2c73",
        140: "32c8ac271d28336797da66979a2088f88f62ce4980f19cb9603f7e900e5c442e",
        160: "512fe01d4ac63c8495ba9c814e487014709224dc804d559cd0f5b24dc8d759db",
        180: "00e8752e5bf394f2f2cc2e8328457f252f39ea1bd3938b1fc82504839dfa02a5",
        200: "6d71b799bbe22b30cc77fb8e77d2ba876542281c5f7156b09d4dd90dc400d9aa",
        220: "bfe6a7ed64b73f238babae2d6eca91cdfe3f89bda420a6be84fdc803a01c6148",
        240: "7a30427d4e6e2b1de842dec397ba16e3633f7c0a79610decea626805c750fb14",
        260: "8a7b7b532716f776c0e00398f04ae5eec7440660b7dafff7ccaa4256fab4c504",
        280: "cd7aef52b28918ab508e3070c73bd4175b4f59163205daea7ff6a878e0745da6",
        300: "9fe3296781a3ae9d8799610d7a0e1b8621b3704b68df5510773dc5ae48ddc5d1",
        320: "d566e7eaa5b6df1d5f00310ada2454bd9d46c7c09e55a3c0ee01a123c39093e9",
        340: "14296f30100738fb4986be63bd683fc6eab6536816f1f8150cc98bfb1ea62f51",
        360: "4122fc5fa68de0312d84fd5e9029068726e713fcb8e307c1ea38c4b56c43dbae",
        380: "06a9fd7b157e82311e02daa3f3b30d19dd9ae7ffc5db58cc7baa04fbc0d2a2a9",
        400: "fc58b00f5ba607255092b88d24c9fb58a17fe7d406095c6c3abf571b89f2a547",
    },
}


def assert_v2_selection_identity(run_name: str, incumbent_episode: int, candidates: Dict[int, str]) -> None:
    """The obs-v2 stage-A/B seeds are consumed: only the recorded selection itself may be reconstructed. Any other run (or a changed
    checkpoint, a different incumbent) is refused - a new obs-v2 selection needs fresh, unconsumed seeds."""
    rec = V2_SELECTION_RECORD
    problems = []
    if run_name != rec["run_name"]:
        problems.append(f"run {run_name!r} is not the recorded run {rec['run_name']!r}")
    if incumbent_episode != rec["incumbent_episode"]:
        problems.append(f"incumbent episode {incumbent_episode} is not the recorded {rec['incumbent_episode']}")
    if dict(candidates) != dict(rec["candidate_sha256"]):
        problems.append("the periodic checkpoints (episodes or SHA-256) differ from the recorded plan")
    if problems:
        raise EvalSeedError("the obs-v2 selection seeds 3,000,401-410 / 3,000,501-520 were consumed by the recorded selection "
                            f"(plan {rec['plan_sha256'][:12]}); they may only reconstruct that experiment: " + "; ".join(problems)
                            + ". A new selection needs fresh, unconsumed seeds.")


def v2_seeds(name: str) -> List[int]:
    """The seeds of one obs-v2 range (``stage_A``, ``stage_B`` or ``head_to_head``), validated."""
    if name not in V2_SEED_PLAN:
        raise EvalSeedError(f"unknown obs-v2 seed range {name!r}; known: {sorted(V2_SEED_PLAN)}")
    lo, hi = V2_SEED_PLAN[name]
    seeds = list(range(lo, hi + 1))
    assert_fresh_validation_seeds(seeds, reconstruct=name)
    return seeds


def _consumed_record(name: str):
    tagged = [r for r in CONSUMED_VALIDATION_RANGES if r[2].startswith(f"[v2:{name}] ")]
    if len(tagged) > 1:
        raise EvalSeedError(f"consumed-range registry has {len(tagged)} records for {name!r}")
    return tagged[0] if tagged else None


def assert_consumed_registry() -> None:
    """The consumed-range registry itself: well-formed, pairwise disjoint, one record per identity, clear of the reserved final seeds."""
    seen: Dict[int, str] = {}
    tags = [r[2].split("]")[0] for r in CONSUMED_VALIDATION_RANGES if r[2].startswith("[v2:")]
    if len(set(tags)) != len(tags):
        raise EvalSeedError("duplicate identity in the consumed-range registry")
    for lo, hi, why in CONSUMED_VALIDATION_RANGES:
        if not lo <= hi:
            raise EvalSeedError(f"malformed consumed range {lo}-{hi}")
        for sd in range(lo, hi + 1):
            if sd in seen:
                raise EvalSeedError(f"seed {sd} is recorded as consumed twice ({seen[sd]} / {why})")
            seen[sd] = why
    flo, fhi = FRESH_FINAL_RESERVED
    if any(flo <= sd <= fhi for sd in seen):
        raise EvalSeedError("a consumed range overlaps the reserved final seeds")


def assert_fresh_validation_seeds(seeds: List[int], reconstruct: str | None = None) -> None:
    """Every seed must be a selection-range seed (refuses training / smoke / final / proxy-validation, see ``assert_selection_seed``),
    must not belong to an already consumed range, and must be unique.

    ``reconstruct=<name>`` (used only by ``v2_seeds``) re-derives a recorded experiment: the one consumed record tagged ``[v2:<name>]``
    is allowed only if ``seeds`` is exactly its full range and that range is the approved ``V2_SEED_PLAN[name]``; every other
    consumed range is still refused."""
    if len(set(seeds)) != len(seeds):
        raise EvalSeedError("duplicate seeds")
    own = _consumed_record(reconstruct) if reconstruct is not None else None
    for sd in seeds:
        assert_selection_seed(sd)
        for rec in CONSUMED_VALIDATION_RANGES:
            lo, hi, why = rec
            if rec is not own and lo <= int(sd) <= hi:
                raise EvalSeedError(f"seed {sd} was already consumed ({why})")
    if own is not None and ((own[0], own[1]) != tuple(V2_SEED_PLAN.get(reconstruct, ())) or
                            sorted(int(s) for s in seeds) != list(range(own[0], own[1] + 1))):
        raise EvalSeedError(f"seeds overlap the consumed range {own[0]:,}-{own[1]:,} of {reconstruct!r}, "
                            f"which may only be reconstructed exactly")


def assert_v2_seed_plan() -> None:
    """The obs-v2 ranges are fresh, pairwise disjoint, and disjoint from the reserved fresh final seeds."""
    seen: Dict[int, str] = {}
    for name in V2_SEED_PLAN:
        for sd in v2_seeds(name):
            if sd in seen:
                raise EvalSeedError(f"seed {sd} is in both {seen[sd]} and {name}")
            seen[sd] = name
    lo, hi = FRESH_FINAL_RESERVED
    if any(lo <= sd <= hi for sd in seen):
        raise EvalSeedError("an obs-v2 validation range overlaps the reserved final seeds")
