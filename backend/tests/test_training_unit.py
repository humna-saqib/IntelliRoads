"""Stage-3 unit tests (no SUMO): replay masks, mask-aware Double-DQN targets, warm-up/target-sync bookkeeping,
seeds, run directories, validation-only checkpoint selection, checkpoint format, elapsed normalisation."""

from __future__ import annotations

import inspect
import random
from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn as nn

from app.environment.observation import ELAPSED_MAX_S, EnvError, discover_topology, encode_state, read_measurement
from app.environment.signal_safety import SignalSafetyConfig
from app.training import seeds as S
from app.training.double_dqn import MaskedDoubleDQN, double_dqn_targets
from app.training.replay import MaskedReplayBuffer
from app.training import runs as runs_module
from app.training.runs import (
    BACKEND,
    DEFAULT_RUNS_ROOT,
    assert_output_root_allowed,
    CHECKPOINT_FORMAT,
    CheckpointSelector,
    RunDirError,
    create_run_dir,
    load_checkpoint,
    save_checkpoint,
)
from app.training.trainer import TrainConfig

SS = 11
M_ALL = [True] * 4


def push(buf, a=0, r=0.0, term=False, trunc=False, mask=M_ALL, nmask=M_ALL, s=0.0, ns=1.0):
    buf.push([s] * SS, a, r, [ns] * SS, term, trunc, mask, nmask)


# ------------------------------------------------------------------ replay: masks
def test_replay_stores_current_and_next_state_masks():
    buf = MaskedReplayBuffer(10, SS, seed=0)
    push(buf, a=2, mask=[True, False, True, True], nmask=[True, False, False, False])
    push(buf, a=0, mask=[True, True, False, False], nmask=[True, True, True, True])
    b = buf.sample(2)
    order = b.actions.squeeze(1).tolist()
    for row, act in enumerate(order):
        if act == 2:
            assert b.masks[row].tolist() == [True, False, True, True] and b.next_masks[row].tolist() == [True, False, False, False]
        else:
            assert b.masks[row].tolist() == [True, True, False, False] and b.next_masks[row].tolist() == [True] * 4
    assert b.masks.dtype == torch.bool and b.next_masks.dtype == torch.bool and b.states.shape == (2, SS)


def test_replay_ring_buffer_overwrites_oldest():
    buf = MaskedReplayBuffer(5, SS, seed=0)
    for i in range(8):
        push(buf, r=float(i))
    assert len(buf) == 5 and sorted(buf.rewards.tolist()) == [3.0, 4.0, 5.0, 6.0, 7.0]


@pytest.mark.parametrize("kw", [
    dict(a=1, mask=[True, False, True, True]),                      # stored action is illegal under its own mask
    dict(mask=[False] * 4), dict(nmask=[False] * 4),                # no legal action
    dict(mask=[True, True]), dict(nmask=[True] * 5),                # wrong shape
    dict(r=float("nan")), dict(s=float("inf")),
])
def test_replay_rejects_invalid_transitions(kw):
    with pytest.raises(ValueError):
        push(MaskedReplayBuffer(5, SS, seed=0), **kw)


def test_replay_rejects_bad_action_id_and_oversized_sample():
    buf = MaskedReplayBuffer(5, SS, seed=0)
    with pytest.raises(ValueError):
        push(buf, a=7)
    push(buf)
    with pytest.raises(ValueError, match="cannot sample"):
        buf.sample(2)


def test_replay_terminated_and_truncated_are_stored_separately():
    buf = MaskedReplayBuffer(5, SS, seed=0)
    push(buf, term=False, trunc=True)                                # time limit
    push(buf, term=True, trunc=False)                                # true terminal
    b = buf.sample(2)
    assert sorted(b.terminated.tolist()) == [0.0, 1.0] and sorted(buf.truncated[:2].tolist()) == [False, True]
    assert buf.terminated[0] == False and buf.truncated[0] == True    # noqa: E712 - truncation does NOT cut the bootstrap


