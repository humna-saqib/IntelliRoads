"""Stage-1 unit tests for the corrected observation layer – run without SUMO (fake TraCI connection)."""

from __future__ import annotations

import ast
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from app.agent.dqn_agent import DQNAgent, normalize_state
from app.environment import observation as obs
from app.environment.observation import (
    ELAPSED_MAX_S,
    N_PHASES,
    STATE_SIZE,
    VEHICLE_SPACE_M,
    WAIT_MAX_S,
    EnvError,
    discover_topology,
    encode_state,
    read_measurement,
)
from app.environment.traffic_env import EnvConfig, legacy_reward, replay_done_flag

LANES = ["west_in", "ab_west", "north_in", "ad_north"]
LENGTHS = {"west_in": 300.0, "ab_west": 400.0, "north_in": 300.0, "ad_north": 400.0}


def make_conn(values=None, states=("GGrr", "yyrr", "rrGG", "rryy"), link_lanes=LANES, program="0"):
    """Fake TraCI connection for one junction 'J'. ``values[lane] = (count, halting, waiting, occupancy)``."""
    values = values or {l: (0, 0, 0.0, 0.0) for l in LANES}
    logic = SimpleNamespace(programID=program, phases=[SimpleNamespace(state=s) for s in states])
    tl = SimpleNamespace(
        getControlledLinks=lambda j: [[(l, "out", "via")] for l in link_lanes],
        getAllProgramLogics=lambda j: [logic],
        getProgram=lambda j: program,
    )
    lane = SimpleNamespace(
        getLength=lambda l: LENGTHS[l],
        getLastStepVehicleNumber=lambda l: values[l][0],
        getLastStepHaltingNumber=lambda l: values[l][1],
        getWaitingTime=lambda l: values[l][2],
        getLastStepOccupancy=lambda l: values[l][3],
    )
    return SimpleNamespace(trafficlight=tl, lane=lane)


# ------------------------------------------------------------------ topology
def test_topology_covers_all_four_lanes_and_partitions_into_green_groups():
    topo = discover_topology(make_conn(), "J")
    assert topo.lanes == tuple(LANES)
    assert topo.groups == ((0, 1), (2, 3)) and topo.green_phases == (0, 2) and topo.n_phases == N_PHASES
    assert topo.capacities == tuple(LENGTHS[l] / VEHICLE_SPACE_M for l in LANES)


@pytest.mark.parametrize("bad", [
    dict(states=("GGrr", "yyrr", "rrGG")),                    # 3 phases
    dict(states=("GGGG", "yyyy", "GGGG", "yyyy")),            # groups overlap
    dict(states=("Grrr", "yrrr", "rGrr", "ryrr")),            # groups do not cover all lanes
    dict(states=("rrrr", "yyyy", "rrrr", "yyyy")),            # no green phase
])
def test_topology_rejects_unsupported_programs(bad):
    with pytest.raises(EnvError):
        discover_topology(make_conn(**bad), "J")


def test_topology_reports_traci_failure_as_envError():
    conn = make_conn()
    conn.trafficlight.getControlledLinks = lambda j: (_ for _ in ()).throw(RuntimeError("unknown tls"))
    with pytest.raises(EnvError, match="traffic-light definition"):
        discover_topology(conn, "J")


# ------------------------------------------------------------------ measurement
def test_measurement_aggregates_all_four_lanes():
    vals = {"west_in": (4, 2, 40.0, 0.10), "ab_west": (6, 1, 60.0, 0.20), "north_in": (0, 0, 0.0, 0.0), "ad_north": (10, 5, 100.0, 0.30)}
    topo = discover_topology(make_conn(vals), "J")
    m = read_measurement(make_conn(vals), topo)
    assert m.count == 20 and m.halting == 8
    assert m.mean_wait_s == pytest.approx(200.0 / 20)
    assert m.occupancy == pytest.approx((0.10 * 300 + 0.20 * 400 + 0.0 * 300 + 0.30 * 400) / 1400)
    assert m.group_halting == (3, 5)                 # lanes (west_in, ab_west) | (north_in, ad_north)


