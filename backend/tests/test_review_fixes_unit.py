"""Stage-9 review fixes (no SUMO simulation): ledger safeguards, final-seed reuse, safe CLI defaults, never-inserted trips,
training-configuration checks, environment cleanup, atomic best.pt, the legacy evaluation script and the legacy DQN agent.

Everything writes into ``tmp_path`` only; no real output folder, checkpoint, route file, registry or ledger is touched.
"""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.evaluation import protocol as P
from app.evaluation import runner
from app.evaluation import seeds as ES
from app.evaluation.controllers import DQNController
from app.evaluation.metrics import MeasurementError
from app.training import seeds as TS
from app.training import trainer as T
from app.training.double_dqn import MaskedDoubleDQN
from app.training.runs import RunDirError, finalize_best
from app.training.trainer import TrainConfig, train

def _final(n=2):
    return P.EvalProtocol(n_seeds=n, mode="final")


def _entry(run_id, seeds, sha="a" * 64, status=None, policy=None, mode="final"):
    e = {"run_id": run_id, "mode": mode, "checkpoint_sha256": sha, "seeds": list(seeds)}
    if status:
        e["status"] = status
    if policy:
        e["policy_sha256"] = policy
    return e


# ------------------------------------------------------------------ D1 / R4: repeat guard, crashed attempts, policy hash, lock
def test_a_started_but_never_completed_final_counts_as_a_previous_attempt():
    led = [_entry("crashed", [4_000_061, 4_000_062], status="started")]
    with pytest.raises(P.ProtocolError, match="started \\(and did not complete\\)"):
        P.assert_final_not_repeated(led, "a" * 64, allow_repeat=False)
    P.assert_final_not_repeated(led, "a" * 64, allow_repeat=True)              # an explicit, recorded repeat stays possible


def test_ledger_entries_written_before_the_status_field_count_as_completed():
    led = [_entry("fyp_final_s0", [4_000_001, 4_000_030])]
    with pytest.raises(P.ProtocolError, match="already has"):
        P.assert_final_not_repeated(led, "a" * 64, allow_repeat=False)
    P.assert_final_not_repeated(led, "b" * 64, allow_repeat=False)


def test_the_same_policy_in_a_different_file_is_a_repeat():
    led = [_entry("first", [4_000_061, 4_000_062], sha="a" * 64, status="completed", policy="p" * 64)]
    with pytest.raises(P.ProtocolError, match="already has"):
        P.assert_final_not_repeated(led, "c" * 64, allow_repeat=False, policy_sha="p" * 64)
    P.assert_final_not_repeated(led, "c" * 64, allow_repeat=False, policy_sha="q" * 64)


def test_smoke_entries_never_block_a_final_run():
    led = [_entry("s", [4_000_061, 4_000_062], mode="smoke", status="completed")]
    P.assert_final_not_repeated(led, "a" * 64, allow_repeat=False)
    P.assert_final_seeds_unused(led, [4_000_061, 4_000_062])


def test_policy_weight_hash_ignores_the_file_and_tracks_the_weights():
    import torch
    a, b = MaskedDoubleDQN(11, seed=0), MaskedDoubleDQN(11, seed=1)
    b.policy_net.load_state_dict(a.policy_net.state_dict())                     # same weights, different objects
    assert P.policy_weights_sha256(a) == P.policy_weights_sha256(b)
    with torch.no_grad():
        next(b.policy_net.parameters()).add_(1e-6)
    assert P.policy_weights_sha256(a) != P.policy_weights_sha256(b)


