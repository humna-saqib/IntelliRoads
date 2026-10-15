"""Stage-7 unit tests (no SUMO): the obs-v2 seed set of the selection tool, its guards, and unchanged v1 behaviour."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests.fyp_evidence import missing_evidence

from app.evaluation import seeds as ES
from app.evaluation import selection as sel
from app.training.runs import BACKEND

V1_RUN, V2_RUN = BACKEND / "training_runs" / "fyp_s0", BACKEND / "training_runs" / "fyp_s0_obs_v2"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _fake_run(tmp_path, obs="fyp-obs-v2", best_ep=240, episodes=(20, 40, 240)):
    d = tmp_path / "run"; d.mkdir()
    (d / "config.json").write_text(json.dumps({"obs_version": obs}))
    for e in episodes:
        (d / f"ckpt_ep{e:04d}.pt").write_bytes(f"w{e}".encode())
    (d / "best.json").write_text(json.dumps({"episode": best_ep, "file": f"ckpt_best_ep{best_ep:04d}.pt", "score": 1.0}))
    return d


def _as_recorded(monkeypatch, run, incumbent=240):
    """Make a fake run *the* recorded obs-v2 experiment (Stage 9 identity guard), so the seed-range guards behind it can be tested."""
    rec = {"run_name": run.name, "incumbent_episode": incumbent, "plan_sha256": "0" * 64,
           "candidate_sha256": {int(p.name[7:11]): sha(p) for p in sorted(run.glob("ckpt_ep*.pt"))}}
    monkeypatch.setattr(ES, "V2_SELECTION_RECORD", rec)
    return run


def test_v1_plan_is_unchanged_and_reproduces_the_recorded_fyp_s0_plan_hash():
    if not (V1_RUN / "best.json").exists() or not (BACKEND / "selection_runs" / "sel_fyp_s0" / "plan.json").exists():
        missing_evidence("training_runs/fyp_s0 and selection_runs/sel_fyp_s0")
    recorded = json.loads((BACKEND / "selection_runs" / "sel_fyp_s0" / "plan.json").read_text())["plan_sha256"]
    plan = sel.build_plan(V1_RUN)                                               # default = established v1 seed set
    assert plan.sha256() == recorded == "a26fa3e9470e575a02a500b7698ababb664f826fa3c67b3071b905b801135686"
    assert plan.stage_a_seeds == tuple(range(3_000_101, 3_000_111)) and plan.stage_b_seeds == tuple(range(3_000_201, 3_000_221))


def test_obs_v2_plan_uses_exactly_the_approved_seeds_and_the_run_checkpoint_hashes():
    if not (V2_RUN / "best.json").exists():
        missing_evidence("training_runs/fyp_s0_obs_v2")
    plan = sel.build_plan(V2_RUN, incumbent_episode=240, seed_set="obs-v2")
    assert plan.stage_a_seeds == tuple(range(3_000_401, 3_000_411)) and plan.stage_b_seeds == tuple(range(3_000_501, 3_000_521))
    assert plan.incumbent_episode == 240 and [c[0] for c in plan.candidates] == list(range(20, 401, 20))
    assert all(h == sha(V2_RUN / f) for _, f, h in plan.candidates)
    used = set(plan.stage_a_seeds) | set(plan.stage_b_seeds)
    assert not used & set(ES.v2_seeds("head_to_head"))
    assert not any(4_000_000 <= s <= 5_999_999 for s in used)
    with pytest.raises(sel.SelectionError, match="selects episode 240"):
        sel.build_plan(V2_RUN, seed_set="obs-v2")                               # default incumbent 400 does not match best.json


def test_obs_v2_seed_set_is_refused_for_a_v1_run_and_for_other_stage_sizes(tmp_path, monkeypatch):
    with pytest.raises(sel.SelectionError, match="reserved for fyp-obs-v2"):
        sel.build_plan(_fake_run(tmp_path, obs=None, best_ep=240), incumbent_episode=240, seed_set="obs-v2")
    d = tmp_path / "x"; d.mkdir()
    run = _as_recorded(monkeypatch, _fake_run(d))
    for a, b in ((5, 20), (10, 19), (11, 20)):
        with pytest.raises(sel.SelectionError, match="fixes 10 stage-A and 20 stage-B"):
            sel.build_plan(run, stage_a_n=a, stage_b_n=b, incumbent_episode=240, seed_set="obs-v2")
    with pytest.raises(sel.SelectionError, match="unknown seed set"):
        sel.build_plan(run, incumbent_episode=240, seed_set="v3")
    p = sel.build_plan(run, incumbent_episode=240, seed_set="obs-v2")
    assert p.stage_a_seeds[0] == 3_000_401 and p.stage_b_seeds[-1] == 3_000_520


@pytest.mark.parametrize("bad,match", [({"stage_A": (3_000_501, 3_000_510)}, "consumed"),      # overlaps stage B (recorded as consumed since Stage 8.5)
                                       ({"stage_B": (3_000_311, 3_000_330)}, "consumed"),      # previously consumed seeds
                                       ({"stage_A": (3_000_051, 3_000_060)}, "proxy-validation"),
                                       ({"stage_B": (4_000_031, 4_000_050)}, "FINAL"),         # reserved final seeds
                                       ({"stage_A": (5_000_001, 5_000_010)}, "SMOKE")])
def test_plan_rejects_overlapping_consumed_and_reserved_seed_ranges(tmp_path, monkeypatch, bad, match):
    plan = dict(ES.V2_SEED_PLAN); plan.update(bad)
    monkeypatch.setattr(ES, "V2_SEED_PLAN", plan)
    with pytest.raises(ES.EvalSeedError, match=match):
        sel.build_plan(_as_recorded(monkeypatch, _fake_run(tmp_path)), incumbent_episode=240, seed_set="obs-v2")


def test_selection_with_the_obs_v2_plan_touches_only_its_assigned_seeds(tmp_path, monkeypatch):
    run = _as_recorded(monkeypatch, _fake_run(tmp_path, episodes=(20, 40, 60, 240)))
    plan = sel.build_plan(run, incumbent_episode=240, seed_set="obs-v2")
    used = []

    class Agent:
        pass

    class Runner:
        def __init__(self, protocol):
            assert protocol.mode == "validation"

        def run(self, controller, seed):
            used.append((controller.info["selected_episode"], seed))
            w = 20.0 + (seed % 5)
            return {sel.PRIMARY: w, "wait_per_vehicle_completed_s": w, "travel_time_completed_s": 140.0, "mean_queue_per_lane": 0.8,
                    "throughput_veh_per_h": 2500.0, "trips_scheduled": 1000.0, "trips_completed": 1000.0, "trips_unfinished": 0.0,
                    "trips_not_inserted": 0.0, "completion_rate": 1.0, "drain_s_used": 150.0, "drain_exhausted": 0, "decisions": 450,
                    "actions_switch": 300, "actions_extend": 50, "actions_reduce": 5, "phases_completed": 800.0, "wall_s": 0.0}

        def close(self):
            pass

    monkeypatch.setattr(sel, "load_candidate_checkpoint",
                        lambda rd, f: (Agent(), {"selected_episode": int(f[7:11]), "obs_version": "fyp-obs-v2", "detector_range_m": 40.0}))
    monkeypatch.setattr(sel, "load_validation_selected_checkpoint", lambda rd: (Agent(), {"sha256": "x"}))
    monkeypatch.setattr(sel, "weights_equal", lambda a, b: True)
    monkeypatch.setattr(sel, "DQNController", lambda agent, info: type("C", (), {"info": info})())
    res = sel.run_selection(plan, tmp_path / "out", "s", confirm=True, make_runner=Runner, progress=lambda s: None)
    a_seeds = {s for e, s in used if s in plan.stage_a_seeds}; b_seeds = {s for e, s in used if s in plan.stage_b_seeds}
    assert {s for _, s in used} == set(range(3_000_401, 3_000_411)) | set(range(3_000_501, 3_000_521))
    assert len(a_seeds) == 10 and len(b_seeds) == 20 and res["decision"]["selected_episode"] == 240
    assert json.loads((tmp_path / "out" / "s" / "plan.json").read_text())["stage_a_seeds"] == list(range(3_000_401, 3_000_411))


def test_build_plan_defaults_keep_the_v1_seed_set():
    import inspect
    p = inspect.signature(sel.build_plan).parameters
    assert p["seed_set"].default == "v1" and p["incumbent_episode"].default == 400 and sel.SEED_SETS == ("v1", "obs-v2")


# ------------------------------------------------------------------ Stage 9 (R2): consumed obs-v2 seeds only for the recorded experiment
def test_recorded_identity_matches_the_stored_plan():
    stored = BACKEND / "selection_runs" / "sel_fyp_s0_obs_v2" / "plan.json"
    rec = ES.V2_SELECTION_RECORD
    assert rec["run_name"] == "fyp_s0_obs_v2" and rec["incumbent_episode"] == 240 and len(rec["candidate_sha256"]) == 20
    assert rec["candidate_sha256"][240] == "7a30427d4e6e2b1de842dec397ba16e3633f7c0a79610decea626805c750fb14"
    if stored.exists():                                                         # evidence check when the outputs are present
        p = json.loads(stored.read_text())
        assert p["plan_sha256"] == rec["plan_sha256"]
        assert {c[0]: c[2] for c in p["candidates"]} == rec["candidate_sha256"]


def test_a_new_obs_v2_run_cannot_reuse_the_consumed_selection_seeds(tmp_path):
    run = _fake_run(tmp_path)                                                   # a valid obs-v2 run that is not the recorded experiment
    with pytest.raises(ES.EvalSeedError, match="consumed by the recorded selection"):
        sel.build_plan(run, incumbent_episode=240, seed_set="obs-v2")


@pytest.mark.parametrize("change", ["name", "incumbent", "checkpoint", "extra_checkpoint"])
def test_reconstruction_refuses_any_identity_mismatch(tmp_path, monkeypatch, change):
    run = _as_recorded(monkeypatch, _fake_run(tmp_path, episodes=(20, 40, 240)))
    sel.build_plan(run, incumbent_episode=240, seed_set="obs-v2")             # exact identity: allowed
    if change == "name":
        run = run.rename(tmp_path / "other_run")
        inc = 240
    elif change == "incumbent":
        (run / "best.json").write_text(json.dumps({"episode": 40, "file": "ckpt_best_ep0040.pt", "score": 1.0}))
        inc = 40
    elif change == "checkpoint":
        (run / "ckpt_ep0020.pt").write_bytes(b"retrained")
        inc = 240
    else:
        (run / "ckpt_ep0060.pt").write_bytes(b"w60")
        inc = 240
    with pytest.raises(ES.EvalSeedError, match="may only reconstruct that experiment"):
        sel.build_plan(run, incumbent_episode=inc, seed_set="obs-v2")