def test_empty_junction_has_zero_mean_wait_by_definition():
    m = read_measurement(make_conn(), discover_topology(make_conn(), "J"))
    assert (m.count, m.halting, m.mean_wait_s, m.occupancy) == (0, 0, 0.0, 0.0)


@pytest.mark.parametrize("idx,bad", [
    (0, float("nan")), (0, -1), (1, float("inf")), (1, -3), (2, float("nan")), (2, -0.5), (3, float("nan")), (3, -0.01),
    (3, 35.0),                                       # occupancy in percent instead of fraction
])
def test_invalid_traci_values_raise_instead_of_being_replaced(idx, bad):
    vals = {l: (3, 1, 10.0, 0.1) for l in LANES}
    row = list(vals["ab_west"]); row[idx] = bad; vals["ab_west"] = tuple(row)
    conn = make_conn(vals)
    with pytest.raises(EnvError, match="ab_west"):
        read_measurement(conn, discover_topology(conn, "J"))


def test_halting_larger_than_count_is_rejected():
    vals = {l: (3, 1, 10.0, 0.1) for l in LANES}; vals["west_in"] = (2, 3, 0.0, 0.1)
    conn = make_conn(vals)
    with pytest.raises(EnvError, match="exceeds"):
        read_measurement(conn, discover_topology(conn, "J"))


@pytest.mark.parametrize("getter", ["getLastStepVehicleNumber", "getLastStepHaltingNumber", "getWaitingTime", "getLastStepOccupancy"])
def test_failing_traci_call_raises_no_fallback_constant(getter):
    conn = make_conn()
    topo = discover_topology(conn, "J")

    def boom(lane):
        raise RuntimeError("TraCI error")

    setattr(conn.lane, getter, boom)
    with pytest.raises(EnvError, match="TraCI call failed"):
        read_measurement(conn, topo)


def test_new_modules_never_use_the_nonexistent_lane_halting_api():
    base = Path(obs.__file__).parent
    for name in ("observation.py", "traffic_env.py"):
        assert ".getHaltingNumber(" not in (base / name).read_text(), f"{name} calls the non-existent traci.lane.getHaltingNumber"


def test_every_exception_handler_re_raises_so_nothing_is_silently_replaced():
    """AST check: an ``except`` block must raise; the only allowed exception is resource clean-up in ``close()``."""
    base = Path(obs.__file__).parent
    for name in ("observation.py", "traffic_env.py"):
        tree = ast.parse((base / name).read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.ExceptHandler) and fn.name != "close":
                    assert any(isinstance(n, ast.Raise) for n in ast.walk(node)), f"{name}:{node.lineno} swallows an exception in {fn.name}()"


# ------------------------------------------------------------------ encoding
def _encode(vals, phase=0, elapsed=0.0):
    conn = make_conn(vals); topo = discover_topology(conn, "J")
    return encode_state(topo, read_measurement(conn, topo), phase, elapsed)


def test_encoding_values_and_normalisation_bounds():
    vals = {"west_in": (4, 2, 40.0, 0.10), "ab_west": (6, 1, 60.0, 0.20), "north_in": (0, 0, 0.0, 0.0), "ad_north": (10, 5, 100.0, 0.30)}
    vec, clipped = _encode(vals, phase=2, elapsed=27.0)
    caps = [LENGTHS[l] / VEHICLE_SPACE_M for l in LANES]
    assert vec.shape == (STATE_SIZE,) and clipped == 0
    assert vec[0] == pytest.approx(20 / sum(caps)) and vec[1] == pytest.approx(8 / sum(caps))
    assert vec[2] == pytest.approx((200 / 20) / WAIT_MAX_S)
    assert vec[3] == pytest.approx((0.10 * 300 + 0.20 * 400 + 0.30 * 400) / 1400)
    assert vec[4] == pytest.approx(3 / (caps[0] + caps[1])) and vec[5] == pytest.approx(5 / (caps[2] + caps[3]))
    assert list(vec[6:10]) == [0, 0, 1, 0]
    assert vec[10] == pytest.approx(27.0 / ELAPSED_MAX_S)
    assert np.all((vec >= 0) & (vec <= 1))