def test_replay_sampling_is_reproducible_for_a_seed():
    def run(seed):
        buf = MaskedReplayBuffer(50, SS, seed=seed)
        for i in range(50):
            push(buf, r=float(i))
        return buf.sample(10).rewards.tolist()
    assert run(3) == run(3) and run(3) != run(4)


# ------------------------------------------------------------------ mask-aware Double-DQN target
class FixedQ(nn.Module):
    """Returns the same Q row for every input (a stand-in network with known values)."""

    def __init__(self, row):
        super().__init__()
        self.row = torch.tensor([row], dtype=torch.float32)

    def forward(self, x):
        return self.row.expand(x.shape[0], -1)


def targets(policy_q, target_q, mask, reward=1.0, term=0.0, gamma=0.5):
    n = 1
    return double_dqn_targets(FixedQ(policy_q), FixedQ(target_q), torch.zeros(n, SS), torch.tensor([mask]), torch.tensor([reward]),
                              torch.tensor([term]), gamma).item()


def test_illegal_next_action_cannot_be_selected_for_bootstrapping():
    # policy would pick action 1 (value 9) – but SWITCH is illegal in the next state, so the best LEGAL action (3) is used
    masked = targets([1.0, 9.0, 2.0, 3.0], [10.0, 20.0, 30.0, 40.0], [True, False, True, True])
    assert masked == pytest.approx(1.0 + 0.5 * 40.0)
    unmasked = targets([1.0, 9.0, 2.0, 3.0], [10.0, 20.0, 30.0, 40.0], [True] * 4)
    assert unmasked == pytest.approx(1.0 + 0.5 * 20.0) and masked != unmasked, "the unmasked rule bootstraps from an unreachable action"


def test_keep_only_mask_forces_the_keep_value():
    assert targets([0.1, 9, 9, 9], [7.0, 99, 99, 99], [True, False, False, False]) == pytest.approx(1.0 + 0.5 * 7.0)


def test_double_dqn_decouples_selection_from_evaluation():
    # policy selects action 3; target evaluates it (40) even though the target net's own best legal action is 2 (50)
    y = targets([1.0, 0.0, 2.0, 3.0], [10.0, 20.0, 50.0, 40.0], M_ALL)
    assert y == pytest.approx(1.0 + 0.5 * 40.0)


def test_terminal_transitions_do_not_bootstrap_but_truncations_do():
    pq, tq = [0.0, 0.0, 0.0, 1.0], [5.0, 5.0, 5.0, 8.0]
    terminal = targets(pq, tq, M_ALL, reward=2.0, term=1.0)
    truncated = targets(pq, tq, M_ALL, reward=2.0, term=0.0)             # truncation is stored as terminated = 0
    assert terminal == pytest.approx(2.0)
    assert truncated == pytest.approx(2.0 + 0.5 * 8.0)


def test_empty_next_mask_is_rejected():
    with pytest.raises(ValueError, match="no legal action"):
        targets([0.0] * 4, [0.0] * 4, [False] * 4)


def test_targets_carry_no_gradient_and_target_net_is_not_trained():
    torch.manual_seed(0)
    agent = MaskedDoubleDQN(SS, seed=0)
    buf = MaskedReplayBuffer(64, SS, seed=0)
    rng = np.random.default_rng(0)
    for _ in range(64):
        buf.push(rng.random(SS), int(rng.integers(4)), float(rng.normal()), rng.random(SS), False, False, M_ALL, M_ALL)
    before = [p.clone() for p in agent.target_net.parameters()]
    agent.train_step(buf.sample(16))
    assert all(torch.equal(a, b) for a, b in zip(before, agent.target_net.parameters()))
    assert any(not torch.equal(a, b) for a, b in zip(before, agent.policy_net.parameters()))


def test_training_fits_a_fixed_regression_batch():
    torch.manual_seed(1)
    agent = MaskedDoubleDQN(SS, lr=5e-3, seed=1)
    buf = MaskedReplayBuffer(32, SS, seed=1)
    rng = np.random.default_rng(1)
    for _ in range(32):                                                   # terminal transitions: target == reward
        buf.push(rng.random(SS), 0, 1.0, rng.random(SS), True, False, M_ALL, M_ALL)
    losses = [agent.train_step(buf.sample(32))[0] for _ in range(300)]
    assert losses[-1] < 0.05 * losses[0]


