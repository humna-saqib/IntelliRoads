"""Stage-3 live tests: the training pipeline on real SUMO.

Everything here is a tiny **smoke check** of the plumbing (60 s episodes, a handful of gradient steps) – it
proves the pipeline is wired correctly and reproducible, not that a policy has been learned.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch

pytest.importorskip("traci")
sumolib = pytest.importorskip("sumolib")

import train_dqn
from app.environment.observation import STATE_SIZE, EnvError
from app.environment.signal_safety import EXTEND, KEEP
from app.environment.traffic_env import EnvConfig, TrafficSignalEnv
from app.training import seeds as S
from app.training import runs as runs_module
from app.training.runs import BACKEND, RunDirError
from app.training.trainer import TrainConfig, evaluate_policy, train

try:
    sumolib.checkBinary("sumo")
except Exception:  # pragma: no cover
    pytest.skip("SUMO binary not available", allow_module_level=True)

TRACKED_ROUTES = BACKEND / "sumo" / "routes" / "intelliroads.rou.xml"
JUNCTIONS = ("junctionA", "junctionB", "junctionC", "junctionD")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_hashes():
    files = [TRACKED_ROUTES, BACKEND / "data" / "models" / "dqn_agent.pt", BACKEND / "final_dqn_model" / "dqn_episode_final.pt",
             BACKEND / "sumo" / "network" / "intelliroads.net.xml", BACKEND / "evaluation_results" / "eval_raw.csv"]
    return {str(f): sha(f) for f in files if f.exists()}


def tiny_cfg(tmp_path, run_id="r", **kw):
    base = dict(run_id=run_id, out_root=tmp_path, seed=7, episodes=2, horizon_s=60, val_every=1, val_n=1, warmup=32, batch_size=16,
                buffer_size=2000, updates_per_decision=1, target_update_steps=5, eps_decay_decisions=20, smoke=True)
    base.update(kw)
    return TrainConfig(**base)


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ the pipeline runs end to end on the new environment
def test_smoke_training_produces_the_expected_files_in_a_new_directory(tmp_path):
    before = protected_hashes()
    res = train(tiny_cfg(tmp_path))
    run = res["run_dir"]
    assert run == tmp_path.resolve() / "r"
    names = {p.name for p in run.iterdir()}
    assert {"config.json", "episodes.csv", "validation.csv", "best.json", "best.pt", "last.pt", "timing.json"} <= names
    assert {"ckpt_ep0001.pt", "ckpt_ep0002.pt"} <= names
    assert res["episodes_run"] == 2 and res["smoke"] is True and res["grad_steps"] > 0
    assert protected_hashes() == before, "no existing model, checkpoint, evaluation file or route file may change"
    cfg = json.loads((run / "config.json").read_text())
    assert cfg["smoke"] is True and cfg["versions"]["sumo"].startswith("SUMO") and cfg["config"]["seed"] == 7
    assert "app/training/trainer.py" in cfg["source_sha256"] and cfg["git_dirty"] in (True, False, None)


def test_checkpoints_have_no_replay_buffer(tmp_path):
    run = train(tiny_cfg(tmp_path))["run_dir"]
    for p in run.glob("*.pt"):
        ck = torch.load(p, weights_only=False)
        assert not any("replay" in k or "buffer" in k for k in ck) and p.stat().st_size < 300_000, p.name
        assert ck["state_size"] == STATE_SIZE and len(ck["feature_names"]) == STATE_SIZE


def test_uses_the_new_environment_and_never_imports_legacy_environment_or_route_writers():
    banned = {"app.environment.sumo_environment", "app.services.traci_session", "app.sumo_tools.route_generator"}
    files = [BACKEND / "train_dqn.py"] + sorted((BACKEND / "app" / "training").glob("*.py"))
    for f in files:
        for node in ast.walk(ast.parse(f.read_text())):
            mods = [node.module] if isinstance(node, ast.ImportFrom) and node.module else [a.name for a in node.names] if isinstance(node, ast.Import) else []
            assert not banned & set(mods), f"{f.name} imports a legacy module: {banned & set(mods)}"
    assert "TrafficSignalEnv" in (BACKEND / "app" / "training" / "trainer.py").read_text()


# ------------------------------------------------------------------ replay content: masks, terminal vs truncated
def test_replay_transitions_carry_valid_masks_and_correct_terminal_flags(tmp_path):
    res = train(tiny_cfg(tmp_path))
    buf = res["buffer"]
    n = len(buf)
    assert n == 2 * 12 * 4                                                         # 2 episodes x 12 decisions x 4 junctions
    assert buf.masks[:n].any(axis=1).all() and buf.next_masks[:n].any(axis=1).all()
    assert buf.masks[np.arange(n), buf.actions[:n]].all(), "every stored action was legal in its own state"
    assert buf.masks[:n, 0].all() and buf.next_masks[:n, 0].all(), "KEEP is always legal"
    assert not buf.terminated[:n].any(), "a time limit is not a terminal state"
    trunc = buf.truncated[:n].reshape(2, 12, 4)
    assert trunc[:, -1].all() and not trunc[:, :-1].any(), "only the last decision of each episode is a truncation"


def test_next_state_masks_of_consecutive_transitions_chain(tmp_path):
    buf = train(tiny_cfg(tmp_path))["buffer"]
    s, ns, m, nm = buf.states[:48].reshape(12, 4, -1), buf.next_states[:48].reshape(12, 4, -1), buf.masks[:48].reshape(12, 4, -1), buf.next_masks[:48].reshape(12, 4, -1)
    assert np.array_equal(ns[:-1], s[1:]) and np.array_equal(nm[:-1], m[1:]), "s' and its mask are the next decision's s and mask"


# ------------------------------------------------------------------ warm-up
def test_no_gradient_step_before_the_replay_buffer_reaches_the_warm_up_size(tmp_path):
    cfg = tiny_cfg(tmp_path, "warm", warmup=200, buffer_size=2000)                 # 2 episodes give only 96 transitions
    res = train(cfg)
    assert res["grad_steps"] == 0 and len(res["buffer"]) == 96
    rows = read_csv(res["run_dir"] / "episodes.csv")
    assert all(r["grad_steps"] == "0" and r["mean_loss"] == "" for r in rows)


def test_learning_starts_exactly_when_the_warm_up_size_is_reached(tmp_path):
    res = train(tiny_cfg(tmp_path, "warm2", warmup=48, batch_size=16))             # buffer hits 48 at the last decision of episode 1
    rows = read_csv(res["run_dir"] / "episodes.csv")
    assert rows[0]["grad_steps"] == "1" and int(rows[1]["grad_steps"]) == 1 + 12   # then one update per decision


def test_target_network_is_synchronised_every_n_gradient_steps(tmp_path):
    """Episode 1 reaches the warm-up on its last decision (1 gradient step); episode 2 adds 12 -> 13 steps in total.
    With a sync every 5 gradient steps the target must have been refreshed after steps 5 and 10 only."""
    res = train(tiny_cfg(tmp_path, "tgt", warmup=48, batch_size=16, target_update_steps=5))
    rows = read_csv(res["run_dir"] / "episodes.csv")
    assert [int(r["grad_steps"]) for r in rows] == [1, 13] and [int(r["target_syncs"]) for r in rows] == [0, 2]
    res2 = train(tiny_cfg(tmp_path, "tgt2", warmup=48, batch_size=16, target_update_steps=7))
    assert [int(r["target_syncs"]) for r in read_csv(res2["run_dir"] / "episodes.csv")] == [0, 1]       # step 7 only


# ------------------------------------------------------------------ validation-only checkpoint selection
def test_selected_checkpoint_is_the_best_validation_score_and_only_validation_seeds_are_used(tmp_path):
    res = train(tiny_cfg(tmp_path, "sel", episodes=4, val_every=2, val_n=2))
    run = res["run_dir"]
    val = read_csv(run / "validation.csv")
    scores = [float(r["score"]) for r in val]
    best = json.loads((run / "best.json").read_text())
    first_min = int(val[int(np.argmin(scores))]["episode"])                        # ties -> earliest
    assert best["episode"] == first_min == res["best_episode"] and best["score"] == min(scores)
    assert torch.equal(torch.load(run / "best.pt", weights_only=False)["policy_net"]["net.0.weight"],
                       torch.load(run / best["file"], weights_only=False)["policy_net"]["net.0.weight"])
    cfg = json.loads((run / "config.json").read_text())
    train_lo, train_hi = cfg["train_seeds"]
    assert all(not (train_lo <= v <= train_hi) for v in cfg["val_seeds"]) and not set(cfg["val_seeds"]) & {s for s in range(train_lo, train_hi + 1)}
    for r in val:
        assert all(int(x) in cfg["val_seeds"] for x in r["seeds"].split())


def test_validation_refuses_evaluation_seeds(tmp_path):
    env = TrafficSignalEnv(EnvConfig(horizon_s=20))
    try:
        from app.training.double_dqn import MaskedDoubleDQN
        agent = MaskedDoubleDQN(STATE_SIZE, seed=0)
        for seed in (1_000_001, 4_000_001):
            with pytest.raises(S.SeedError, match="protected"):
                evaluate_policy(agent, env, [seed])
        assert env.conn is None, "no simulation may even be started for a protected seed"
    finally:
        env.close()


def test_training_refuses_protected_seed_bases_before_creating_anything(tmp_path):
    with pytest.raises(S.SeedError):
        train(tiny_cfg(tmp_path, "bad", train_seed_base=999_999))
    with pytest.raises(S.SeedError):
        train(tiny_cfg(tmp_path, "bad2", val_seed_base=3_999_999))
    assert list(tmp_path.iterdir()) == []


def test_early_stopping_uses_validation_progress_only(tmp_path):
    res = train(tiny_cfg(tmp_path, "pat", episodes=6, val_every=1, patience=1))   # the policy barely changes -> no validation improvement
    assert res["stopped_early"] is True and res["episodes_run"] < 6


# ------------------------------------------------------------------ reproducibility
def _fingerprint(run: Path):
    ck = torch.load(run / "last.pt", weights_only=False)
    return ((run / "episodes.csv").read_text(), (run / "validation.csv").read_text(),
            {k: v.clone() for k, v in ck["policy_net"].items()}, json.loads((run / "config.json").read_text())["source_sha256"])


def test_same_seed_reproduces_logs_and_weights_exactly(tmp_path):
    a = _fingerprint(train(tiny_cfg(tmp_path, "a", seed=3))["run_dir"])
    b = _fingerprint(train(tiny_cfg(tmp_path, "b", seed=3))["run_dir"])
    assert a[0] == b[0] and a[1] == b[1] and a[3] == b[3]
    assert all(torch.equal(a[2][k], b[2][k]) for k in a[2])


def test_different_seed_gives_a_different_run(tmp_path):
    a = _fingerprint(train(tiny_cfg(tmp_path, "a", seed=3))["run_dir"])
    c = _fingerprint(train(tiny_cfg(tmp_path, "c", seed=4))["run_dir"])
    assert a[0] != c[0] and not all(torch.equal(a[2][k], c[2][k]) for k in a[2])


# ------------------------------------------------------------------ route files and protected artefacts
def test_training_never_modifies_or_adds_files_in_the_tracked_route_directory(tmp_path):
    routes = BACKEND / "sumo" / "routes"
    before_listing = sorted(p.name for p in routes.iterdir())
    before = sha(TRACKED_ROUTES)
    train(tiny_cfg(tmp_path))
    assert sha(TRACKED_ROUTES) == before and sorted(p.name for p in routes.iterdir()) == before_listing


def test_environment_refuses_route_files_outside_its_temporary_directory(tmp_path):
    before = sha(TRACKED_ROUTES)
    env = TrafficSignalEnv(EnvConfig(horizon_s=20), route_factory=lambda seed, out_dir: TRACKED_ROUTES)
    try:
        with pytest.raises(EnvError, match="temporary directory"):
            env.reset(seed=1)
    finally:
        env.close()
    assert sha(TRACKED_ROUTES) == before and env.conn is None


# ------------------------------------------------------------------ CLI
def test_cli_smoke_run_is_labelled_and_goes_to_the_requested_directory(tmp_path, capsys):
    res = train_dqn.main(["--smoke", "--run-id", "cli", "--out-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "SMOKE CHECK (not a training run)" in out and res["run_dir"].name == "smoke_cli" and res["smoke"] is True
    assert (res["run_dir"] / "best.pt").exists()


def test_cli_never_reuses_a_run_directory(tmp_path):
    train_dqn.main(["--smoke", "--run-id", "once", "--out-root", str(tmp_path)])
    with pytest.raises(RunDirError, match="already exists"):
        train_dqn.main(["--smoke", "--run-id", "once", "--out-root", str(tmp_path)])


def test_cli_refuses_protected_output_roots_without_writing(tmp_path, monkeypatch):
    """Uses a stand-in protected folder inside tmp_path – the real protected folders are never an output target in tests."""
    fake = tmp_path / "final_dqn_model"
    fake.mkdir()
    (fake / "dqn_episode_final.pt").write_bytes(b"precious")
    monkeypatch.setattr(runs_module, "PROTECTED_DIRS", (fake,))
    with pytest.raises(RunDirError, match="protected"):
        train_dqn.main(["--smoke", "--run-id", "x", "--out-root", str(fake)])
    assert sorted(p.name for p in fake.iterdir()) == ["dqn_episode_final.pt"] and (fake / "dqn_episode_final.pt").read_bytes() == b"precious"


# ------------------------------------------------------------------ elapsed-phase normalisation on the real signal
def test_elapsed_feature_reaches_exactly_one_at_the_maximum_green_without_clipping():
    env = TrafficSignalEnv(EnvConfig(horizon_s=100, decision_interval_s=1))
    try:
        env.reset(seed=1)
        peak, clipped = 0.0, 0
        for _ in range(70):
            m = env.action_masks()["junctionA"]
            acts = {j: KEEP for j in JUNCTIONS}
            acts["junctionA"] = EXTEND if m[EXTEND] else KEEP
            r = env.step(acts)
            peak = max(peak, r.obs["junctionA"][10]); clipped += r.info["clipped_features"]
            if env.sim_time == 59:
                assert r.obs["junctionA"][10] == pytest.approx(59 / 60)
        assert peak == pytest.approx(1.0) and clipped == 0, "60 s green / 60 s normaliser: full range, no saturation"
    finally:
        env.close()