def test_signal_phase_is_one_hot_and_visible_to_the_network():
    for p in range(N_PHASES):
        vec, _ = _encode(None, phase=p)
        assert vec[6:10].sum() == 1 and vec[6 + p] == 1
    # legacy encoding (phase index / 90) would have been <= 0.033 for every phase
    assert normalize_state([0, 0, 0, 0, 3])[4] < 0.04


def test_full_junction_saturates_at_one_and_counts_clipped_features():
    vals = {l: (int(LENGTHS[l] / VEHICLE_SPACE_M) + 5, int(LENGTHS[l] / VEHICLE_SPACE_M) + 5, 400.0 * 50, 1.0) for l in LANES}
    vec, clipped = _encode(vals, elapsed=500.0)
    assert vec.max() <= 1.0 and clipped >= 3


@pytest.mark.parametrize("phase,elapsed", [(4, 0.0), (-1, 0.0), (1.5, 0.0), (0, -1.0), (0, float("nan")), (0, float("inf"))])
def test_invalid_phase_or_elapsed_raises(phase, elapsed):
    with pytest.raises(EnvError):
        _encode(None, phase=phase, elapsed=elapsed)


# ------------------------------------------------------------------ transitions / replay flag / config / reward
def test_truncation_does_not_cut_the_bootstrap_but_termination_does():
    assert replay_done_flag(terminated=False, truncated=True) is False
    assert replay_done_flag(terminated=True, truncated=False) is True
    assert replay_done_flag(terminated=False, truncated=False) is False


def test_config_validation():
    EnvConfig()
    for kwargs in (dict(horizon_s=0), dict(decision_interval_s=0), dict(horizon_s=100, decision_interval_s=30), dict(junction_ids=())):
        with pytest.raises(EnvError):
            EnvConfig(**kwargs)
    assert EnvConfig().horizon_s == 1800 and EnvConfig().decision_interval_s == 5


def test_reward_uses_legacy_formula_on_the_corrected_measurement():
    vals = {l: (2, 1, 20.0, 0.05) for l in LANES}
    conn = make_conn(vals); topo = discover_topology(conn, "J"); m = read_measurement(conn, topo)
    keep = legacy_reward(m, 4, 0, 0.4, 0.70, 15.0)
    switch = legacy_reward(m, 4, 1, 0.4, 0.70, 15.0)
    expected = -1.0 * 10.0 - 2.0 * 4 + 5.0 * 0.4 + 1.0
    assert keep == pytest.approx(expected) and switch == pytest.approx(expected - 1.5)
    jam = {l: (20, 20, 20.0 * 20, 0.9) for l in LANES}
    mj = read_measurement(make_conn(jam), topo)
    assert legacy_reward(mj, 4, 0, 0.0, 0.70, 15.0) == pytest.approx(-1.0 * 20 - 2.0 * 80 - 4.0)


# ------------------------------------------------------------------ agent integration (default behaviour unchanged)
def test_agent_default_still_uses_legacy_normalisation():
    agent = DQNAgent(state_size=5, action_size=4, device="cpu")
    assert agent.normalize_inputs is True
    state = [12.0, 3.0, 20.0, 40.0, 1.0]
    with torch.no_grad():
        expected = int(agent.policy_net(torch.tensor([normalize_state(state)], dtype=torch.float32)).argmax(1).item())
    assert agent.select_action(state, epsilon=0.0) == expected
    assert agent._prepare(state) == normalize_state(state)


def test_agent_with_prenormalised_inputs_does_not_truncate_the_state():
    agent = DQNAgent(state_size=STATE_SIZE, action_size=4, device="cpu", normalize_inputs=False, batch_size=8)
    state = list(np.linspace(0, 1, STATE_SIZE))
    assert agent._prepare(state) == pytest.approx(state) and len(agent._prepare(state)) == STATE_SIZE
    assert 0 <= agent.select_action(state, epsilon=0.0) < 4
    with pytest.raises(ValueError):
        agent.select_action(state[:5], epsilon=0.0)
    rng = np.random.default_rng(0)
    for _ in range(32):
        agent.store_transition(list(rng.random(STATE_SIZE)), int(rng.integers(4)), float(rng.normal()), list(rng.random(STATE_SIZE)), False)
    loss, q = agent.train_step(batch_size=8)
    assert math.isfinite(loss) and math.isfinite(q)