# ------------------------------------------------------------------ target updates by gradient-step count; warm-up config
def test_target_network_is_synchronised_by_gradient_steps_not_epochs():
    torch.manual_seed(2)
    agent = MaskedDoubleDQN(SS, lr=1e-2, seed=2)
    buf = MaskedReplayBuffer(64, SS, seed=2)
    rng = np.random.default_rng(2)
    for _ in range(64):
        buf.push(rng.random(SS), int(rng.integers(4)), float(rng.normal()), rng.random(SS), False, False, M_ALL, M_ALL)
    equal = lambda: all(torch.equal(a, b) for a, b in zip(agent.policy_net.parameters(), agent.target_net.parameters()))
    synced = []
    for step in range(1, 7):
        agent.train_step(buf.sample(16))
        synced.append(agent.maybe_sync_target(3))
    assert synced == [False, False, True, False, False, True]
    assert equal(), "after the 6th gradient step (a multiple of 3) the target equals the policy"
    agent.train_step(buf.sample(16))
    assert not equal() and agent.grad_steps == 7
    with pytest.raises(ValueError):
        agent.maybe_sync_target(0)


def test_exploration_is_epsilon_greedy_over_legal_actions_and_seeded():
    a1, a2 = MaskedDoubleDQN(SS, seed=5), MaskedDoubleDQN(SS, seed=5)
    state, mask = np.zeros(SS), [True, False, True, False]
    draws = [a1.act(state, mask, 1.0) for _ in range(200)]
    assert set(draws) == {0, 2}
    assert draws == [a2.act(state, mask, 1.0) for _ in range(200)]
    assert a1.act(state, mask, 0.0) in (0, 2) and a1.random_legal(mask) in (0, 2)
    with pytest.raises(ValueError):
        a1.act(state, [False] * 4, 0.5)


def test_train_config_validation_and_epsilon_schedule():
    cfg = TrainConfig(run_id="x", warmup=100, batch_size=32, episodes=10, horizon_s=100, decision_interval_s=5, eps_start=1.0, eps_end=0.1)
    assert cfg.decay_decisions == 100                                      # half of 10 * 20 decisions
    assert cfg.epsilon(0) == 1.0 and cfg.epsilon(50) == pytest.approx(0.55) and cfg.epsilon(100) == pytest.approx(0.1) == cfg.epsilon(10_000)
    for kw in (dict(warmup=8, batch_size=16), dict(buffer_size=10, warmup=100), dict(episodes=0), dict(select_metric="loss"),
               dict(eps_end=0.9, eps_start=0.1), dict(target_update_steps=0)):
        with pytest.raises(ValueError):
            TrainConfig(run_id="x", **kw)


# ------------------------------------------------------------------ seeds
def test_seed_ranges_are_disjoint_and_avoid_the_protected_ranges():
    train = [S.train_seed(e) for e in range(1, 2001)]
    val = S.val_seeds(50)
    S.assert_disjoint(train, val)
    assert train[0] == 2_000_001 and val[0] == 3_000_001
    for seed in train + val:
        S.assert_not_protected(seed)
    with pytest.raises(S.SeedError):
        S.assert_disjoint([1, 2, 3], [3, 4])


@pytest.mark.parametrize("seed", [1_000_000, 1_000_001, 1_500_000, 1_999_999, 4_000_000, 4_000_001, 4_999_999, 5_000_000, 5_999_999])
def test_protected_evaluation_seeds_are_refused(seed):
    with pytest.raises(S.SeedError, match="protected"):
        S.assert_not_protected(seed)


@pytest.mark.parametrize("seed", [0, 999_999, 2_000_000, 3_999_999, 6_000_000])
def test_seeds_next_to_the_protected_ranges_are_allowed(seed):
    assert S.assert_not_protected(seed) == seed