def test_ledger_lock_refuses_a_concurrent_holder_and_is_released(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    with P.ledger_lock(ledger):
        with pytest.raises(P.ProtocolError, match="another evaluation"):
            with P.ledger_lock(ledger):
                pass
    with P.ledger_lock(ledger):                                                  # released after the first holder left
        pass


def test_a_corrupt_ledger_line_fails_with_a_clear_error(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps(_entry("x", [1, 2])) + "\n{\"run_id\": \"half")
    with pytest.raises(P.ProtocolError, match="corrupt at line 2"):
        P.read_ledger(ledger)


# ------------------------------------------------------------------ D2: final seeds are used once
def test_final_seed_ranges_already_in_the_ledger_are_refused_with_a_way_out():
    led = [_entry("fyp_final_s0", [4_000_001, 4_000_030]), _entry("fyp_final_s0_obs_v2", [4_000_031, 4_000_060], status="completed")]
    for seeds in (ES.eval_seeds(30, "final"), [4_000_030, 4_000_031], [4_000_055, 4_000_070]):
        with pytest.raises(P.ProtocolError, match="--seed-base 4000060"):
            P.assert_final_seeds_unused(led, seeds)
    P.assert_final_seeds_unused(led, ES.eval_seeds(30, "final", base=4_000_060))  # 4,000,061 ... 4,000,090: fresh
    P.assert_final_seeds_unused(led + [_entry("crash", [4_000_061, 4_000_062], status="started")], [4_000_063, 4_000_064])
    with pytest.raises(P.ProtocolError, match="crash"):
        P.assert_final_seeds_unused(led + [_entry("crash", [4_000_061, 4_000_062], status="started")], [4_000_062])


# ------------------------------------------------------------------ D1 / D2 / R4 through evaluate() (episodes replaced, no SUMO)
def _fake_row(name, seed):
    return {"controller": name, "seed": seed, **{k: 1.0 for k in runner.METRIC_KEYS}, **{k: 0 for k in runner.EXTRA_COLUMNS}}


@pytest.fixture
def no_sim(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(runner, "DEFAULT_EVAL_ROOT", tmp_path)                  # the canonical final root, as a tmp stand-in

    def fake_run_episode(env, controller, seed, protocol, program=None):
        calls.append((controller.name, seed))
        if getattr(fake_run_episode, "crash_at", None) == len(calls):
            raise RuntimeError("simulated crash in the middle of a final run")
        return {"row": _fake_row(controller.name, seed), "timing": None, "lanes": []}

    monkeypatch.setattr(runner, "run_episode", fake_run_episode)
    monkeypatch.setattr(runner, "TrafficSignalEnv", lambda cfg: SimpleNamespace(close=lambda: None))
    fake_run_episode.calls = calls
    return fake_run_episode


def _dqn():
    agent = MaskedDoubleDQN(11, seed=0)
    return DQNController(agent, {"sha256": "f" * 64, "policy_sha256": P.policy_weights_sha256(agent), "obs_version": None})


def test_final_run_writes_started_then_completed_entries(tmp_path, no_sim):
    seeds, dqn = ES.eval_seeds(2, "final", base=4_000_060), _dqn()
    runner.evaluate(_final(), ["fixed_time", "dqn"], seeds, tmp_path, "f1", dqn=dqn, confirm_final=True, progress=lambda s: None)
    led = P.read_ledger(tmp_path / "ledger.jsonl")
    assert [e["status"] for e in led] == ["started", "completed"]
    assert all(e["policy_sha256"] == dqn.info["policy_sha256"] and e["seeds"] == [4_000_061, 4_000_062] for e in led)


def test_a_crashed_final_run_blocks_a_silent_retry(tmp_path, no_sim):
    seeds = ES.eval_seeds(2, "final", base=4_000_060)
    no_sim.crash_at = 2
    with pytest.raises(RuntimeError, match="simulated crash"):
        runner.evaluate(_final(), ["fixed_time", "dqn"], seeds, tmp_path, "f1", dqn=_dqn(), confirm_final=True, progress=lambda s: None)
    led = P.read_ledger(tmp_path / "ledger.jsonl")
    assert [e["status"] for e in led] == ["started"]                           # the attempt is on record although it crashed
    no_sim.crash_at = None
    with pytest.raises(P.ProtocolError):                                        # same seeds and same model: refused
        runner.evaluate(_final(), ["fixed_time", "dqn"], seeds, tmp_path, "f2", dqn=_dqn(), confirm_final=True, progress=lambda s: None)
    with pytest.raises(P.ProtocolError, match="started"):                       # fresh seeds, same model: still refused
        runner.evaluate(_final(), ["fixed_time", "dqn"], ES.eval_seeds(2, "final", base=4_000_070), tmp_path, "f3",
                        dqn=_dqn(), confirm_final=True, progress=lambda s: None)
    assert not (tmp_path / "f2").exists() and not (tmp_path / "f3").exists()


def test_a_final_run_on_used_seeds_is_refused_before_anything_is_created(tmp_path, no_sim):
    (tmp_path / "ledger.jsonl").write_text(json.dumps(_entry("fyp_final_s0", [4_000_001, 4_000_030])) + "\n")
    with pytest.raises(P.ProtocolError, match="--seed-base"):
        runner.evaluate(_final(), ["fixed_time"], ES.eval_seeds(2, "final"), tmp_path, "again", confirm_final=True, progress=lambda s: None)
    assert not (tmp_path / "again").exists() and no_sim.calls == []
    assert len(P.read_ledger(tmp_path / "ledger.jsonl")) == 1


def test_a_concurrent_final_run_is_refused(tmp_path, no_sim):
    with P.ledger_lock(tmp_path / "ledger.jsonl"):                              # another run is between its check and its record
        with pytest.raises(P.ProtocolError, match="another evaluation"):
            runner.evaluate(_final(), ["fixed_time"], ES.eval_seeds(2, "final", base=4_000_060), tmp_path, "c",
                            confirm_final=True, progress=lambda s: None)
    assert not (tmp_path / "c").exists() and no_sim.calls == []


def test_a_final_run_without_confirmation_creates_nothing(tmp_path, no_sim):
    with pytest.raises(P.ProtocolError, match="confirm"):
        runner.evaluate(_final(), ["fixed_time"], ES.eval_seeds(2, "final", base=4_000_060), tmp_path, "u", progress=lambda s: None)
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------ R1: safe CLI default
def test_evaluate_fyp_defaults_to_smoke_and_final_needs_confirmation(tmp_path, capsys):
    import evaluate_fyp
    assert evaluate_fyp.build_parser().parse_args([]).mode == "smoke"
    evaluate_fyp.main(["--plan"])
    assert "PROTOCOL (smoke)" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="--confirm-final"):
        evaluate_fyp.main(["--mode", "final", "--run-id", "x", "--out-root", str(tmp_path)])
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------ D7: never-inserted trips at a terminated end are caught
class _Conn:
    def __init__(self, pending):
        self.simulation = SimpleNamespace(getMinExpectedNumber=lambda: 0, getPendingVehicles=lambda: list(pending))


class _Env:
    """Ends (terminated) exactly when the demand stops; reports ``pending`` vehicles still waiting for insertion."""

    def __init__(self, protocol, pending):
        self.cfg = SimpleNamespace(horizon_s=protocol.horizon_s, demand_end_s=protocol.demand_end_s, junction_ids=["J"])
        self.topology = {"J": SimpleNamespace(lanes=[f"l{i}" for i in range(16)])}
        self.conn, self.sim_time, self.signal_log, self.step_s = _Conn(pending), 0.0, [], protocol.decision_interval_s

    def reset(self, seed):
        return {"J": np.zeros(11)}

    def add_second_hook(self, hook):
        pass

    def action_masks(self):
        return {"J": np.ones(4, dtype=bool)}

    def step(self, actions):
        self.sim_time += self.step_s
        done = self.sim_time >= self.cfg.demand_end_s
        return SimpleNamespace(obs={"J": np.zeros(11)}, terminated=done, truncated=False,
                               info={"coerced_actions": {}, "safety_violations": [], "action_masks": self.action_masks()})


class _Measurer:
    def __init__(self, *a, **k):
        self.lane_acc = SimpleNamespace(per_lane=lambda: [{} for _ in range(16)])

    def finalize(self, steps, run_end_s=None, not_inserted=0):
        return {**{k: 0.0 for k in runner.METRIC_KEYS}, "wait_per_vehicle_all_s": 5.0, "trips_unfinished": 0.0,
                "trips_not_inserted": float(not_inserted), "n_lane_obs": 16 * 1800}


class _Keep:
    name, params = "keep_only", {}

    def start_episode(self, env):
        pass

    def act(self, env, obs, masks):
        return {"J": 0}


@pytest.mark.parametrize("pending,raises", [(["v1", "v2"], True), ([], False)])
def test_terminated_episode_with_never_inserted_vehicles_is_rejected(monkeypatch, pending, raises):
    monkeypatch.setattr(runner, "EpisodeMeasurer", _Measurer)
    proto = P.EvalProtocol(n_seeds=1, mode="smoke")
    env = _Env(proto, pending)
    if raises:
        with pytest.raises(MeasurementError, match="2 vehicles were never inserted"):
            runner.run_episode(env, _Keep(), 5_000_001, proto)
    else:
        row = runner.run_episode(env, _Keep(), 5_000_001, proto)["row"]
        assert row["vehicles_left_at_end"] == 0 and row["trips_not_inserted"] == 0.0


# ------------------------------------------------------------------ D3 / R3: configuration checks before any output exists
def _cfg(tmp_path, **kw):
    base = dict(run_id="r", out_root=tmp_path, seed=7, episodes=2, horizon_s=60, val_every=1, val_n=1, warmup=32, batch_size=16,
                buffer_size=2000, updates_per_decision=1, target_update_steps=5, eps_decay_decisions=20)
    base.update(kw)
    return TrainConfig(**base)


@pytest.mark.parametrize("kw,match", [
    (dict(seed=-1), "seed must be"), (dict(seed=2 ** 32), "seed must be"),
    (dict(val_n=100), "--val-n must be <= 99"),
    (dict(train_seed_base=2_999_999), "training seeds must lie in 2,000,000 - 2,999,999"),
    (dict(train_seed_base=0), "training seeds must lie"),
    (dict(val_seed_base=3_000_098, val_n=5), "validation seeds must lie in 3,000,001 - 3,000,099"),
    (dict(val_seed_base=3_000_200), "validation seeds must lie"),
])
def test_invalid_training_configuration_is_refused_before_the_run_directory_exists(tmp_path, kw, match):
    with pytest.raises(TS.SeedError, match=match):
        train(_cfg(tmp_path, **kw))
    assert list(tmp_path.iterdir()) == []


def test_the_recorded_fyp_seed_plans_remain_valid():
    for n_ep, n_val in ((400, 5), (2, 1)):
        TS.assert_training_seed_plan([TS.train_seed(e) for e in range(1, n_ep + 1)], TS.val_seeds(n_val))
    assert TS.val_seeds(99)[-1] == 3_000_099 and TS.check_seed(0) == 0 and TS.check_seed(2 ** 32 - 1) == 2 ** 32 - 1


class _BrokenEnv:
    """Fails on reset; optionally also fails on close. Records every close() call."""
    closed: list = []

    def __init__(self, cfg, close_fails=False):
        self.close_fails = close_fails
        self.conn = None

    def reset(self, seed):
        raise RuntimeError("boom: original training error")

    def close(self):
        _BrokenEnv.closed.append(self)
        if self.close_fails:
            raise RuntimeError("close failed")


def test_config_is_persisted_immediately_and_both_environments_are_closed_on_failure(tmp_path, monkeypatch):
    _BrokenEnv.closed = []
    made = []

    def factory(cfg):
        e = _BrokenEnv(cfg, close_fails=not made)                               # the first (training) env fails to close
        made.append(e)
        return e

    monkeypatch.setattr(T, "TrafficSignalEnv", factory)
    with pytest.raises(RuntimeError, match="boom: original training error"):     # the original error is not masked
        train(_cfg(tmp_path))
    assert _BrokenEnv.closed == made and len(made) == 2                         # both closed although the first close raised
    cfg = json.loads((tmp_path / "r" / "config.json").read_text())              # config.json exists although no episode ran
    assert cfg["config"]["run_id"] == "r" and cfg["versions"]["sumo"] is None


def test_close_errors_are_reported_when_nothing_else_failed():
    class Ok:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class Bad(Ok):
        def close(self):
            super().close()
            raise RuntimeError("close failed")

    a, b = Bad(), Ok()
    with pytest.raises(RuntimeError, match="close failed"):
        T._close_envs(a, b)
    assert a.closed and b.closed
    T._close_envs(Bad(), Ok(), suppress=True)


# ------------------------------------------------------------------ R5: best.pt through a temporary file
def test_best_pt_is_created_atomically_and_never_overwritten(tmp_path, monkeypatch):
    src = tmp_path / "ckpt_best_ep0020.pt"
    src.write_bytes(b"weights" * 100)
    dst = finalize_best(tmp_path, src)
    assert dst.read_bytes() == src.read_bytes() and sorted(p.name for p in tmp_path.iterdir()) == ["best.pt", "ckpt_best_ep0020.pt"]
    with pytest.raises(RunDirError, match="refusing to overwrite"):
        finalize_best(tmp_path, src)
    other = tmp_path / "other"; other.mkdir()

    def broken_copy(src_f, dst_f, *a):
        dst_f.write(b"trunc")
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copyfileobj", broken_copy)
    with pytest.raises(OSError, match="disk full"):
        finalize_best(other, src)
    assert list(other.iterdir()) == []                                          # no truncated best.pt and no temporary file left


def test_best_pt_is_fsynced_before_publishing(tmp_path, monkeypatch):
    import os
    src = tmp_path / "ckpt_best_ep0020.pt"
    src.write_bytes(b"w" * 64)
    events = []
    real_fsync, real_link = os.fsync, os.link
    monkeypatch.setattr(os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(os, "link", lambda a, b: (events.append("link"), real_link(a, b))[1])
    finalize_best(tmp_path, src)
    assert events[:2] == ["fsync", "link"]                                      # data durable before the name appears


def test_best_pt_without_hard_links_fails_cleanly(tmp_path, monkeypatch):
    import os
    src = tmp_path / "ckpt_best_ep0020.pt"
    src.write_bytes(b"w" * 64)

    def no_links(a, b):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    with pytest.raises(RunDirError, match="must support hard links"):
        finalize_best(tmp_path, src)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ckpt_best_ep0020.pt"]


def test_best_pt_created_concurrently_is_never_overwritten(tmp_path, monkeypatch):
    import os
    src = tmp_path / "ckpt_best_ep0020.pt"
    src.write_bytes(b"mine")
    real_link = os.link

    def racing_link(a, b):
        Path(b).write_bytes(b"theirs")                                          # another process publishes first
        return real_link(a, b)

    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(RunDirError, match="refusing to overwrite"):
        finalize_best(tmp_path, src)
    assert (tmp_path / "best.pt").read_bytes() == b"theirs"                     # the other writer's file is untouched
    assert sorted(p.name for p in tmp_path.iterdir()) == ["best.pt", "ckpt_best_ep0020.pt"]


# ------------------------------------------------------------------ D6 / R6 / T4: legacy evaluation script
def test_legacy_checkpoint_option_is_local_and_checked_before_any_output(tmp_path):
    import evaluate_controllers as EC
    default = EC.CHECKPOINT_PATH
    missing = tmp_path / "missing.pt"
    with pytest.raises(FileNotFoundError, match="missing.pt"):
        EC.main(["--checkpoint", str(missing), "--output-dir", str(tmp_path / "out"), "--episodes", "1"])
    assert EC.CHECKPOINT_PATH == default                                        # the module default is never reassigned
    assert not (tmp_path / "out").exists()


def test_legacy_sumocfg_rewrite_requires_exactly_one_match(tmp_path, monkeypatch):
    import evaluate_controllers as EC
    cfg = EC.make_episode_config(tmp_path / "ok", 1_000_001)
    text = cfg.read_text()
    assert str(tmp_path / "ok" / "episode_1000001.rou.xml") in text and "../routes/intelliroads.rou.xml" not in text
    broken = tmp_path / "broken.sumocfg"
    broken.write_text(EC.SUMO_CONFIG_PATH.read_text().replace("route-files", "additional-files"))
    monkeypatch.setattr(EC, "SUMO_CONFIG_PATH", broken)
    with pytest.raises(RuntimeError, match="exactly one <route-files"):
        EC.make_episode_config(tmp_path / "bad", 1_000_002)


# ------------------------------------------------------------------ T3 / T4: legacy DQN agent defaults and masks
def _legacy_agent():
    from app.agent.dqn_agent import DQNAgent
    return DQNAgent(state_size=5, action_size=4, device="cpu")


def test_unmasked_exploration_still_uses_randrange():
    agent, state = _legacy_agent(), [10.0, 5.0, 20.0, 1.0, 0.0]
    for seed in range(20):
        random.seed(seed)
        got = agent.select_action(state, epsilon=1.0)
        random.seed(seed)
        random.random()                                                         # the epsilon draw
        assert got == random.randrange(4)


@pytest.mark.parametrize("mask,match", [([False] * 4, "no legal action"), ([True] * 3, "4 entries"), ([True] * 5, "4 entries")])
def test_invalid_legal_masks_are_refused(mask, match):
    with pytest.raises(ValueError, match=match):
        _legacy_agent().select_action([10.0, 5.0, 20.0, 1.0, 0.0], epsilon=0.0, legal_mask=mask)


# ------------------------------------------------------------------ T1: evidence mode turns a missing saved output into a failure
def test_missing_evidence_skips_by_default_and_fails_in_evidence_mode(monkeypatch):
    from tests import fyp_evidence as FE
    monkeypatch.setattr(FE, "REQUIRE_EVIDENCE", False)
    with pytest.raises(pytest.skip.Exception, match="IR_REQUIRE_EVIDENCE=1 to make this a failure"):
        FE.missing_evidence("training_runs/x")
    monkeypatch.setattr(FE, "REQUIRE_EVIDENCE", True)
    with pytest.raises(pytest.fail.Exception, match="not present: training_runs/x"):
        FE.missing_evidence("training_runs/x")


# ------------------------------------------------------------------ final 1: no bypass through another output root
def test_final_run_in_another_output_root_is_refused(tmp_path, no_sim):
    canon = tmp_path                                                            # = runner.DEFAULT_EVAL_ROOT (fixture)
    (canon / "ledger.jsonl").write_text(json.dumps(_entry("fyp_final_s0", [4_000_001, 4_000_030])) + "\n")
    other = tmp_path / "elsewhere"
    for seeds in (ES.eval_seeds(2, "final"), ES.eval_seeds(2, "final", base=4_000_060)):     # used and fresh seeds alike
        with pytest.raises(P.ProtocolError, match="must write to"):
            runner.evaluate(_final(), ["fixed_time"], seeds, other, "bypass", confirm_final=True, progress=lambda s: None)
    assert not other.exists() and no_sim.calls == []
    assert len(P.read_ledger(canon / "ledger.jsonl")) == 1


def test_cli_refuses_a_final_out_root_before_loading_anything(tmp_path):
    import evaluate_fyp
    with pytest.raises(SystemExit, match="always writes to"):
        evaluate_fyp.main(["--mode", "final", "--confirm-final", "--run-id", "x", "--out-root", str(tmp_path / "o"),
                           "--dqn-run", str(tmp_path / "no_such_run"), "--seed-base", "4000060"])
    assert list(tmp_path.iterdir()) == []                                       # no directory, no model loaded (it does not exist)


# ------------------------------------------------------------------ final 2: the ledger range is exactly the evaluated seed set
@pytest.mark.parametrize("seeds", [[4_000_062, 4_000_061], [4_000_061, 4_000_061], [4_000_061, 4_000_063]])
def test_final_seed_lists_must_be_sorted_unique_and_contiguous(tmp_path, no_sim, seeds):
    with pytest.raises((P.ProtocolError, ES.EvalSeedError), match="sorted, unique and contiguous|duplicate"):   # duplicates: the seed guard
        runner.evaluate(_final(), ["fixed_time"], seeds, tmp_path, "s", confirm_final=True, progress=lambda s: None)
    with pytest.raises(P.ProtocolError, match="sorted, unique and contiguous"):
        runner.assert_final_seed_list(seeds)                                    # the final-list check rejects each case on its own
    assert list(tmp_path.iterdir()) == [] and no_sim.calls == []


def test_recorded_range_equals_the_evaluated_seeds(tmp_path, no_sim):
    seeds = ES.eval_seeds(2, "final", base=4_000_060)
    runner.evaluate(_final(), ["fixed_time"], seeds, tmp_path, "ok", confirm_final=True, progress=lambda s: None)
    rec = P.read_ledger(tmp_path / "ledger.jsonl")
    assert all(e["seeds"] == [4_000_061, 4_000_062] for e in rec) and sorted({s for _, s in no_sim.calls}) == seeds
