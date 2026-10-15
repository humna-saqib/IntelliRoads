"""Stage-2 live-SUMO tests: action legality, min/max green, yellow protection, remaining-time arithmetic.

Expected values come from the signal programme (G30 y5 G30 y5) and from SUMO's own schedule
(``getNextSwitch``), never from the environment's bookkeeping.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("traci")
sumolib = pytest.importorskip("sumolib")

from app.environment.observation import EnvError
from app.environment.signal_safety import EXTEND, KEEP, REDUCE, SWITCH, IllegalActionError, SignalSafetyConfig
from app.environment.traffic_env import EnvConfig, TrafficSignalEnv

JUNCTIONS = ("junctionA", "junctionB", "junctionC", "junctionD")
A = "junctionA"
NOMINAL = {0: 30.0, 1: 5.0, 2: 30.0, 3: 5.0}
GREENS = (0, 2)
SAFETY = SignalSafetyConfig()

try:
    sumolib.checkBinary("sumo")
except Exception:  # pragma: no cover
    pytest.skip("SUMO binary not available", allow_module_level=True)


@pytest.fixture
def make_env():
    envs = []

    def _make(horizon=300, interval=5, **kw):
        env = TrafficSignalEnv(EnvConfig(horizon_s=horizon, decision_interval_s=interval, **kw))
        envs.append(env)
        return env

    yield _make
    for e in envs:
        e.close()


def keep_all():
    return {j: KEEP for j in JUNCTIONS}


def act_a(action):
    a = keep_all(); a[A] = action
    return a


def log_of(env, junction=A):
    return [(e["phase"], e["duration_s"]) for e in env.signal_log if e["junction"] == junction]


def legal_random(env, rng):
    return {j: int(rng.choice(np.flatnonzero(m))) for j, m in env.action_masks().items()}


def run_until_phases_logged(env, n, policy, max_steps=200):
    """Step until junction A has completed ``n`` phases."""
    for _ in range(max_steps):
        if len(log_of(env)) >= n:
            return
        env.step(policy(env))
    raise AssertionError("phases did not complete in time")


# ------------------------------------------------------------------ masks and rejection of illegal actions
def test_fresh_episode_masks_forbid_only_an_immediate_switch(make_env):
    env = make_env()
    env.reset(seed=1)
    for j, m in env.action_masks().items():
        assert m.tolist() == [True, False, True, True], j


def test_switch_before_min_green_is_rejected_without_side_effects(make_env):
    env = make_env()
    env.reset(seed=1)
    env.step(keep_all())                                            # t = 5 -> elapsed 5 < min_green 10
    with pytest.raises(IllegalActionError, match="SWITCH is illegal"):
        env.step(act_a(SWITCH))
    assert env.sim_time == 5.0 and env.conn.simulation.getTime() == 5.0
    assert env.conn.trafficlight.getPhase(A) == 0 and env.conn.trafficlight.getNextSwitch(A) == 30.0
    env.step(keep_all())                                            # the environment is still usable
    assert env.sim_time == 10.0


def test_one_illegal_action_prevents_all_other_junction_actions_from_being_applied(make_env):
    env = make_env()
    env.reset(seed=1)
    env.step(keep_all())
    acts = {"junctionB": EXTEND, A: SWITCH, "junctionC": KEEP, "junctionD": KEEP}   # B (applied first) legal, A illegal
    with pytest.raises(IllegalActionError):
        env.step(acts)
    assert env.conn.trafficlight.getNextSwitch("junctionB") == 30.0, "validation must happen before anything is applied"


def test_keep_policy_coerces_illegal_actions_and_reports_them(make_env):
    env = make_env(on_illegal_action="keep")
    ref = make_env()
    env.reset(seed=3); ref.reset(seed=3)
    env.step(keep_all()); ref.step(keep_all())
    r = env.step(act_a(SWITCH))                                     # illegal at t = 5
    rk = ref.step(keep_all())
    assert r.info["coerced_actions"] == {A: (SWITCH, KEEP)} and r.info["applied_actions"][A] == KEEP
    assert r.rewards == rk.rewards, "a coerced action must behave exactly like KEEP"
    np.testing.assert_array_equal(r.obs[A], rk.obs[A])
    assert env.conn.trafficlight.getPhase(A) == 0


def test_step_info_carries_the_masks_for_the_next_decision(make_env):
    env = make_env(horizon=20)
    env.reset(seed=2)
    r = env.step(keep_all())
    for j in JUNCTIONS:
        np.testing.assert_array_equal(r.info["action_masks"][j], env.action_masks()[j])
    for _ in range(3):
        r = env.step(keep_all())
    assert r.truncated, "episode must have ended by truncation"
    # a time-limit truncation must still bootstrap, so the masks of the final state are provided
    assert all(m[KEEP] for m in r.info["action_masks"].values()) and set(r.info["action_masks"]) == set(JUNCTIONS)


# ------------------------------------------------------------------ minimum green and the safe yellow
def test_switch_at_exactly_min_green_gives_a_full_yellow_before_the_next_green(make_env):
    env = make_env(interval=5)
    env.reset(seed=4)
    env.step(keep_all()); env.step(keep_all())                       # t = 10: elapsed == min_green
    assert env.action_masks()[A][SWITCH]
    env.step(act_a(SWITCH))
    assert env.conn.trafficlight.getPhase(A) == 1 and env.conn.trafficlight.getNextSwitch(A) == 15.0
    run_until_phases_logged(env, 2, lambda e: keep_all())
    assert log_of(env)[:2] == [(0, 10.0), (1, 5.0)]
    assert env.conn.trafficlight.getPhase(A) == 2


def test_yellow_phase_cannot_be_switched_extended_or_reduced(make_env):
    env = make_env(horizon=110, interval=1)
    env.reset(seed=5)
    tl = env.conn.trafficlight
    tested = 0
    for _ in range(105):
        env.step(keep_all())
        if tl.getPhase(A) in (1, 3):
            assert env.action_masks()[A].tolist() == [True, False, False, False]
            before = tl.getNextSwitch(A)
            for bad in (SWITCH, EXTEND, REDUCE):
                with pytest.raises(IllegalActionError):
                    env.step(act_a(bad))
            assert tl.getNextSwitch(A) == before and tl.getPhase(A) in (1, 3)
            tested += 1
    assert tested >= 8, "both yellow phases must have been exercised"
    assert {d for p, d in log_of(env) if p in (1, 3)} == {5.0}


def test_natural_keep_cycle_is_exactly_30_5_30_5(make_env):
    env = make_env(horizon=120, interval=5)
    env.reset(seed=6)
    for _ in range(24):
        env.step(keep_all())
    for j in JUNCTIONS:
        assert log_of(env, j)[:4] == [(0, 30.0), (1, 5.0), (2, 30.0), (3, 5.0)], j


# ------------------------------------------------------------------ EXTEND / REDUCE arithmetic
@pytest.mark.parametrize("t_decision", [5, 10, 20, 25])
def test_extend_adds_five_seconds_to_the_remaining_green_whenever_it_is_applied(make_env, t_decision):
    """Legacy code set remaining = nominal + 5 = 35 s *from the decision time*; the green now ends at 30 + 5 = 35 s."""
    env = make_env(interval=5)
    env.reset(seed=7)
    for _ in range(t_decision // 5):
        env.step(keep_all())
    env.step(act_a(EXTEND))
    assert env.conn.trafficlight.getNextSwitch(A) == 35.0
    run_until_phases_logged(env, 2, lambda e: keep_all())
    assert log_of(env)[:2] == [(0, 35.0), (1, 5.0)]


@pytest.mark.parametrize("t_decision,expected_end", [(0, 25.0), (5, 25.0), (10, 25.0), (15, 25.0)])
def test_reduce_removes_five_seconds_from_the_remaining_green(make_env, t_decision, expected_end):
    env = make_env(interval=5)
    env.reset(seed=8)
    for _ in range(t_decision // 5):
        env.step(keep_all())
    env.step(act_a(REDUCE))
    assert env.conn.trafficlight.getNextSwitch(A) == expected_end
    run_until_phases_logged(env, 2, lambda e: keep_all())
    assert log_of(env)[:2] == [(0, expected_end), (1, 5.0)]


@pytest.mark.parametrize("interval", [1, 5])
def test_repeated_extension_stops_exactly_at_max_green(make_env, interval):
    env = make_env(horizon=150, interval=interval)
    env.reset(seed=9)
    masked_seen = False

    def policy(e):
        nonlocal masked_seen
        m = e.action_masks()[A]
        masked_seen |= not m[EXTEND]
        return act_a(EXTEND if m[EXTEND] else KEEP)

    run_until_phases_logged(env, 2, policy)
    assert log_of(env)[:2] == [(0, 60.0), (1, 5.0)], "endless extension (legacy defect) is impossible"
    assert masked_seen, "EXTEND must be masked once max_green is reached"
    assert all(d <= SAFETY.max_green_s for p, d in log_of(env) if p in GREENS)


@pytest.mark.parametrize("interval,expected_green", [(1, 10.0), (5, 15.0)])
def test_repeated_reduction_never_goes_below_min_green(make_env, interval, expected_green):
    env = make_env(horizon=100, interval=interval)
    env.reset(seed=10)
    masked_seen = False

    def policy(e):
        nonlocal masked_seen
        m = e.action_masks()[A]
        masked_seen |= not m[REDUCE]
        return act_a(REDUCE if m[REDUCE] else KEEP)

    run_until_phases_logged(env, 2, policy)
    assert log_of(env)[:2] == [(0, expected_green), (1, 5.0)]
    assert masked_seen and expected_green >= SAFETY.min_green_s


def test_alternating_extend_and_reduce_does_not_drift(make_env):
    env = make_env(interval=5)
    env.reset(seed=11)
    seq = [KEEP, KEEP, EXTEND, REDUCE]                                # t = 0, 5, 10, 15
    run_until_phases_logged(env, 2, lambda e: act_a(seq.pop(0) if seq else KEEP))
    assert log_of(env)[:2] == [(0, 30.0), (1, 5.0)]


# ------------------------------------------------------------------ safety over long runs
def _check_log(env):
    for j in JUNCTIONS:
        log = log_of(env, j)
        assert len(log) >= 4, j
        for (p0, d0), (p1, _) in zip(log, log[1:]):
            assert p1 == (p0 + 1) % 4, f"{j}: invalid transition {p0}->{p1}"
        for p, d in log:
            if p in GREENS:
                assert SAFETY.min_green_s <= d <= SAFETY.max_green_s, (j, p, d)
            else:
                assert d == SAFETY.yellow_s, (j, p, d)


@pytest.mark.parametrize("seed,interval", [(21, 5), (22, 5), (23, 2), (24, 1)])
def test_random_legal_actions_for_a_full_episode_never_break_a_safety_rule(make_env, seed, interval):
    horizon = 1800 if interval == 5 else 600
    env = make_env(horizon=horizon, interval=interval)                 # strict_safety=True: any violation raises
    env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    non_keep = 0
    while True:
        acts = legal_random(env, rng)
        non_keep += sum(a != KEEP for a in acts.values())
        r = env.step(acts)
        assert r.info["coerced_actions"] == {} and r.info["safety_violations"] == 0
        if r.truncated or r.terminated:
            break
    assert r.truncated and env.sim_time == horizon and non_keep > 50
    _check_log(env)


def test_environment_log_matches_an_independent_reading_of_the_signal_schedule(make_env):
    """Re-derive every phase duration from per-second TraCI polls: start(new) = getNextSwitch - programmed length."""
    env = make_env(horizon=500, interval=1)
    env.reset(seed=31)
    tl = env.conn.trafficlight
    rng = np.random.default_rng(31)
    cur = {j: tl.getPhase(j) for j in JUNCTIONS}
    start = {j: 0.0 for j in JUNCTIONS}
    mine = {j: [] for j in JUNCTIONS}
    while True:
        r = env.step(legal_random(env, rng))
        for j in JUNCTIONS:
            p = tl.getPhase(j)
            if p != cur[j]:
                new_start = tl.getNextSwitch(j) - NOMINAL[p]            # a phase that has just begun has its full programmed length left
                mine[j].append((cur[j], new_start - start[j]))
                cur[j], start[j] = p, new_start
        if r.truncated or r.terminated:
            break
    for j in JUNCTIONS:
        assert mine[j] == log_of(env, j), j
        assert len(mine[j]) > 20


# ------------------------------------------------------------------ the safety monitor itself
def test_external_tampering_with_the_schedule_is_detected_not_ignored(make_env):
    env = make_env(interval=5)
    env.reset(seed=41)
    env.step(keep_all())
    env.conn.trafficlight.setPhase(A, 1)                              # someone cuts the green at 5 s behind the environment's back
    with pytest.raises(EnvError, match="unsafe signal transition.*min_green"):
        env.step(keep_all())


def test_unsafe_transition_is_flagged_strictly_or_counted(make_env):
    strict = make_env(interval=1)
    strict.reset(seed=42)
    strict.conn.trafficlight.setPhaseDuration(A, 3)                   # green forced to end after 3 s < min_green
    with pytest.raises(EnvError, match="min_green"):
        for _ in range(10):
            strict.step(keep_all())
    lenient = make_env(interval=1, strict_safety=False)
    lenient.reset(seed=42)
    lenient.conn.trafficlight.setPhaseDuration(A, 3)
    for _ in range(10):
        r = lenient.step(keep_all())
    assert r.info["safety_violations"] >= 1
