"""Stage-6 unit tests (no SUMO): the additive obs-v2 seed configuration and its compatibility with the existing seed registry."""

from __future__ import annotations

import pytest

from app.evaluation import seeds as ES
from app.training import seeds as TS


def test_v2_ranges_are_exactly_the_approved_ones():
    assert ES.v2_seeds("stage_A") == list(range(3_000_401, 3_000_411))
    assert ES.v2_seeds("stage_B") == list(range(3_000_501, 3_000_521))
    assert ES.v2_seeds("head_to_head") == list(range(3_000_601, 3_000_631))
    assert ES.FRESH_FINAL_RESERVED == (4_000_031, 4_000_060)
    ES.assert_v2_seed_plan()
    with pytest.raises(ES.EvalSeedError):
        ES.v2_seeds("stage_C")


def test_v2_ranges_are_pairwise_disjoint_and_disjoint_from_consumed_and_final_seeds():
    a, b, h = (set(ES.v2_seeds(n)) for n in ("stage_A", "stage_B", "head_to_head"))
    assert not (a & b or a & h or b & h)
    earlier = {s for lo, hi, why in ES.CONSUMED_VALIDATION_RANGES if not why.startswith("[v2:") for s in range(lo, hi + 1)}
    assert not (a | b | h) & earlier                                           # disjoint from everything consumed before obs-v2
    assert all(s < 4_000_000 for s in a | b | h)
    lo, hi = ES.FRESH_FINAL_RESERVED
    assert not any(lo <= s <= hi for s in a | b | h)


@pytest.mark.parametrize("seed,why", [(3_000_101, "consumed"), (3_000_215, "consumed"), (3_000_305, "consumed"), (3_000_320, "consumed"),
                                      (3_000_005, "proxy-validation"), (2_000_001, "TRAINING"), (5_000_001, "SMOKE"),
                                      (4_000_031, "FINAL"), (4_000_060, "FINAL"), (4_000_001, "FINAL")])
def test_fresh_seed_check_refuses_consumed_training_smoke_and_final_seeds(seed, why):
    with pytest.raises(ES.EvalSeedError, match=why):
        ES.assert_fresh_validation_seeds([seed])


def test_overlap_and_duplicate_rejection():
    with pytest.raises(ES.EvalSeedError, match="duplicate"):
        ES.assert_fresh_validation_seeds([3_000_401, 3_000_401])
    original = dict(ES.V2_SEED_PLAN)
    try:
        ES.V2_SEED_PLAN["head_to_head"] = (3_000_410, 3_000_412)              # overlaps stage A (recorded as consumed since Stage 8.5)
        with pytest.raises(ES.EvalSeedError, match="consumed"):
            ES.assert_v2_seed_plan()
        ES.V2_SEED_PLAN["head_to_head"] = (3_000_318, 3_000_322)              # overlaps the consumed decision-logging seeds
        with pytest.raises(ES.EvalSeedError, match="consumed"):
            ES.assert_v2_seed_plan()
    finally:
        ES.V2_SEED_PLAN.clear(); ES.V2_SEED_PLAN.update(original)
    ES.assert_v2_seed_plan()


@pytest.mark.parametrize("seed", [3_000_401, 3_000_410, 3_000_501, 3_000_520, 3_000_601, 3_000_630])
def test_reserved_v2_seeds_are_refused_by_training_and_its_validation(seed):
    with pytest.raises(TS.SeedError, match="protected"):
        TS.assert_not_protected(seed)
    with pytest.raises(TS.SeedError):
        TS.val_seeds(seed - TS.VAL_SEED_BASE)                                  # a --val-n large enough to reach the range is refused


def test_existing_seed_behaviour_is_unchanged():
    assert TS.TRAIN_SEED_BASE == 2_000_000 and TS.VAL_SEED_BASE == 3_000_000
    assert [TS.train_seed(e) for e in (1, 400)] == [2_000_001, 2_000_400]
    assert TS.val_seeds(5) == [3_000_001, 3_000_002, 3_000_003, 3_000_004, 3_000_005]
    assert TS.PROTECTED_RANGES[:3] == ((1_000_000, 1_999_999, "legacy evaluation seeds (evaluate_controllers.py)"),
                                       (4_000_000, 4_999_999, "reserved for the final evaluation"),
                                       (5_000_000, 5_999_999, "evaluation-protocol smoke-check seeds (never used for training or selection)"))
    for s in (0, 999_999, 2_000_000, 2_000_400, 3_000_400, 3_000_411, 3_000_631, 3_999_999, 6_000_000):
        assert TS.assert_not_protected(s) == s                                 # neighbours of the new ranges stay allowed
    assert ES.selection_seeds("A", 10) == list(range(3_000_101, 3_000_111))     # existing selection stages unchanged
    assert ES.selection_seeds("B", 20) == list(range(3_000_201, 3_000_221))
    assert ES.SELECTION_RANGE == (3_000_100, 3_999_999) and ES.FINAL_EVAL_RANGE == (4_000_000, 4_999_999)
    assert ES.eval_seeds(30, "final") == list(range(4_000_001, 4_000_031))
