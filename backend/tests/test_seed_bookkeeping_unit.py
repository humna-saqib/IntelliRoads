"""Stage-8.5 unit tests (no SUMO): completed obs-v2 experiments recorded in the consumed-range registry; exact reconstruction only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests.fyp_evidence import missing_evidence

from app.evaluation import seeds as ES
from app.evaluation import selection as sel
from app.training import seeds as TS
from app.training.runs import BACKEND

SEL = BACKEND / "selection_runs" / "sel_fyp_s0_obs_v2"
H2H = BACKEND / "evaluation_runs" / "h2h_v1ep400_vs_v2ep240_s0"
V2_RUN = BACKEND / "training_runs" / "fyp_s0_obs_v2"
RECORDED = {"stage_A": (3_000_401, 3_000_410), "stage_B": (3_000_501, 3_000_520), "head_to_head": (3_000_601, 3_000_630)}
FINAL = list(range(4_000_031, 4_000_061))


def test_registry_records_exactly_the_three_completed_ranges_once():
    tagged = {r[2].split("]")[0][4:]: (r[0], r[1]) for r in ES.CONSUMED_VALIDATION_RANGES if r[2].startswith("[v2:")}
    assert tagged == RECORDED
    assert [r[:2] for r in ES.CONSUMED_VALIDATION_RANGES[:5]] == [(3_000_001, 3_000_099), (3_000_101, 3_000_110), (3_000_201, 3_000_220),
                                                                   (3_000_301, 3_000_310), (3_000_311, 3_000_320)]   # earlier records untouched
    for rec in ES.CONSUMED_VALIDATION_RANGES[5:]:
        assert ("selection_runs/sel_fyp_s0_obs_v2/" in rec[2] or "evaluation_runs/h2h_v1ep400_vs_v2ep240_s0/" in rec[2]) and "sha256" in rec[2]
    ES.assert_consumed_registry()


@pytest.mark.parametrize("extra", [(3_000_401, 3_000_410, "[v2:stage_A] again"), (3_000_605, 3_000_606, "other"),
                                   (3_000_700, 3_000_701, "[v2:stage_B] duplicate identity"), (4_000_040, 4_000_041, "final")])
def test_reapplying_or_conflicting_records_are_refused(monkeypatch, extra):
    monkeypatch.setattr(ES, "CONSUMED_VALIDATION_RANGES", ES.CONSUMED_VALIDATION_RANGES + (extra,))
    with pytest.raises(ES.EvalSeedError):
        ES.assert_consumed_registry()


def test_reconstruction_reproduces_the_original_seed_lists():
    for name, (lo, hi) in RECORDED.items():
        assert ES.v2_seeds(name) == list(range(lo, hi + 1))
    ES.assert_v2_seed_plan()


def test_original_stage_a_and_b_plan_is_reproduced_exactly():
    if not (SEL / "plan.json").exists() or not (V2_RUN / "best.json").exists():
        missing_evidence("selection_runs/sel_fyp_s0_obs_v2 and training_runs/fyp_s0_obs_v2")
    stored = json.loads((SEL / "plan.json").read_text())
    plan = sel.build_plan(V2_RUN, incumbent_episode=240, seed_set="obs-v2")
    assert list(plan.stage_a_seeds) == stored["stage_a_seeds"] and list(plan.stage_b_seeds) == stored["stage_b_seeds"]
    assert [list(c) for c in plan.candidates] == [list(c) for c in stored["candidates"]]


def test_original_head_to_head_seed_plan_matches_its_stored_protocol():
    if not (H2H / "protocol.json").exists():
        missing_evidence("evaluation_runs/h2h_v1ep400_vs_v2ep240_s0")
    assert json.loads((H2H / "protocol.json").read_text())["seeds"] == ES.v2_seeds("head_to_head")


@pytest.mark.parametrize("seeds", [list(range(3_000_401, 3_000_411)), list(range(3_000_501, 3_000_521)), list(range(3_000_601, 3_000_631)),
                                   [3_000_405], [3_000_625, 3_000_640], list(range(3_000_600, 3_000_631))])
def test_a_new_experiment_cannot_reuse_consumed_seeds(seeds):
    with pytest.raises(ES.EvalSeedError, match="consumed"):
        ES.assert_fresh_validation_seeds(seeds)


@pytest.mark.parametrize("name,seeds", [("stage_A", list(range(3_000_501, 3_000_511))),          # identity mismatch
                                        ("stage_B", list(range(3_000_401, 3_000_411))),
                                        ("stage_A", list(range(3_000_401, 3_000_410))),           # partial (subset)
                                        ("head_to_head", list(range(3_000_601, 3_000_632))),      # partial overlap beyond the range
                                        ("stage_C", list(range(3_000_401, 3_000_411))),           # unknown identity
                                        ("head_to_head", [3_000_601, 3_000_401])])                # mixes another recorded range
def test_reconstruction_rejects_identity_or_range_mismatch(name, seeds):
    with pytest.raises(ES.EvalSeedError):
        ES.assert_fresh_validation_seeds(seeds, reconstruct=name)


@pytest.mark.parametrize("name,rng", [("stage_A", (3_000_401, 3_000_409)), ("head_to_head", (3_000_601, 3_000_640)),
                                      ("stage_B", (3_000_401, 3_000_420))])
def test_changing_an_approved_range_cannot_reconstruct(monkeypatch, name, rng):
    monkeypatch.setitem(ES.V2_SEED_PLAN, name, rng)
    with pytest.raises(ES.EvalSeedError):
        ES.v2_seeds(name)


def test_reserved_final_seeds_stay_final_only():
    ES.assert_seeds_for_mode(FINAL, "final")
    assert not any(lo <= s <= hi for lo, hi, _ in ES.CONSUMED_VALIDATION_RANGES for s in FINAL)
    for check in (lambda: ES.assert_seeds_for_mode(FINAL, "smoke"), lambda: ES.assert_seeds_for_mode(FINAL, "validation"),
                  lambda: ES.assert_selection_seeds(FINAL[:10], FINAL[10:]), lambda: ES.assert_fresh_validation_seeds(FINAL),
                  lambda: ES.assert_fresh_validation_seeds(FINAL, reconstruct="head_to_head")):
        with pytest.raises(ES.EvalSeedError):
            check()
    for s in FINAL:
        with pytest.raises(TS.SeedError):
            TS.assert_not_protected(s)


def test_v1_selection_seeds_unchanged():
    assert ES.selection_seeds("A", 10) == list(range(3_000_101, 3_000_111))
    assert ES.selection_seeds("B", 20) == list(range(3_000_201, 3_000_221))
