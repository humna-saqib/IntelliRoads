"""Stage-5 unit tests (no SUMO): fyp-obs-v2 presence features, schema versioning, checkpoint compatibility, reward isolation."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from tests.fyp_evidence import missing_evidence
import torch

from app.environment import observation as O
from app.environment.observation import (DEFAULT_DETECTOR_RANGE_M, FEATURE_NAMES, FEATURE_NAMES_V2, OBS_SCHEMAS, OBS_V1, OBS_V2,
                                         EnvError, JunctionMeasurement, JunctionTopology, encode_state, encode_state_v2,
                                         presence_capacity, read_group_presence, read_presence, schema_feature_names,
                                         schema_state_size, served_group)
from app.environment.traffic_env import EnvConfig, legacy_reward
from app.evaluation.controllers import DQNController
from app.evaluation.protocol import ProtocolError, load_candidate_checkpoint, load_validation_selected_checkpoint
from app.training.double_dqn import MaskedDoubleDQN
from app.training.runs import (BACKEND, CHECKPOINT_FORMAT, CHECKPOINT_FORMAT_V2, CheckpointSchemaError, RunDirError,
                               assert_schema_matches, checkpoint_schema, load_checkpoint, save_checkpoint)
from app.training.trainer import TrainConfig

TOPO = JunctionTopology("J", ("a", "b", "c", "d"), (300.0, 400.0, 300.0, 400.0), ((0, 1), (2, 3)), (0, 2), 4)
V1_NAMES = ("count_frac", "halting_frac", "mean_wait_norm", "occupancy", "halting_frac_g0", "halting_frac_g1",
            "phase_0", "phase_1", "phase_2", "phase_3", "elapsed_norm")


class FakeConn:
    """vehicles: {vid: (lane, position_from_lane_start, speed)}"""

    def __init__(self, vehicles, fail_lane=None, bad=None):
        self.v, self.fail_lane, self.bad = vehicles, fail_lane, bad or {}
        outer = self

        class Lane:
            def getLastStepVehicleIDs(self, lane):
                if lane == outer.fail_lane:
                    raise RuntimeError("TraCI lost the lane")
                return [vid for vid, (ln, _, _) in outer.v.items() if ln == lane]

        class Veh:
            def getLanePosition(self, vid):
                return outer.bad.get((vid, "pos"), outer.v[vid][1])

            def getSpeed(self, vid):
                return outer.bad.get((vid, "speed"), outer.v[vid][2])

        self.lane, self.vehicle = Lane(), Veh()


def _meas(seed=0):
    rng = np.random.default_rng(seed)
    per = {l: {"count": 5.0, "halting": 2.0, "waiting_time": 10.0, "occupancy": 0.2} for l in TOPO.lanes}
    return JunctionMeasurement(float(rng.integers(0, 40)), float(rng.integers(0, 10)), float(rng.uniform(0, 60)), float(rng.uniform(0, 1)),
                               (float(rng.integers(0, 6)), float(rng.integers(0, 6))), per)


# ------------------------------------------------------------------ schema
def test_v1_schema_is_unchanged_and_v2_is_a_strict_superset():
    assert FEATURE_NAMES == V1_NAMES and O.STATE_SIZE == 11
    assert FEATURE_NAMES_V2[:11] == V1_NAMES and FEATURE_NAMES_V2[11:] == (
        "served_moving_near", "served_stopped_near", "opposing_moving_near", "opposing_stopped_near")
    assert schema_state_size(OBS_V1) == 11 and schema_state_size(OBS_V2) == 15 and set(OBS_SCHEMAS) == {OBS_V1, OBS_V2}
    assert (OBS_V1, OBS_V2) == ("fyp-obs-v1", "fyp-obs-v2") and DEFAULT_DETECTOR_RANGE_M == 40.0
    with pytest.raises(EnvError):
        schema_feature_names("fyp-obs-v3")


def test_env_and_train_config_default_to_v1_and_refuse_unknown_schemas_or_bad_ranges():
    assert EnvConfig().obs_version == OBS_V1 and TrainConfig(run_id="x").obs_version == OBS_V1
    for bad in ({"obs_version": "v2"}, {"detector_range_m": 0}, {"detector_range_m": -5}, {"detector_range_m": float("nan")}):
        with pytest.raises(EnvError):
            EnvConfig(**bad)
        with pytest.raises(ValueError):
            TrainConfig(run_id="x", **bad)
    EnvConfig(obs_version=OBS_V2, detector_range_m=25.0)


# ------------------------------------------------------------------ presence counts
def test_moving_and_stopped_counts_per_approach():
    conn = FakeConn({"m1": ("a", 280.0, 5.0), "s1": ("a", 295.0, 0.0), "s2": ("b", 390.0, 0.05), "m2": ("b", 370.0, 0.1),
                     "o1": ("c", 290.0, 0.0), "o2": ("d", 365.0, 8.0), "far": ("a", 100.0, 0.0)})
    assert read_group_presence(conn, TOPO, 0, 40.0) == (2, 2)                # far vehicle (200 m away) excluded
    assert read_group_presence(conn, TOPO, 1, 40.0) == (1, 1)
    assert read_presence(conn, TOPO, 0, 40.0) == (2, 2, 1, 1)                 # phase 0 serves group 0
    assert read_presence(conn, TOPO, 2, 40.0) == (1, 1, 2, 2)                 # phase 2 serves group 1 -> roles swap


def test_detector_boundary_and_lane_membership():
    conn = FakeConn({"at": ("a", 260.0, 3.0), "beyond": ("a", 259.99, 3.0), "atb": ("b", 360.0, 0.0), "out": ("zzz", 299.0, 0.0)})
    assert read_group_presence(conn, TOPO, 0, 40.0) == (1, 1)                 # exactly 40 m counts, 40.01 m does not; foreign lane ignored
    assert read_group_presence(conn, TOPO, 0, 40.02) == (2, 1)
    assert read_group_presence(conn, TOPO, 1, 40.0) == (0, 0)


def test_stopped_threshold_is_sumo_halting_speed():
    conn = FakeConn({"x": ("a", 299.0, 0.0999), "y": ("a", 298.0, 0.1)})
    assert read_group_presence(conn, TOPO, 0, 40.0) == (1, 1)


def test_empty_approaches_give_zero():
    assert read_presence(FakeConn({}), TOPO, 0, 40.0) == (0, 0, 0, 0)
    v, c = encode_state_v2(TOPO, _meas(), 0, 0.0, (0, 0, 0, 0), 40.0)
    assert list(v[11:]) == [0.0] * 4 and c == 0


@pytest.mark.parametrize("bad", [{"fail_lane": "b"}, {"bad": {("v", "pos"): float("nan")}}, {"bad": {("v", "speed"): -1.0}},
                                 {"bad": {("v", "speed"): "fast"}}])
def test_missing_or_invalid_traci_data_raises_instead_of_defaulting(bad):
    conn = FakeConn({"v": ("a", 290.0, 1.0), "w": ("b", 390.0, 0.0)}, **bad)
    with pytest.raises(EnvError):
        read_presence(conn, TOPO, 0, 40.0)


# ------------------------------------------------------------------ phase-relative mapping
def test_served_group_mapping_including_yellow():
    assert [served_group(TOPO, p) for p in range(4)] == [0, 0, 1, 1]          # yellow 1 follows green 0, yellow 3 follows green 2
    for bad in (-1, 4, 1.5, None):
        with pytest.raises(EnvError):
            served_group(TOPO, bad)
    odd = JunctionTopology("K", TOPO.lanes, TOPO.lengths_m, TOPO.groups, (0, 1), 4)
    with pytest.raises(EnvError):
        served_group(odd, 3)                                                  # phase 3 does not follow a green


# ------------------------------------------------------------------ encoding
def test_v2_prefix_is_byte_identical_to_v1():
    for seed in range(20):
        m = _meas(seed)
        for phase, el in ((0, 0.0), (1, 3.0), (2, 25.0), (3, 4.0)):
            v1, c1 = encode_state(TOPO, m, phase, el, 60.0)
            v2, c2 = encode_state_v2(TOPO, m, phase, el, (1, 2, 3, 4), 40.0, 60.0)
            assert v2.shape == (15,) and v1.shape == (11,) and np.array_equal(v2[:11], v1) and c2 >= c1


def test_normalisation_uses_the_physical_maximum_within_the_detector_and_clips():
    cap = presence_capacity(TOPO, 0, 40.0)
    assert cap == pytest.approx(2 * 40.0 / 7.5)
    v, c = encode_state_v2(TOPO, _meas(), 0, 0.0, (1, 0, 2, 0), 40.0)
    assert v[11] == pytest.approx(1 / cap) and v[13] == pytest.approx(2 / cap) and c == 0
    v, c = encode_state_v2(TOPO, _meas(), 0, 0.0, (99, 0, 0, 0), 40.0)
    assert v[11] == 1.0 and c == 1                                            # clipped and counted
    assert presence_capacity(TOPO, 0, 500.0) == pytest.approx(700.0 / 7.5)   # range longer than the lanes: lane length caps it
    for bad in ((1, 2, 3), (1, 2, 3, -1), (1, 2, 3, float("nan"))):
        with pytest.raises(EnvError):
            encode_state_v2(TOPO, _meas(), 0, 0.0, bad, 40.0)
    with pytest.raises(EnvError):
        encode_state_v2(TOPO, _meas(), 0, 0.0, (0, 0, 0, 0), 0.0)


def test_identical_state_gives_identical_observation():
    conn = FakeConn({"m": ("a", 280.0, 4.0), "s": ("c", 299.0, 0.0)})
    a = encode_state_v2(TOPO, _meas(3), 2, 10.0, read_presence(conn, TOPO, 2, 40.0), 40.0)[0]
    b = encode_state_v2(TOPO, _meas(3), 2, 10.0, read_presence(conn, TOPO, 2, 40.0), 40.0)[0]
    assert np.array_equal(a, b)


def test_reward_function_is_unchanged():
    m = JunctionMeasurement(20.0, 6.0, 12.5, 0.3, (4.0, 2.0), {})
    want = round(-1.0 * 12.5 - 2.0 * 6.0 - 0 + 5.0 * 0.6 - 1.5 * 1 + 1.0, 4)  # legacy weights 1, 2, 4, 5, 1.5, bonus 1
    assert legacy_reward(m, 4, 1, 0.6, 0.70, 15.0) == want
    assert legacy_reward(m, 4, 0, 0.6, 0.70, 15.0) == round(want + 1.5, 4)


# ------------------------------------------------------------------ checkpoint schema
def _ck(fmt, **kw):
    d = {"format": fmt, "state_size": 11, "feature_names": list(V1_NAMES)}
    d.update(kw)
    return d


def test_checkpoint_schema_accepts_only_consistent_metadata():
    assert checkpoint_schema(_ck(CHECKPOINT_FORMAT))["obs_version"] == OBS_V1
    assert checkpoint_schema(_ck(CHECKPOINT_FORMAT, feature_names=[]))["state_size"] == 11       # old v1 files without names
    v2 = _ck(CHECKPOINT_FORMAT_V2, obs_version=OBS_V2, state_size=15, feature_names=list(FEATURE_NAMES_V2), detector_range_m=40.0)
    assert checkpoint_schema(v2) == {"obs_version": OBS_V2, "feature_names": FEATURE_NAMES_V2, "state_size": 15, "detector_range_m": 40.0}
    bad = [_ck(CHECKPOINT_FORMAT, state_size=15), _ck(CHECKPOINT_FORMAT, feature_names=list(FEATURE_NAMES_V2)),
           _ck(CHECKPOINT_FORMAT, feature_names=list(V1_NAMES[::-1])),
           {**v2, "feature_names": list(V1_NAMES)}, {**v2, "state_size": 11}, {**v2, "detector_range_m": None},
           {**v2, "detector_range_m": -1.0}, {**v2, "obs_version": "fyp-obs-v9"}, {"format": None, "state_size": 5}, {}]
    for b in bad:
        with pytest.raises(CheckpointSchemaError):
            checkpoint_schema(b)


def test_schema_mismatch_between_checkpoint_and_environment_is_refused():
    v1 = checkpoint_schema(_ck(CHECKPOINT_FORMAT))
    v2 = {"obs_version": OBS_V2, "detector_range_m": 40.0}
    assert_schema_matches(v1, OBS_V1, 40.0)
    assert_schema_matches(v2, OBS_V2, 40.0)
    for s, ver, rng in ((v1, OBS_V2, 40.0), (v2, OBS_V1, 40.0), (v2, OBS_V2, 25.0)):
        with pytest.raises(CheckpointSchemaError):
            assert_schema_matches(s, ver, rng)


def _save(path, size, version=None, rng=None, names=None, episode=20):
    agent = MaskedDoubleDQN(size, 4, hidden=8, seed=0)
    save_checkpoint(path, agent, episode=episode, decisions=10, val_score=None, val_metric="mean_wait_s", train_config={"hidden": 8, "smoke": False},
                    feature_names=names if names is not None else (FEATURE_NAMES_V2 if size == 15 else FEATURE_NAMES),
                    obs_version=version, detector_range_m=rng)
    return agent


def test_v1_save_path_writes_exactly_the_old_payload(tmp_path):
    _save(tmp_path / "v1.pt", 11, OBS_V1, 40.0)
    _save(tmp_path / "old.pt", 11)
    a, b = (torch.load(str(tmp_path / n), weights_only=False) for n in ("v1.pt", "old.pt"))
    assert a["format"] == b["format"] == CHECKPOINT_FORMAT and set(a) == set(b)
    assert "obs_version" not in a and "detector_range_m" not in a


def test_v2_checkpoint_round_trip_and_cross_loading_refused(tmp_path):
    agent = _save(tmp_path / "v2.pt", 15, OBS_V2, 40.0)
    ck = torch.load(str(tmp_path / "v2.pt"), weights_only=False)
    assert ck["format"] == CHECKPOINT_FORMAT_V2 and ck["obs_version"] == OBS_V2 and ck["state_size"] == 15
    assert ck["feature_names"] == list(FEATURE_NAMES_V2) and ck["detector_range_m"] == 40.0
    same = MaskedDoubleDQN(15, 4, hidden=8, seed=9)
    load_checkpoint(tmp_path / "v2.pt", same)
    assert all(torch.equal(same.policy_net.state_dict()[k], agent.policy_net.state_dict()[k]) for k in agent.policy_net.state_dict())
    with pytest.raises(RunDirError):
        load_checkpoint(tmp_path / "v2.pt", MaskedDoubleDQN(11, 4, hidden=8))      # never reshaped into a v1 agent
    _save(tmp_path / "v1.pt", 11)
    with pytest.raises(RunDirError):
        load_checkpoint(tmp_path / "v1.pt", MaskedDoubleDQN(15, 4, hidden=8))
    with pytest.raises(CheckpointSchemaError):
        _save(tmp_path / "inconsistent.pt", 15, OBS_V2, 40.0, names=FEATURE_NAMES)   # refuses to write inconsistent metadata
    assert not (tmp_path / "inconsistent.pt").exists()


def test_evaluation_loaders_report_the_schema_and_never_mix(tmp_path):
    d = tmp_path / "run"; d.mkdir(); (d / "config.json").write_text("{}")
    _save(d / "ckpt_ep0020.pt", 15, OBS_V2, 40.0)
    agent, info = load_candidate_checkpoint(d, "ckpt_ep0020.pt")
    assert info["obs_version"] == OBS_V2 and info["detector_range_m"] == 40.0 and agent.state_size == 15
    _save(d / "ckpt_ep0040.pt", 11, episode=40)
    agent, info = load_candidate_checkpoint(d, "ckpt_ep0040.pt")
    assert info["obs_version"] == OBS_V1 and info["detector_range_m"] is None and agent.state_size == 11


def test_the_episode_400_checkpoint_still_loads_through_the_v1_path_unchanged():
    run = BACKEND / "training_runs" / "fyp_s0"
    if not (run / "best.pt").exists():
        missing_evidence("training_runs/fyp_s0")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {f: sha(run / f) for f in ("best.pt", "ckpt_ep0400.pt", "best.json")}
    agent, info = load_validation_selected_checkpoint(run)
    assert info["obs_version"] == OBS_V1 and info["selected_episode"] == 400 and agent.state_size == 11
    assert info["sha256"] == "0e1862889f6fd3237697048e26225dca567bfe474dae3a4cd51f29010fb4f9e7"
    a2, i2 = load_candidate_checkpoint(run, "ckpt_ep0400.pt")
    assert i2["obs_version"] == OBS_V1
    assert {f: sha(run / f) for f in before} == before                         # loading never writes


def test_dqn_controller_refuses_an_environment_with_another_schema():
    v1_agent, v2_agent = SimpleNamespace(state_size=11), SimpleNamespace(state_size=15)
    env = lambda ver, rng=40.0, size=None: SimpleNamespace(cfg=SimpleNamespace(obs_version=ver, detector_range_m=rng),
                                                           state_size=size or (15 if ver == OBS_V2 else 11))
    DQNController(v1_agent, {}).start_episode(env(OBS_V1))                       # legacy info without obs_version = v1
    DQNController(v2_agent, {"obs_version": OBS_V2, "detector_range_m": 40.0}).start_episode(env(OBS_V2))
    for ctrl, e in ((DQNController(v1_agent, {}), env(OBS_V2)),
                    (DQNController(v2_agent, {"obs_version": OBS_V2, "detector_range_m": 40.0}), env(OBS_V1)),
                    (DQNController(v2_agent, {"obs_version": OBS_V2, "detector_range_m": 40.0}), env(OBS_V2, 25.0))):
        with pytest.raises(CheckpointSchemaError):
            ctrl.start_episode(e)
    with pytest.raises(ValueError):
        DQNController(v1_agent, {}).start_episode(env(OBS_V1, size=15))


def test_environment_settings_follow_the_evaluated_checkpoint():
    from app.evaluation.runner import _obs_kwargs
    assert _obs_kwargs(None) == {} and _obs_kwargs(DQNController(None, {})) == {}
    assert _obs_kwargs(DQNController(None, {"obs_version": OBS_V1})) == {}
    assert _obs_kwargs(DQNController(None, {"obs_version": OBS_V2, "detector_range_m": 25.0})) == {"obs_version": OBS_V2, "detector_range_m": 25.0}


def test_training_cli_defaults_to_v1():
    import train_dqn
    a = train_dqn.build_parser().parse_args(["--run-id", "x"])
    assert a.obs_version == OBS_V1 and a.detector_range_m == 40.0
    a = train_dqn.build_parser().parse_args(["--run-id", "x", "--obs-version", OBS_V2, "--detector-range-m", "25"])
    cfg = train_dqn.config_from_args(a)
    assert cfg.obs_version == OBS_V2 and cfg.detector_range_m == 25.0
    with pytest.raises(SystemExit):
        train_dqn.build_parser().parse_args(["--run-id", "x", "--obs-version", "fyp-obs-v9"])


def test_each_presence_feature_uses_its_own_group_capacity_and_order():
    asym = JunctionTopology("A", ("a", "b", "c"), (300.0, 300.0, 30.0), ((0, 1), (2,)), (0, 2), 4)   # group 1: one short lane
    c0, c1 = presence_capacity(asym, 0, 40.0), presence_capacity(asym, 1, 40.0)
    assert c0 == pytest.approx(80 / 7.5) and c1 == pytest.approx(30 / 7.5)
    v, _ = encode_state_v2(asym, _meas(), 0, 0.0, (1, 2, 3, 0), 40.0)
    assert list(v[11:]) == pytest.approx([1 / c0, 2 / c0, min(3 / c1, 1.0), 0.0])
    v, _ = encode_state_v2(asym, _meas(), 2, 0.0, (1, 0, 0, 1), 40.0)          # phase 2: served = the short group
    assert list(v[11:]) == pytest.approx([1 / c1, 0.0, 0.0, 1 / c0])


def test_presence_tuple_order_is_served_moving_served_stopped_opposing_moving_opposing_stopped():
    conn = FakeConn({"sm": ("a", 290.0, 3.0), "ss1": ("a", 295.0, 0.0), "ss2": ("b", 395.0, 0.0),
                     "om1": ("c", 280.0, 2.0), "om2": ("c", 270.0, 2.0), "om3": ("d", 380.0, 2.0), "os": ("d", 399.0, 0.0)})
    assert read_presence(conn, TOPO, 0, 40.0) == (1, 2, 3, 1)
    assert read_presence(conn, TOPO, 3, 40.0) == (3, 1, 1, 2)                 # yellow after phase 2: served = group 1


def test_load_checkpoint_validates_the_schema_even_when_sizes_match(tmp_path):
    agent = MaskedDoubleDQN(11, 4, hidden=8, seed=0)
    save_checkpoint(tmp_path / "bad.pt", agent, episode=1, decisions=1, val_score=None, val_metric="mean_wait_s",
                    train_config={"hidden": 8}, feature_names=V1_NAMES[::-1])            # wrong v1 feature names, right size
    with pytest.raises(CheckpointSchemaError):
        load_checkpoint(tmp_path / "bad.pt", MaskedDoubleDQN(11, 4, hidden=8))
