"""Stage-5 SUMO integration / regression tests for fyp-obs-v2.

Only already-consumed seeds are used: smoke seed 5,000,001, and the diagnostic validation seeds 3,000,301 (min-green sweep)
and 3,000,311 (decision logging), whose stored outputs serve as regression references.  Nothing is written to project directories.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from tests.fyp_evidence import missing_evidence

pytest.importorskip("traci")
sumolib = pytest.importorskip("sumolib")

from app.environment.observation import FEATURE_NAMES_V2, OBS_V1, OBS_V2, presence_capacity, served_group
from app.environment.signal_safety import KEEP
from app.environment.traffic_env import EnvConfig, TrafficSignalEnv
from app.evaluation import runner
from app.evaluation.controllers import ActuatedStyleController, DQNController
from app.evaluation.protocol import EvalProtocol, load_validation_selected_checkpoint
from app.training.runs import BACKEND, CheckpointSchemaError

try:
    sumolib.checkBinary("sumo")
except Exception:  # pragma: no cover
    pytest.skip("SUMO binary not available", allow_module_level=True)

RUN = BACKEND / "training_runs" / "fyp_s0"
SWEEP = BACKEND / "diagnostic_runs" / "mingreen_ep400_r2" / "episodes.csv"
DECLOG = BACKEND / "diagnostic_runs" / "decision_logging_ep400"
PROTO = EvalProtocol(n_seeds=1, mode="validation")             # the approved 300 s + 1800 s + <=600 s measurement


def _lockstep(cfg_a, cfg_b, seed=5_000_001, horizon=300):
    a, b = TrafficSignalEnv(cfg_a), TrafficSignalEnv(cfg_b)
    out = []
    try:
        oa, ob = a.reset(seed), b.reset(seed)
        while True:
            out.append((oa, ob, a.action_masks(), b.action_masks()))
            keep = {j: KEEP for j in a.cfg.junction_ids}
            ra, rb = a.step(keep), b.step(keep)
            out[-1] = out[-1] + (ra.rewards, rb.rewards)
            oa, ob = ra.obs, rb.obs
            if ra.truncated or ra.terminated:
                assert rb.truncated == ra.truncated and rb.terminated == ra.terminated
                break
    finally:
        a.close(); b.close()
    return out


def test_v2_environment_keeps_v1_features_rewards_and_masks_identical():
    steps = _lockstep(EnvConfig(horizon_s=300), EnvConfig(horizon_s=300, obs_version=OBS_V2))
    assert len(steps) == 60
    for oa, ob, ma, mb, ra, rb in steps:
        for j in oa:
            assert oa[j].shape == (11,) and ob[j].shape == (15,)
            assert np.array_equal(ob[j][:11], oa[j])                         # v1 part byte-identical
            assert np.array_equal(ma[j], mb[j])                             # legal-action masks unchanged
            assert ra[j] == rb[j]                                           # reward unchanged
            assert 0.0 <= ob[j][11:].min() and ob[j][11:].max() <= 1.0
    assert any(ob[j][11:].sum() > 0 for oa, ob, *_ in steps for j in ob)  # the presence features are not trivially zero


def test_v2_observations_are_deterministic():
    steps = _lockstep(EnvConfig(horizon_s=300, obs_version=OBS_V2), EnvConfig(horizon_s=300, obs_version=OBS_V2))
    assert all(np.array_equal(oa[j], ob[j]) for oa, ob, *_ in steps for j in oa)


def test_served_group_maps_each_green_phase_to_the_lanes_sumo_gives_green():
    root = ET.parse(BACKEND / "sumo" / "network" / "intelliroads.net.xml").getroot()
    states = {t.get("id"): [p.get("state") for p in t.findall("phase")] for t in root.findall("tlLogic")}
    lane_id = {(e.get("id"), ln.get("index")): ln.get("id") for e in root.findall("edge") for ln in e.findall("lane")}   # lanes have custom ids
    links = {}
    for c in root.findall("connection"):
        if c.get("tl"):
            links.setdefault(c.get("tl"), {})[int(c.get("linkIndex"))] = lane_id[(c.get("from"), c.get("fromLane"))]
    env = TrafficSignalEnv(EnvConfig(horizon_s=60, obs_version=OBS_V2))
    try:
        env.reset(5_000_001)
        for j, topo in env.topology.items():
            for phase in range(topo.n_phases):
                k = served_group(topo, phase)
                green = phase if phase in topo.green_phases else (phase - 1) % topo.n_phases
                want = {links[j][i] for i, ch in enumerate(states[j][green]) if ch in "Gg"}
                assert {topo.lanes[i] for i in topo.groups[k]} == want, (j, phase)
    finally:
        env.close()


def test_a_v1_checkpoint_cannot_drive_a_v2_environment():
    if not (RUN / "best.pt").exists():
        missing_evidence("training_runs/fyp_s0")
    agent, info = load_validation_selected_checkpoint(RUN)
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, demand_end_s=PROTO.demand_end_s, obs_version=OBS_V2))
    try:
        with pytest.raises(CheckpointSchemaError):
            runner.run_episode(env, DQNController(agent, info), 5_000_001, PROTO)
    finally:
        env.close()


def test_regression_episode_400_reproduces_the_stored_minimum_green_sweep_result_exactly():
    """v1 path unchanged end to end: same checkpoint, same seed, same default settings -> identical measurements."""
    if not (RUN / "best.pt").exists() or not SWEEP.exists():
        missing_evidence("training_runs/fyp_s0 and diagnostic_runs/mingreen_ep400_r2")
    ref = next(r for r in csv.DictReader(open(SWEEP)) if r["setting"] == "A" and r["seed"] == "3000301")
    agent, info = load_validation_selected_checkpoint(RUN)
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, decision_interval_s=5, demand_end_s=PROTO.demand_end_s))
    assert env.cfg.obs_version == OBS_V1 and env.state_size == 11
    try:
        row = runner.run_episode(env, DQNController(agent, info), 3_000_301, PROTO)["row"]
    finally:
        env.close()
    for k in ("wait_per_vehicle_all_s", "travel_time_completed_s", "mean_queue_per_lane", "throughput_veh_per_h", "trips_scheduled",
              "trips_completed", "drain_s_used", "decisions", "actions_keep", "actions_switch", "actions_extend", "actions_reduce"):
        assert float(row[k]) == float(ref[k]), k


def test_v2_presence_features_equal_the_independently_logged_counts_and_do_not_perturb_the_simulation():
    """The actuated controller ignores the observation, so its trajectory on seed 3,000,311 must equal the decision-logging run;
    the v2 presence features must then equal the logged 40 m counts divided by the group capacity, at every decision."""
    dec, eps = DECLOG / "decisions_actuated.csv", DECLOG / "episodes.csv"
    if not dec.exists() or not eps.exists():
        missing_evidence("diagnostic_runs/decision_logging_ep400")
    logged = [r for r in csv.DictReader(open(dec)) if r["seed"] == "3000311"]
    ref = next(r for r in csv.DictReader(open(eps)) if r["controller"] == "actuated_style" and r["seed"] == "3000311")

    class Recording(ActuatedStyleController):
        def start_episode(self, env):
            super().start_episode(env); self.seen = []

        def act(self, env, obs, masks):
            acts = super().act(env, obs, masks)
            for j in env.cfg.junction_ids:
                self.seen.append((env.sim_time, j, env.phase_view(j).phase, obs[j].copy()))
            return acts

    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, decision_interval_s=5, demand_end_s=PROTO.demand_end_s, obs_version=OBS_V2))
    ctrl = Recording()
    try:
        row = runner.run_episode(env, ctrl, 3_000_311, PROTO)["row"]        # also enforces: no illegal actions, no safety violations
        topo = env.topology
    finally:
        env.close()
    assert float(row["wait_per_vehicle_all_s"]) == float(ref["wait_per_vehicle_all_s"])    # trajectory unchanged by the v2 reads
    assert len(ctrl.seen) == len(logged)
    clipped = 0
    for (t, j, phase, vec), r in zip(ctrl.seen, logged):
        assert (float(r["t"]), r["junction"], int(r["phase"])) == (t, j, phase)
        k = served_group(topo[j], phase)
        caps = (presence_capacity(topo[j], k, 40.0),) * 2 + (presence_capacity(topo[j], 1 - k, 40.0),) * 2
        counts = [float(r[c]) for c in ("cur_moving_40m", "cur_stopped_40m", "opp_moving_40m", "opp_stopped_40m")]
        want = [min(n / c, 1.0) for n, c in zip(counts, caps)]               # specification: count / capacity, clipped to [0, 1]
        assert list(vec[11:]) == pytest.approx(want, abs=1e-12), (t, j)
        assert list(vec.shape) == [len(FEATURE_NAMES_V2)]
        clipped += sum(1 for n, c in zip(counts, caps) if n > c)
    # clipping happens only where the logged count really exceeds the 7.5 m-per-vehicle capacity (short vehicles, e.g. motorcycles)
    assert clipped < 0.01 * 4 * len(logged)
