"""Stage-5 unit tests (no SUMO, no simulation): selection seeds, validation mode, statistics, two-stage decision logic, plan, loader, safety."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pytest

from app.evaluation import selection as sel
from app.evaluation import seeds as ES
from app.evaluation.protocol import (EvalProtocol, ProtocolError, candidate_checkpoints, load_candidate_checkpoint)
from app.training import seeds as TS
from app.training.double_dqn import MaskedDoubleDQN
from app.training.runs import BACKEND, RunDirError, assert_output_root_allowed as runs_module_assert, save_checkpoint

SS = 11


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------ seeds: only fresh selection seeds
def test_selection_stage_seeds_are_as_planned_and_disjoint():
    a, b = ES.selection_seeds("A", 10), ES.selection_seeds("B", 20)
    assert a == list(range(3_000_101, 3_000_111)) and b == list(range(3_000_201, 3_000_221))
    assert not set(a) & set(b)
    ES.assert_selection_seeds(a, b)


@pytest.mark.parametrize("seed,why", [
    (4_000_001, "FINAL"), (4_000_030, "FINAL"), (4_000_031, "FINAL"), (4_000_060, "FINAL"), (4_000_000, "FINAL"), (4_999_999, "FINAL"),
    (5_000_001, "SMOKE"), (5_999_999, "SMOKE"),
    (2_000_001, "TRAINING"), (2_000_400, "TRAINING"), (2_999_999, "TRAINING"),
    (3_000_001, "proxy-validation"), (3_000_005, "proxy-validation"), (3_000_099, "proxy-validation"),
    (1_000_001, "outside"), (0, "outside"), (6_000_000, "outside"),
])
def test_selection_refuses_training_smoke_final_and_proxy_validation_seeds(seed, why):
    with pytest.raises(ES.EvalSeedError, match=why):
        ES.assert_selection_seed(seed)


def test_the_reserved_fresh_final_seeds_can_never_be_selection_seeds():
    lo, hi = ES.FRESH_FINAL_RESERVED
    assert (lo, hi) == (4_000_031, 4_000_060)
    for s in range(lo, hi + 1):
        with pytest.raises(ES.EvalSeedError):
            ES.assert_selection_seed(s)
    for stage in "AB":                                                       # no stage size can reach them
        assert max(ES.selection_seeds(stage, ES.MAX_STAGE_SEEDS)) < 4_000_000


def test_selection_stage_sizes_and_overlap_are_enforced():
    for bad in (0, 100, -1):
        with pytest.raises(ES.EvalSeedError):
            ES.selection_seeds("A", bad)
    with pytest.raises(ES.EvalSeedError):
        ES.selection_seeds("C", 5)
    with pytest.raises(ES.EvalSeedError, match="overlap"):
        ES.assert_selection_seeds([3_000_101, 3_000_102], [3_000_102, 3_000_201])
    with pytest.raises(ES.EvalSeedError, match="duplicate"):
        ES.assert_selection_seeds([3_000_101, 3_000_101], [3_000_201])
    with pytest.raises(ES.EvalSeedError):
        ES.assert_selection_seeds([3_000_101], [4_000_031])                  # a final seed smuggled into stage B
    with pytest.raises(ES.EvalSeedError):
        ES.assert_selection_seeds([], [3_000_201])


def test_validation_mode_accepts_only_selection_seeds_and_final_smoke_modes_refuse_them():
    ES.assert_seeds_for_mode(ES.selection_seeds("A", 3), "validation")
    for bad in ([4_000_001], [5_000_001], [2_000_001], [3_000_001]):
        with pytest.raises(ES.EvalSeedError):
            ES.assert_seeds_for_mode(bad, "validation")
    with pytest.raises(ES.EvalSeedError):
        ES.assert_seeds_for_mode([3_000_101], "final")                       # selection seeds are not final seeds
    with pytest.raises(ES.EvalSeedError):
        ES.assert_seeds_for_mode([3_000_101], "smoke")
    with pytest.raises(ES.EvalSeedError):
        ES.eval_seeds(3, "validation")                                       # final/smoke sequences cannot be requested for validation


def test_training_and_validation_of_train_dqn_never_overlap_the_selection_seeds_by_default():
    train = [TS.train_seed(e) for e in (1, 400, 999)]
    val = TS.val_seeds(99)                                                   # train_dqn.py validation may use up to 99 seeds
    for s in train + val:
        with pytest.raises(ES.EvalSeedError):
            ES.assert_selection_seed(s)
    for s in ES.selection_seeds("A", 99) + ES.selection_seeds("B", 99):
        TS.assert_not_protected(s) if s < 4_000_000 else None                # training code does not use them either
        assert s not in train and s not in val


def test_eval_protocol_validation_mode_exists_and_evaluate_refuses_it(tmp_path):
    p = EvalProtocol(n_seeds=2, mode="validation")
    assert p.horizon_s == 2700
    with pytest.raises(ProtocolError):
        EvalProtocol(mode="nonsense")
    from app.evaluation import runner
    with pytest.raises(ProtocolError, match="checkpoint-selection tool"):
        runner.evaluate(p, ["fixed_time"], ES.selection_seeds("A", 2), tmp_path, "v", progress=lambda s: None)
    assert list(tmp_path.iterdir()) == []                                    # nothing created, no ledger


# ------------------------------------------------------------------ statistics
@pytest.mark.parametrize("p,df", [(0.975, 19), (0.99167, 19), (0.995, 9), (0.975, 29), (0.9, 5)])
def test_t_quantile_matches_scipy(p, df):
    scipy_stats = pytest.importorskip("scipy.stats")
    assert sel.t_quantile(p, df) == pytest.approx(scipy_stats.t.ppf(p, df), rel=1e-6)


def test_t_quantile_known_value_without_scipy():
    assert sel.t_quantile(0.975, 19) == pytest.approx(2.0930, abs=1e-3)
    assert sel.t_quantile(0.975, 29) == pytest.approx(2.0452, abs=1e-3)
    with pytest.raises(sel.SelectionError):
        sel.t_quantile(0.4, 5)


def test_paired_interval_by_hand():
    d = np.array([-1.0, -2.0, -3.0, -4.0])
    r = sel.paired_interval(d, np.zeros(4), 0.05)
    half = 3.1824 * d.std(ddof=1) / 2.0
    assert r["mean_diff"] == -2.5 and r["ci_low"] == pytest.approx(-2.5 - half, abs=1e-3) and r["ci_high"] == pytest.approx(-2.5 + half, abs=1e-3)
    with pytest.raises(sel.SelectionError):
        sel.paired_interval([1, 2], [1, 2, 3], 0.05)                          # not seed-aligned
    with pytest.raises(sel.SelectionError):
        sel.paired_interval([1.0], [2.0], 0.05)
    with pytest.raises(sel.SelectionError):
        sel.paired_interval([1.0, float("nan")], [1.0, 2.0], 0.05)


# ------------------------------------------------------------------ eligibility, ranking, decision
def _row(wait=15.0, exhausted=0, unfinished=0, not_inserted=0, completion=1.0):
    return {sel.PRIMARY: wait, "drain_exhausted": exhausted, "trips_unfinished": unfinished, "trips_not_inserted": not_inserted, "completion_rate": completion}


def test_eligibility_gates():
    assert sel.candidate_eligibility([_row(), _row()]) == (True, [])
    for bad in (_row(exhausted=1), _row(unfinished=2), _row(not_inserted=1), _row(completion=0.99), _row(wait=float("nan"))):
        ok, why = sel.candidate_eligibility([_row(), bad])
        assert not ok and why
    assert not sel.candidate_eligibility([])[0]


def test_stage_a_ranking_excludes_the_incumbent_ineligible_candidates_and_breaks_ties_by_episode():
    scores = {20: [30.0], 40: [18.0], 60: [17.0], 80: [17.0], 100: [16.0], 400: [10.0]}
    elig = {20: True, 40: True, 60: True, 80: True, 100: False, 400: True}
    f = sel.rank_stage_a(scores, elig, incumbent=400, top_k=3)
    assert f == [40, 60, 80, 400]                                             # top 3 eligible challengers (ties 60/80 by episode) + incumbent last
    assert 100 not in f and 20 not in f                                       # ineligible 100 (best score) and the worst 20 are out
    assert sel.rank_stage_a({400: [1.0], 20: [2.0]}, {400: True, 20: True}, 400, 3) == [20, 400]
    with pytest.raises(sel.SelectionError):
        sel.rank_stage_a({20: [1.0]}, {20: True}, 400, 3)


def test_incumbent_is_kept_when_a_challenger_is_only_nominally_better():
    inc = [20.0, 21.0, 19.0, 22.0, 20.5, 21.5, 19.5, 20.0]
    chal = [x - 0.2 + (0.9 if i % 2 else -0.9) for i, x in enumerate(inc)]    # lower mean, but the interval contains 0
    d = sel.decide({400: inc, 80: chal}, {400: True, 80: True}, 400)
    c = d["challengers"]["80"]
    assert c["mean_diff"] < 0 and c["ci_high"] > 0 and not c["supported_improvement"]
    assert d["selected_episode"] == 400 and d["replaced"] is False


def test_a_clearly_better_eligible_challenger_replaces_the_incumbent():
    rng = np.random.default_rng(0)
    inc = list(20 + rng.normal(0, 3, 20))
    chal = [x - 3.0 + e for x, e in zip(inc, rng.normal(0, 0.5, 20))]       # paired, consistently ~3 s lower
    d = sel.decide({400: inc, 280: chal}, {400: True, 280: True}, 400)
    assert d["replaced"] and d["selected_episode"] == 280 and d["challengers"]["280"]["ci_high"] < 0


def test_an_ineligible_challenger_never_replaces_the_incumbent_however_good_it_looks():
    inc = [20.0 + i % 3 for i in range(20)]
    chal = [x - 5.0 + 0.01 * i for i, x in enumerate(inc)]
    d = sel.decide({400: inc, 100: chal}, {400: True, 100: False}, 400)
    assert d["challengers"]["100"]["ci_high"] < 0 and not d["challengers"]["100"]["supported_improvement"] and d["selected_episode"] == 400


def test_bonferroni_adjustment_makes_the_rule_stricter_with_more_challengers():
    rng = np.random.default_rng(3)
    inc = list(20 + rng.normal(0, 2, 20))
    noise = rng.normal(0, 1.0, 20)
    chal = [x - 0.62 + n for x, n in zip(inc, noise)]
    alone = sel.decide({400: inc, 80: chal}, {400: True, 80: True}, 400)
    three = sel.decide({400: inc, 80: chal, 100: list(inc), 120: list(inc)}, {400: True, 80: True, 100: True, 120: True}, 400)
    c1, c3 = alone["challengers"]["80"], three["challengers"]["80"]
    assert c3["t_crit"] > c1["t_crit"] and c3["ci_high"] > c1["ci_high"]       # wider interval with k = 3
    assert alone["confidence_per_comparison"] == pytest.approx(0.95) and three["confidence_per_comparison"] == pytest.approx(1 - 0.05 / 3)
    # find a case where the unadjusted interval excludes 0 but the adjusted one does not
    for shift in np.linspace(0.3, 1.5, 25):
        ch = [x - shift + n for x, n in zip(inc, noise)]
        a = sel.decide({400: inc, 80: ch}, {400: True, 80: True}, 400)["challengers"]["80"]["supported_improvement"]
        t = sel.decide({400: inc, 80: ch, 100: list(inc), 120: list(inc)}, {400: True, 80: True, 100: True, 120: True}, 400)["challengers"]["80"]["supported_improvement"]
        if a and not t:
            break
    else:
        pytest.fail("no shift found where the multiplicity adjustment matters")


def test_when_several_challengers_are_supported_the_largest_improvement_wins():
    rng = np.random.default_rng(1)
    inc = list(20 + rng.normal(0, 2, 20))
    c1 = [x - 2.0 + e for x, e in zip(inc, rng.normal(0, 0.3, 20))]
    c2 = [x - 4.0 + e for x, e in zip(inc, rng.normal(0, 0.3, 20))]
    d = sel.decide({400: inc, 280: c1, 340: c2}, {400: True, 280: True, 340: True}, 400)
    assert d["selected_episode"] == 340 and d["replaced"]


def test_decide_needs_the_incumbent_and_aligned_seeds():
    with pytest.raises(sel.SelectionError):
        sel.decide({280: [1.0, 2.0]}, {280: True}, 400)
    with pytest.raises(sel.SelectionError):
        sel.decide({400: [1.0, 2.0, 3.0], 280: [1.0, 2.0]}, {400: True, 280: True}, 400)
    assert sel.decide({400: [1.0, 2.0]}, {400: True}, 400)["selected_episode"] == 400    # no challenger: incumbent stays


# ------------------------------------------------------------------ plan (reads file names and hashes only)
def _fake_run(tmp_path: Path, episodes=(20, 40, 400), best_ep=400) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    (d / "config.json").write_text("{}")
    for e in episodes:
        (d / f"ckpt_ep{e:04d}.pt").write_bytes(f"weights-{e}".encode())
        (d / f"ckpt_best_ep{e:04d}.pt").write_bytes(f"best-{e}".encode())
    (d / "last.pt").write_bytes(b"last")
    (d / "best.pt").write_bytes(b"best")
    (d / "best.json").write_text(json.dumps({"episode": best_ep, "file": f"ckpt_best_ep{best_ep:04d}.pt", "metric": "mean_wait_s", "score": 1.0}))
    return d


def test_candidates_are_the_periodic_checkpoints_only(tmp_path):
    d = _fake_run(tmp_path)
    assert [(e, p.name) for e, p in candidate_checkpoints(d)] == [(20, "ckpt_ep0020.pt"), (40, "ckpt_ep0040.pt"), (400, "ckpt_ep0400.pt")]


def test_build_plan_is_deterministic_hash_bound_and_uses_selection_seeds_only(tmp_path):
    d = _fake_run(tmp_path)
    p1, p2 = sel.build_plan(d), sel.build_plan(d)
    assert p1.sha256() == p2.sha256() and p1.incumbent_episode == 400
    assert [c[0] for c in p1.candidates] == [20, 40, 400] and p1.candidates[0][2] == sha(d / "ckpt_ep0020.pt")
    assert set(p1.stage_a_seeds) | set(p1.stage_b_seeds) <= set(range(3_000_100, 4_000_000))
    assert not any(4_000_000 <= s <= 5_999_999 for s in p1.stage_a_seeds + p1.stage_b_seeds)
    assert p1.to_dict()["uses_final_seeds"] is False and p1.to_dict()["uses_ledger"] is False and p1.to_dict()["reserved_final_seeds"] == [4_000_031, 4_000_060]
    assert sel.build_plan(d, stage_a_n=5).sha256() != p1.sha256()
    (d / "ckpt_ep0020.pt").write_bytes(b"tampered")
    assert sel.build_plan(d).sha256() != p1.sha256()                          # the plan is bound to the checkpoint bytes
    assert p1.n_episodes() == (30, 80) and p1.protocol_for(p1.stage_a_seeds).mode == "validation"


def test_build_plan_refuses_a_run_whose_selection_is_not_the_incumbent_or_that_is_too_small(tmp_path):
    with pytest.raises(sel.SelectionError, match="best.json selects episode 40"):
        sel.build_plan(_fake_run(tmp_path / "a", best_ep=40) if (tmp_path / "a").mkdir() is None else None)
    (tmp_path / "b").mkdir()
    with pytest.raises(sel.SelectionError, match="fewer than two"):
        sel.build_plan(_fake_run(tmp_path / "b", episodes=(400,)))


# ------------------------------------------------------------------ loader for candidates
def _save(path: Path, episode: int, smoke=False, hidden=8):
    agent = MaskedDoubleDQN(SS, 4, hidden=hidden, seed=0)
    save_checkpoint(path, agent, episode=episode, decisions=10, val_score=None, val_metric="mean_wait_s", train_config={"hidden": hidden, "smoke": smoke})
    return agent


def test_candidate_loader_accepts_a_valid_periodic_checkpoint_and_never_writes(tmp_path):
    d = tmp_path / "r"; d.mkdir(); (d / "config.json").write_text("{}")
    _save(d / "ckpt_ep0020.pt", 20)
    before = {p.name: sha(p) for p in d.iterdir()}
    agent, info = load_candidate_checkpoint(d, "ckpt_ep0020.pt")
    assert info["selected_episode"] == 20 and info["sha256"] == before["ckpt_ep0020.pt"] and agent.policy_net.training is False
    assert {p.name: sha(p) for p in d.iterdir()} == before


@pytest.mark.parametrize("name", ["best.pt", "last.pt", "ckpt_best_ep0020.pt", "../x/ckpt_ep0020.pt", "/etc/passwd", "ckpt_ep20.pt", "ckpt_ep0020.pt.bak"])
def test_candidate_loader_refuses_anything_but_plain_periodic_names(tmp_path, name):
    d = tmp_path / "r"; d.mkdir(); (d / "config.json").write_text("{}")
    with pytest.raises(ProtocolError, match="periodic checkpoint name"):
        load_candidate_checkpoint(d, name)


def test_candidate_loader_refuses_smoke_wrong_episode_missing_config_and_the_legacy_model(tmp_path):
    d = tmp_path / "r"; d.mkdir()
    _save(d / "ckpt_ep0020.pt", 20)
    with pytest.raises(ProtocolError, match="missing"):
        load_candidate_checkpoint(d, "ckpt_ep0020.pt")                       # no config.json
    (d / "config.json").write_text("{}")
    _save(d / "ckpt_ep0040.pt", 99)
    with pytest.raises(ProtocolError, match="claims episode"):
        load_candidate_checkpoint(d, "ckpt_ep0040.pt")
    _save(d / "ckpt_ep0060.pt", 60, smoke=True)
    with pytest.raises(ProtocolError, match="smoke"):
        load_candidate_checkpoint(d, "ckpt_ep0060.pt")
    legacy = BACKEND / "data" / "models" / "dqn_agent.pt"
    if legacy.exists():
        (d / "ckpt_ep0080.pt").write_bytes(legacy.read_bytes())
        with pytest.raises(ProtocolError, match="legacy|format"):
            load_candidate_checkpoint(d, "ckpt_ep0080.pt")


# ------------------------------------------------------------------ run_selection with a fake environment (no SUMO)
class FakeRunner:
    """Stands in for SUMO.  Per-episode waiting time = base(episode) + seed-dependent demand effect shared by all checkpoints."""
    log: list = []
    base = {}

    def __init__(self, protocol):
        assert protocol.mode == "validation"
        self.protocol = protocol
        self.closed = False

    def run(self, controller, seed):
        assert 3_000_100 < seed < 4_000_000, f"seed {seed} must be a selection seed"
        FakeRunner.log.append((controller.info["selected_episode"], seed))
        e = controller.info["selected_episode"]
        wait = FakeRunner.base.get(e, 20.0) + (seed % 7) * 1.5 + 0.01 * (e % 5)
        return {sel.PRIMARY: wait, "wait_per_vehicle_completed_s": wait, "travel_time_completed_s": 140.0, "mean_queue_per_lane": 0.8, "throughput_veh_per_h": 2500.0,
                "trips_scheduled": 1200.0, "trips_completed": 1200.0, "trips_unfinished": 0.0, "trips_not_inserted": 0.0, "completion_rate": 1.0, "drain_s_used": 160.0,
                "drain_exhausted": 0, "decisions": 456, "actions_switch": 400, "actions_extend": 100, "actions_reduce": 20, "phases_completed": 900.0, "wall_s": 0.0}

    def close(self):
        self.closed = True


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    d = _fake_run(tmp_path, episodes=(20, 40, 60, 80, 400))
    FakeRunner.log = []
    FakeRunner.base = {}
    class _Agent:
        pass
    def fake_candidate(run_dir, filename):
        e = int(filename[7:11])
        return _Agent(), {"selected_episode": e, "sha256": sha(Path(run_dir) / filename), "smoke_training_run": False}
    monkeypatch.setattr(sel, "load_candidate_checkpoint", fake_candidate)
    monkeypatch.setattr(sel, "load_validation_selected_checkpoint", lambda rd: (_Agent(), {"sha256": "bestsha"}))
    monkeypatch.setattr(sel, "weights_equal", lambda a, b: True)
    class _Ctrl:
        def __init__(self, agent, info):
            self.info = info
    monkeypatch.setattr(sel, "DQNController", _Ctrl)
    return d


def _run(plan, out, run_id="s1", **kw):
    return sel.run_selection(plan, out, run_id, confirm=True, make_runner=FakeRunner, progress=lambda s: None, **kw)


def test_two_stage_flow_uses_exactly_the_planned_selection_seeds_and_keeps_the_incumbent_when_nothing_is_better(fake_env, tmp_path):
    plan = sel.build_plan(fake_env, stage_a_n=3, stage_b_n=4, top_k=2)
    out = tmp_path / "out"
    res = _run(plan, out)
    seeds_used = {s for _, s in FakeRunner.log}
    assert seeds_used == set(plan.stage_a_seeds) | set(plan.stage_b_seeds)
    assert not any(4_000_000 <= s <= 5_999_999 or s < 3_000_100 for s in seeds_used)
    a_calls = [(e, s) for e, s in FakeRunner.log if s in plan.stage_a_seeds]
    assert len(a_calls) == 5 * 3                                              # every candidate on every stage-A seed
    b_calls = [(e, s) for e, s in FakeRunner.log if s in plan.stage_b_seeds]
    assert len(b_calls) == (2 + 1) * 4 and {e for e, _ in b_calls} == set(res["decision"]["finalists"]) and 400 in res["decision"]["finalists"]
    d = res["decision"]
    assert d["selected_episode"] == 400 and d["replaced"] is False and d["uses_final_seeds"] is False and d["ledger_touched"] is False
    assert d["selected_sha256"] == sha(fake_env / "ckpt_ep0400.pt")


def test_a_really_better_challenger_is_selected_on_the_independent_stage_b_seeds(fake_env, tmp_path):
    FakeRunner.base = {400: 20.0, 280: 20.0, 80: 14.0, 60: 18.0}
    plan = sel.build_plan(fake_env, stage_a_n=4, stage_b_n=8, top_k=2)
    res = _run(plan, tmp_path / "out")
    d = res["decision"]
    assert d["finalists"][:-1] == [60, 80] and d["selected_episode"] == 80 and d["replaced"] is True
    assert d["selected_file"] == "ckpt_ep0080.pt" and d["challengers"]["80"]["ci_high"] < 0
    # the stage-A numbers are reported but the decision rests on stage B only
    assert set(d["challengers"]) == {"60", "80"} and all(ES.assert_selection_seed(s) for s in plan.stage_b_seeds)


def test_plan_is_written_before_the_first_episode_and_outputs_are_confined_to_the_new_directory(fake_env, tmp_path):
    plan = sel.build_plan(fake_env, stage_a_n=2, stage_b_n=3, top_k=1)
    out = tmp_path / "out"
    seen = {}
    class Probe(FakeRunner):
        def run(self, controller, seed):
            seen.setdefault("plan_existed", (out / "s1" / "plan.json").exists())
            return super().run(controller, seed)
    train_before = {p.name: sha(p) for p in fake_env.iterdir()}
    res = sel.run_selection(plan, out, "s1", confirm=True, make_runner=Probe, progress=lambda s: None)
    assert seen["plan_existed"] is True
    assert {p.name for p in (out / "s1").iterdir()} == {"plan.json", "stage_a.csv", "stage_b.csv", "decision.json"}
    assert json.loads((out / "s1" / "plan.json").read_text())["plan_sha256"] == plan.sha256()
    assert {p.name: sha(p) for p in fake_env.iterdir()} == train_before        # the training run (best.json, best.pt, checkpoints) is untouched
    assert [p.name for p in out.iterdir()] == ["s1"] and not list(out.glob("**/ledger.jsonl"))


def test_selection_requires_confirmation_and_refuses_existing_or_forbidden_output_directories(fake_env, tmp_path, monkeypatch):
    plan = sel.build_plan(fake_env, stage_a_n=2, stage_b_n=2, top_k=1)
    with pytest.raises(sel.SelectionError, match="confirm"):
        sel.run_selection(plan, tmp_path / "o", "x", confirm=False, make_runner=FakeRunner)
    assert not (tmp_path / "o").exists() and FakeRunner.log == []
    _run(plan, tmp_path / "o", "x")
    with pytest.raises(RunDirError):
        _run(plan, tmp_path / "o", "x")                                          # never overwrite a selection run
    # the guarded defaults are the real output roots (a constant check: no real directory is touched or even resolved)
    assert Path(sel.DEFAULT_EVAL_ROOT) == BACKEND / "evaluation_runs" and Path(sel.DEFAULT_RUNS_ROOT) == BACKEND / "training_runs"
    # run_selection itself, exercised on tmp stand-ins so a broken guard could never write into a real directory
    fake_eval, fake_train = tmp_path / "evaluation_runs", tmp_path / "training_runs"
    monkeypatch.setattr(sel, "DEFAULT_EVAL_ROOT", fake_eval)
    monkeypatch.setattr(sel, "DEFAULT_RUNS_ROOT", fake_train)
    for forbidden in (fake_eval, fake_eval / "sub", fake_train, fake_train / "fyp_s0"):
        with pytest.raises(sel.SelectionError):
            _run(plan, forbidden, "should_not_exist")
        assert not (forbidden / "should_not_exist").exists()
    for real in (BACKEND / "data", BACKEND / "sumo" / "routes"):
        with pytest.raises(RunDirError):
            runs_module_assert(real)


def test_selection_refuses_a_plan_with_final_smoke_or_training_seeds(fake_env, tmp_path):
    plan = sel.build_plan(fake_env, stage_a_n=2, stage_b_n=2, top_k=1)
    for bad in (4_000_031, 4_000_001, 5_000_001, 2_000_001, 3_000_001):
        evil = sel.SelectionPlan(plan.run_dir, plan.candidates, plan.incumbent_episode, plan.stage_a_seeds, (bad, plan.stage_b_seeds[1]))
        with pytest.raises(ES.EvalSeedError):
            _run(evil, tmp_path / f"o{bad}")
        assert FakeRunner.log == [] and not (tmp_path / f"o{bad}").exists()


def test_selection_refuses_a_checkpoint_changed_after_the_plan_and_a_wrong_incumbent(fake_env, tmp_path, monkeypatch):
    plan = sel.build_plan(fake_env, stage_a_n=2, stage_b_n=2, top_k=1)
    (fake_env / "ckpt_ep0040.pt").write_bytes(b"changed after planning")
    with pytest.raises(sel.SelectionError, match="changed after the plan"):
        _run(plan, tmp_path / "o1")
    (fake_env / "ckpt_ep0040.pt").write_bytes(b"weights-40")
    monkeypatch.setattr(sel, "weights_equal", lambda a, b: False)
    FakeRunner.log = []
    with pytest.raises(sel.SelectionError, match="best.pt"):
        _run(plan, tmp_path / "o2")
    assert FakeRunner.log == []                                                  # no episode ran with an unverified incumbent


def _with_flag(predicate):
    orig = FakeRunner.run
    def flagged(self, controller, seed):
        r = orig(self, controller, seed)
        if predicate(controller.info["selected_episode"], seed):
            r = {**r, "drain_exhausted": 1, "trips_unfinished": 5.0, "completion_rate": 0.99}
        return r
    FakeRunner.run = flagged
    return orig


def test_a_candidate_ineligible_in_stage_a_never_reaches_stage_b(fake_env, tmp_path):
    FakeRunner.base = {400: 20.0, 80: 10.0, 60: 22.0, 40: 22.0, 20: 22.0}                # 80 looks best but exhausts its drain in stage A
    orig = _with_flag(lambda e, s: e == 80)
    try:
        plan = sel.build_plan(fake_env, stage_a_n=3, stage_b_n=5, top_k=2)
        d = _run(plan, tmp_path / "o")["decision"]
    finally:
        FakeRunner.run = orig
    assert 80 not in d["finalists"] and d["stage_a"]["80"]["eligible"] is False and d["stage_a"]["80"]["eligibility_reasons"]
    assert d["selected_episode"] == 400 and not d["replaced"]


def test_a_finalist_that_is_ineligible_in_stage_b_cannot_win_even_with_the_best_waiting_time(fake_env, tmp_path):
    FakeRunner.base = {400: 20.0, 80: 5.0, 60: 22.0, 40: 22.0, 20: 22.0}                 # 80 is far better, but fails the gate on the confirmation seeds
    orig = _with_flag(lambda e, s: e == 80 and s >= 3_000_200)
    try:
        plan = sel.build_plan(fake_env, stage_a_n=3, stage_b_n=5, top_k=2)
        d = _run(plan, tmp_path / "o")["decision"]
    finally:
        FakeRunner.run = orig
    c = d["challengers"]["80"]
    assert 80 in d["finalists"] and c["ci_high"] < 0 and c["eligible"] is False and not c["supported_improvement"]
    assert d["selected_episode"] == 400 and not d["replaced"]


# ------------------------------------------------------------------ source-level safety
def _names(path: Path):
    tree = ast.parse(path.read_text())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.alias):
            out.add(n.name)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.add(n.value)
    return out


def test_selection_code_never_touches_the_ledger_final_mode_or_best_files():
    src = (BACKEND / "app" / "evaluation" / "selection.py")
    names = _names(src)
    for forbidden in ("read_ledger", "append_ledger", "assert_final_not_repeated", "ledger.jsonl", "evaluate", "FINAL_EVAL_RANGE", "FINAL_EVAL_BASE", "eval_seeds"):
        assert forbidden not in names, forbidden
    assert "write_json_atomic" in names and not {"unlink", "rmtree", "remove", "rename", "replace", "copy", "copyfile", "move"} & names
    cli = _names(BACKEND / "select_checkpoint.py")
    assert "--confirm-selection" in cli and not {"read_ledger", "append_ledger", "FINAL_EVAL_RANGE"} & cli


def test_run_selection_has_no_default_for_confirmation_and_no_seed_arguments():
    sig = inspect.signature(sel.run_selection)
    assert sig.parameters["confirm"].default is False
    assert not [p for p in sig.parameters if "seed" in p]                          # seeds come only from the hashed plan
    assert not [a.dest for a in __import__("select_checkpoint").build_parser()._actions if "seed" in a.dest and a.dest not in ("stage_a_n", "stage_b_n")]
