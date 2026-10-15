"""Stage-1 live-SUMO tests for ``TrafficSignalEnv``.

Every test starts real SUMO processes (no mock mode). Measurements are compared with
*independent* TraCI queries made by the test itself (vehicle-level getters, the XML network
file), never with the code under test.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("traci")
sumolib = pytest.importorskip("sumolib")

from app.agent.dqn_agent import DQNAgent
from app.environment.observation import ELAPSED_MAX_S, STATE_SIZE, EnvError, encode_state, read_measurement
from app.environment.traffic_env import (
    DEFAULT_SUMO_CONFIG,
    EnvConfig,
    TrafficSignalEnv,
    replay_done_flag,
)

BACKEND = Path(__file__).resolve().parents[1]
NET_XML = BACKEND / "sumo" / "network" / "intelliroads.net.xml"
TRACKED_ROUTES = BACKEND / "sumo" / "routes" / "intelliroads.rou.xml"
JUNCTIONS = ("junctionA", "junctionB", "junctionC", "junctionD")
KEEP = {j: 0 for j in JUNCTIONS}

try:
    sumolib.checkBinary("sumo")
except Exception:  # pragma: no cover
    pytest.skip("SUMO binary not available", allow_module_level=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def make_env():
    envs = []

    def _make(horizon=300, interval=5, **kw):
        env = TrafficSignalEnv(EnvConfig(horizon_s=horizon, decision_interval_s=interval), **kw)
        envs.append(env)
        return env

    yield _make
    for e in envs:
        e.close()


def legal_random(env, rng):
    """One random *legal* action per junction (Stage 2: illegal actions are rejected by the environment)."""
    return {j: int(rng.choice(np.flatnonzero(m))) for j, m in env.action_masks().items()}


def rollout(env, steps, policy=None):
    """Run ``steps`` decisions (``policy(env) -> actions``, default KEEP); return (obs_before, actions, StepResult) list."""
    out, obs = [], env.reset(seed=7) if env.conn is None else None
    cur = {j: v.copy() for j, v in obs.items()} if obs else None
    for t in range(steps):
        acts = policy(env) if policy else dict(KEEP)
        res = env.step(acts)
        out.append((cur, acts, res))
        cur = res.obs
    return out


# ------------------------------------------------------------------ topology: all four incoming lanes
def test_all_four_incoming_lanes_of_each_junction_are_observed(make_env):
    root = ET.parse(NET_XML).getroot()
    expected = {j: set() for j in JUNCTIONS}
    for edge in root.findall("edge"):
        if edge.get("function") == "internal" or edge.get("to") not in expected:
            continue
        expected[edge.get("to")].update(l.get("id") for l in edge.findall("lane"))
    env = make_env()
    env.reset(seed=1)
    for j in JUNCTIONS:
        topo = env.topology[j]
        assert set(topo.lanes) == expected[j] and len(topo.lanes) == 4, j
        assert sorted(len(g) for g in topo.groups) == [2, 2]


# ------------------------------------------------------------------ measurement vs independent queries
def test_measurements_equal_independent_vehicle_level_queries(make_env):
    env = make_env(horizon=240)
    env.reset(seed=3)
    res = None
    for _ in range(40):                                   # 200 s of KEEP: traffic has built up
        res = env.step(KEEP)
    conn = env.conn
    for j in JUNCTIONS:
        m = res.info["metrics"][j]
        cnt = halt = wait = occ_len = 0.0
        for lane in env.topology[j].lanes:
            ids = conn.lane.getLastStepVehicleIDs(lane)
            cnt += len(ids)
            halt += sum(1 for v in ids if conn.vehicle.getSpeed(v) < 0.1)       # SUMO halting threshold
            wait += sum(conn.vehicle.getWaitingTime(v) for v in ids)
            occ_len += sum(conn.vehicle.getLength(v) for v in ids)
        assert m.count == cnt, j
        assert m.halting == halt, j                                             # the supported TraCI API gives the true queue
        assert m.mean_wait_s == pytest.approx(wait / cnt if cnt else 0.0, abs=1e-6), j
        assert m.occupancy == pytest.approx(occ_len / sum(env.topology[j].lengths_m), abs=0.02), j


def test_queue_and_waiting_features_vary_with_traffic_instead_of_being_constant(make_env):
    env = make_env(horizon=400)
    env.reset(seed=11)
    halting, wait, counts = [], [], []
    for _ in range(80):
        r = env.step(KEEP)
        for j in JUNCTIONS:
            halting.append(r.obs[j][1]); wait.append(r.obs[j][2]); counts.append(r.obs[j][0])
    assert len(set(np.round(halting, 6))) > 3 and max(halting) > 0.0, "queue feature must follow real halting vehicles"
    assert max(wait) > 0.0, "waiting-time feature must become non-zero under load"
    assert len(set(np.round(counts, 6))) > 3


def test_observations_are_finite_bounded_and_unclipped_under_normal_traffic(make_env):
    env = make_env(horizon=300)
    env.reset(seed=5)
    rng = np.random.default_rng(0)
    for _ in range(60):
        r = env.step(legal_random(env, rng))
        for v in r.obs.values():
            assert v.shape == (STATE_SIZE,) and np.isfinite(v).all() and v.min() >= 0.0 and v.max() <= 1.0
            assert v[6:10].sum() == 1.0
        assert r.info["clipped_features"] == 0


# ------------------------------------------------------------------ phase encoding and elapsed time
def test_phase_one_hot_and_elapsed_time_follow_the_traffic_light(make_env):
    """KEEP-only: elapsed = programmed phase length - SUMO's own remaining time (getNextSwitch - now).

    (TraCI reports a scheduled switch one second after its scheduled time; deriving elapsed from the poll
    time would be 1 s too small after every natural switch.)"""
    nominal = {0: 30.0, 1: 5.0, 2: 30.0, 3: 5.0}
    env = make_env(horizon=120, interval=1)
    env.reset(seed=2)
    tl = env.conn.trafficlight
    seen = set()
    for _ in range(100):
        r = env.step(KEEP)
        phase = tl.getPhase("junctionA"); seen.add(phase)
        remaining = tl.getNextSwitch("junctionA") - env.sim_time
        v = r.obs["junctionA"]
        assert int(np.argmax(v[6:10])) == phase
        assert v[10] * ELAPSED_MAX_S == pytest.approx(nominal[phase] - remaining), (env.sim_time, phase)
    assert seen == {0, 1, 2, 3}, "the 100 s run must cover a full signal cycle"


def test_action_effect_is_visible_in_the_next_observation(make_env):
    env = make_env(horizon=120, interval=2)
    env.reset(seed=4)
    for _ in range(5):                                  # t = 10: still inside the first green (phase 0)
        r = env.step(KEEP)
    assert int(np.argmax(r.obs["junctionA"][6:10])) == 0 and r.obs["junctionA"][10] * ELAPSED_MAX_S == pytest.approx(10.0)
    acts = dict(KEEP); acts["junctionA"] = 1            # SWITCH_TO_NEXT_PHASE on A only
    r = env.step(acts)
    assert int(np.argmax(r.obs["junctionA"][6:10])) == 1, "SWITCH must show up as the yellow phase in the next state"
    assert r.obs["junctionA"][10] * ELAPSED_MAX_S == pytest.approx(2.0)
    assert int(np.argmax(r.obs["junctionB"][6:10])) == 0 and r.obs["junctionB"][10] * ELAPSED_MAX_S == pytest.approx(12.0)


# ------------------------------------------------------------------ transition semantics
def test_step_advances_exactly_one_decision_interval_and_reads_state_after_the_advance(make_env):
    env = make_env(horizon=100, interval=5)
    env.reset(seed=6)
    assert env.sim_time == 0.0
    for k in range(1, 8):
        r = env.step(KEEP)
        assert env.sim_time == 5.0 * k == env.conn.simulation.getTime() == r.info["sim_time"]
        # the returned observation is exactly the measurement of the *current* (post-advance) instant
        for j in JUNCTIONS:
            m = read_measurement(env.conn, env.topology[j])
            vec, _ = encode_state(env.topology[j], m, env.conn.trafficlight.getPhase(j), r.info["elapsed_s"][j])
            np.testing.assert_array_equal(vec, r.obs[j])


def test_next_state_differs_from_state_unlike_the_legacy_same_instant_read(make_env):
    env = make_env(horizon=300)
    steps = rollout(env, 60)
    same = total = 0
    for before, _, res in steps:
        for j in JUNCTIONS:
            total += 1
            same += int(np.array_equal(before[j][:6], res.obs[j][:6]))         # traffic features only
    assert same / total < 0.5, f"{same}/{total} transitions have an unchanged traffic state (legacy buffer: 100%)"


def test_replay_transitions_are_continuous_and_trainable(make_env):
    env = make_env(horizon=300)
    rng = np.random.default_rng(1)
    steps = rollout(env, 60, policy=lambda e: legal_random(e, rng))
    agent = DQNAgent(state_size=STATE_SIZE, action_size=4, device="cpu", normalize_inputs=False, batch_size=16)
    last_next = None
    for before, acts, res in steps:
        for j in JUNCTIONS:
            agent.store_transition(list(before[j]), acts[j], res.rewards[j], list(res.obs[j]), replay_done_flag(res.terminated, res.truncated))
        if last_next is not None:                                               # s'_k of step k == s of step k+1
            for j in JUNCTIONS:
                np.testing.assert_array_equal(last_next[j], before[j])
        last_next = res.obs
    assert len(agent.memory) == 60 * 4
    assert all(e.done is False for e in agent.memory.memory)
    loss, q = agent.train_step(batch_size=16)
    assert np.isfinite(loss) and np.isfinite(q)


# ------------------------------------------------------------------ episodes: duration, reset, terminal vs truncation
def test_default_episode_is_1800_simulated_seconds():
    cfg = EnvConfig()
    assert cfg.horizon_s == 1800 and cfg.decision_interval_s == 5 and cfg.horizon_s // cfg.decision_interval_s == 360


def test_truncation_at_horizon_is_not_termination_and_steps_after_the_end_fail(make_env):
    env = make_env(horizon=60, interval=5)
    env.reset(seed=8)
    for k in range(1, 12):
        r = env.step(KEEP)
        assert (r.terminated, r.truncated) == (False, False), k
    r = env.step(KEEP)
    assert env.sim_time == 60.0 and r.truncated is True and r.terminated is False
    assert replay_done_flag(r.terminated, r.truncated) is False, "time-limit truncation must keep bootstrapping"
    with pytest.raises(EnvError, match="finished"):
        env.step(KEEP)


def test_true_termination_when_nothing_is_left_to_simulate(make_env, tmp_path):
    def empty_routes(seed, out_dir):
        p = out_dir / "empty.rou.xml"
        p.write_text('<routes><vType id="passenger" vClass="passenger"/></routes>\n')
        return p

    env = make_env(horizon=60, interval=5, route_factory=empty_routes)
    env.reset(seed=1)
    r = env.step(KEEP)
    assert r.terminated is True and r.truncated is False
    assert replay_done_flag(r.terminated, r.truncated) is True
    with pytest.raises(EnvError):
        env.step(KEEP)


def test_reset_starts_a_fresh_episode_and_closes_the_previous_simulation(make_env):
    env = make_env(horizon=100)
    first = env.reset(seed=9)
    for _ in range(6):
        env.step(KEEP)
    old_conn = env.conn
    again = env.reset(seed=9)
    assert env.sim_time == 0.0 and env.conn is not old_conn
    for j in JUNCTIONS:
        np.testing.assert_array_equal(first[j], again[j])
    with pytest.raises(Exception):
        old_conn.simulation.getTime()                    # previous SUMO process was shut down


# ------------------------------------------------------------------ determinism and route-file hygiene
def _trace(env, seed, steps=24):
    rng = np.random.default_rng(123)                       # identical action sequence for both runs
    obs = env.reset(seed=seed)
    trace = [np.concatenate([obs[j] for j in JUNCTIONS])]
    rewards = []
    for _ in range(steps):
        r = env.step(legal_random(env, rng))
        trace.append(np.concatenate([r.obs[j] for j in JUNCTIONS])); rewards.append([r.rewards[j] for j in JUNCTIONS])
    return np.array(trace), np.array(rewards)


def test_same_seed_gives_identical_episodes_and_different_seed_differs(make_env):
    a, ra = _trace(make_env(horizon=300), seed=21)
    b, rb = _trace(make_env(horizon=300), seed=21)
    c, _ = _trace(make_env(horizon=300), seed=22)
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(ra, rb)
    assert not np.array_equal(a, c)


def test_tracked_route_file_is_never_modified_and_a_per_episode_route_file_is_used(make_env):
    before = sha(TRACKED_ROUTES)
    env = make_env(horizon=60)
    env.reset(seed=31)
    used = env.conn.simulation.getOption("route-files")
    assert used == str(env.route_file) and Path(used).name == "episode_31.rou.xml" and Path(used) != TRACKED_ROUTES
    tmp_parent = env.route_file.parent
    for _ in range(4):
        env.step(KEEP)
    env.close()
    assert not tmp_parent.exists(), "temporary episode directory must be removed on close"
    assert sha(TRACKED_ROUTES) == before


# ------------------------------------------------------------------ failing clearly
def test_invalid_usage_raises_clear_errors(make_env):
    env = make_env(horizon=60)
    with pytest.raises(EnvError, match="reset"):
        env.step(KEEP)
    env.reset(seed=1)
    with pytest.raises(EnvError, match="exactly"):
        env.step({"junctionA": 0})
    with pytest.raises(EnvError, match="invalid action"):
        env.step({**KEEP, "junctionB": 9})
    with pytest.raises(EnvError, match="invalid action"):
        env.step({**KEEP, "junctionB": "switch"})


def test_unknown_junction_fails_at_reset():
    env = TrafficSignalEnv(EnvConfig(horizon_s=60, junction_ids=("junctionZ",)))
    try:
        with pytest.raises(EnvError):
            env.reset(seed=1)
    finally:
        env.close()


def test_lost_sumo_connection_raises_instead_of_returning_made_up_numbers(make_env):
    env = make_env(horizon=60)
    env.reset(seed=1)
    env.step(KEEP)
    env.conn.close()                                      # simulate SUMO dying mid-episode
    with pytest.raises(EnvError):
        env.step(KEEP)