def test_training_and_validation_refuse_a_seed_base_inside_a_protected_range():
    with pytest.raises(S.SeedError):
        S.train_seed(1, base=999_999)                                      # -> 1,000,000
    with pytest.raises(S.SeedError):
        S.val_seeds(3, base=3_999_999)                                     # -> 4,000,000


def test_seed_everything_fixes_python_numpy_and_torch():
    def draw(seed):
        S.seed_everything(seed)
        return random.random(), float(np.random.rand()), float(torch.rand(1)), MaskedDoubleDQN(SS, seed=seed).policy_net.net[0].weight.sum().item()
    assert draw(11) == draw(11) and draw(11) != draw(12)
    assert torch.get_num_threads() == 1 and torch.are_deterministic_algorithms_enabled()
    with pytest.raises(S.SeedError):
        S.seed_everything(-1)


# ------------------------------------------------------------------ run directories and checkpoints never overwrite
def test_run_directory_is_new_and_never_reused(tmp_path):
    d = create_run_dir(tmp_path, "run1")
    assert d == tmp_path.resolve() / "run1" and d.is_dir()
    with pytest.raises(RunDirError, match="already exists"):
        create_run_dir(tmp_path, "run1")


@pytest.mark.parametrize("bad", ["", "../x", "a/b", ".hidden/..", "x" * 90, "with space"])
def test_run_id_must_be_a_plain_name(tmp_path, bad):
    with pytest.raises(RunDirError, match="invalid run id"):
        create_run_dir(tmp_path, bad)


@pytest.mark.parametrize("rel", ["data", "data/models", "final_dqn_model", "evaluation_results", "evaluation_v2", "validation_results",
                                 "sumo/routes", "sumo", "app", "tests"])
def test_real_protected_directories_are_refused_as_output_roots(rel):
    """Pure check: never touches the real directories (so it cannot write there even if the guard were broken)."""
    with pytest.raises(RunDirError, match="protected"):
        assert_output_root_allowed(BACKEND / rel)


def test_default_output_root_is_allowed_and_the_check_creates_nothing():
    before = BACKEND / "training_runs"
    existed = before.exists()
    assert assert_output_root_allowed(DEFAULT_RUNS_ROOT) == DEFAULT_RUNS_ROOT.resolve()
    assert before.exists() == existed


def test_create_run_dir_refuses_protected_roots_without_writing(tmp_path, monkeypatch):
    """Integration of the guard with directory creation, on a stand-in 'protected' folder inside tmp_path only."""
    fake = tmp_path / "models"
    fake.mkdir()
    (fake / "dqn_agent.pt").write_bytes(b"precious")
    monkeypatch.setattr(runs_module, "PROTECTED_DIRS", (fake,))
    for root in (fake, fake / "nested"):
        with pytest.raises(RunDirError, match="protected"):
            create_run_dir(root, "new_run")
    assert sorted(p.name for p in fake.iterdir()) == ["dqn_agent.pt"] and (fake / "dqn_agent.pt").read_bytes() == b"precious"


def _agent():
    torch.manual_seed(0)
    return MaskedDoubleDQN(SS, seed=0)


def test_checkpoints_contain_no_replay_buffer_and_are_small(tmp_path):
    agent = _agent()
    p = tmp_path / "c.pt"
    save_checkpoint(p, agent, episode=3, decisions=10, val_score=1.5, val_metric="mean_wait_s", train_config={"a": 1})
    ck = torch.load(p, weights_only=False)
    assert ck["format"] == CHECKPOINT_FORMAT and ck["episode"] == 3 and ck["val_score"] == 1.5
    assert not any("replay" in k or "buffer" in k or "memory" in k for k in ck)
    assert p.stat().st_size < 300_000, "a model-only checkpoint is ~0.1 MB; a replay buffer would be many MB"


def test_checkpoint_round_trip_and_refusals(tmp_path):
    a, b = _agent(), MaskedDoubleDQN(SS, seed=1)
    p = tmp_path / "c.pt"
    save_checkpoint(p, a, episode=1, decisions=1, val_score=0.0, val_metric="mean_wait_s", train_config={})
    load_checkpoint(p, b)
    assert all(torch.equal(x, y) for x, y in zip(a.policy_net.parameters(), b.policy_net.parameters()))
    original = p.read_bytes()
    with pytest.raises(RunDirError, match="refusing to overwrite"):
        save_checkpoint(p, b, episode=2, decisions=2, val_score=0.0, val_metric="mean_wait_s", train_config={})
    assert p.read_bytes() == original, "an existing checkpoint must be left byte-identical"
    with pytest.raises(RunDirError, match="dimensions"):
        load_checkpoint(p, MaskedDoubleDQN(SS + 1, seed=0))
    torch.save({"format": "other"}, tmp_path / "x.pt")
    with pytest.raises(RunDirError, match="not a"):
        load_checkpoint(tmp_path / "x.pt", b)


# ------------------------------------------------------------------ checkpoint selection uses validation scores only
def test_selector_picks_the_best_validation_score_and_keeps_the_earlier_on_ties():
    sel = CheckpointSelector("mean_wait_s")                                # lower is better
    flags = [sel.update(ep, sc) for ep, sc in [(20, 5.0), (40, 3.0), (60, 4.0), (80, 3.0), (100, 2.5)]]
    assert flags == [True, True, False, False, True] and (sel.best_episode, sel.best_score) == (100, 2.5)
    tie = CheckpointSelector("mean_wait_s")
    tie.update(20, 3.0); tie.update(40, 3.0)
    assert tie.best_episode == 20


def test_selector_respects_the_metric_direction_and_rejects_bad_input():
    sel = CheckpointSelector("mean_reward")                                # higher is better
    assert [sel.update(e, s) for e, s in [(1, -5.0), (2, -2.0), (3, -3.0)]] == [True, True, False] and sel.best_episode == 2
    with pytest.raises(ValueError):
        CheckpointSelector("training_loss")
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            sel.update(4, bad)


def test_selection_interface_accepts_only_a_validation_score():
    params = list(inspect.signature(CheckpointSelector.update).parameters)
    assert params == ["self", "episode", "val_score"], "no training return / loss / evaluation-seed argument may exist"


# ------------------------------------------------------------------ elapsed-phase normalisation
def test_elapsed_normaliser_equals_the_maximum_green_so_the_feature_spans_0_to_1():
    assert ELAPSED_MAX_S == SignalSafetyConfig().max_green_s == 60.0


def _enc(elapsed, elapsed_max_s):
    from types import SimpleNamespace
    lanes = ["a", "b", "c", "d"]
    logic = SimpleNamespace(programID="0", phases=[SimpleNamespace(state=s) for s in ("GGrr", "yyrr", "rrGG", "rryy")])
    conn = SimpleNamespace(
        trafficlight=SimpleNamespace(getControlledLinks=lambda j: [[(l, "o", "v")] for l in lanes], getAllProgramLogics=lambda j: [logic],
                                     getProgram=lambda j: "0"),
        lane=SimpleNamespace(getLength=lambda l: 300.0, getLastStepVehicleNumber=lambda l: 0, getLastStepHaltingNumber=lambda l: 0,
                             getWaitingTime=lambda l: 0.0, getLastStepOccupancy=lambda l: 0.0))
    topo = discover_topology(conn, "J")
    return encode_state(topo, read_measurement(conn, topo), 0, elapsed, elapsed_max_s)


@pytest.mark.parametrize("elapsed,max_green,expected", [(0, 60, 0.0), (30, 60, 0.5), (60, 60, 1.0), (45, 45, 1.0), (10, 45, 10 / 45)])
def test_elapsed_feature_is_elapsed_over_the_configured_max_green(elapsed, max_green, expected):
    vec, clipped = _enc(float(elapsed), float(max_green))
    assert vec[10] == pytest.approx(expected) and clipped == 0


def test_elapsed_feature_clips_and_counts_when_it_exceeds_the_normaliser_and_rejects_bad_normalisers():
    vec, clipped = _enc(70.0, 60.0)
    assert vec[10] == 1.0 and clipped == 1
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(EnvError):
            _enc(10.0, bad)
