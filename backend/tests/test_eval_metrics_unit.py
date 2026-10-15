"""Stage-4 unit tests (no SUMO): metric arithmetic, seeds, statistics, fixed-time verification, ledger, controllers, loader."""

from __future__ import annotations

import json
import math
import sys
import types
from types import SimpleNamespace

import numpy as np
import pytest

from app.environment.signal_safety import KEEP, SWITCH, EXTEND, REDUCE, PhaseView, SignalSafetyConfig
from app.evaluation import metrics as M
from app.evaluation import seeds as ES
from app.evaluation.controllers import (ActuatedStyleController, DQNController, FixedTimeController, RuleBasedController,
                                        build_controllers)
from app.evaluation.protocol import (EvalProtocol, ProtocolError, append_ledger, assert_final_not_repeated,
                                     load_validation_selected_checkpoint, program_from_net, read_ledger, verify_fixed_time_timing)
from app.evaluation.runner import paired_difference, summarize, t_critical_95
from app.training import seeds as TS


# ------------------------------------------------------------------ trip ledger
def _ledger():
    L = M.TripLedger()
    L.depart("warm", 100.0); L.add_wait("warm", 5); L.arrive("warm", 200.0)         # departs before the window: excluded
    L.depart("a", 300.0); L.add_wait("a", 10); L.arrive("a", 400.0)                # completed, 100 s, 10 s wait
    L.depart("b", 500.0); L.add_wait("b", 30); L.arrive("b", 560.0)                # completed, 60 s, 30 s wait
    L.depart("c", 2000.0); L.add_wait("c", 20)                                      # unfinished at 2100
    return L


def test_trip_summary_by_hand():
    s = _ledger().summary(300.0, 2100.0)
    assert (s["trips_departed"], s["trips_completed"], s["trips_unfinished"]) == (3, 2, 1)
    assert s["unfinished_share"] == pytest.approx(1 / 3)
    assert s["wait_per_vehicle_all_s"] == pytest.approx((10 + 30 + 20) / 3)           # unfinished counted with partial wait
    assert s["wait_per_vehicle_completed_s"] == pytest.approx(20.0)
    assert s["travel_time_completed_s"] == pytest.approx(80.0)
    assert s["unfinished_age_mean_s"] == pytest.approx(100.0)                         # only c, followed until the run end (2100)
    assert s["completion_rate"] == pytest.approx(2 / 3) and s["trips_not_inserted"] == 0 and s["trips_scheduled"] == 3
    assert s["arrivals_in_window"] == 2 and s["throughput_veh_per_h"] == pytest.approx(2 / 0.5)


def test_departures_before_the_window_are_excluded_but_arrivals_in_window_count_for_throughput():
    L = M.TripLedger()
    L.depart("w", 250.0); L.arrive("w", 400.0)
    s = L.summary(300.0, 2100.0)
    assert s["trips_departed"] == 0 and s["arrivals_in_window"] == 1 and math.isnan(s["wait_per_vehicle_all_s"])


def test_cohort_starts_at_the_window_start_and_keeps_delayed_insertions_after_the_window_end():
    L = M.TripLedger()
    L.depart("pre", 299.0); L.depart("s", 300.0); L.depart("late", 2103.0)           # "late": window demand inserted after the window
    L.arrive("s", 400.0); L.arrive("late", 2200.0)
    s = L.summary(300.0, 2100.0, run_end_s=2400.0)
    assert s["trips_departed"] == 2 and s["departed_after_window"] == 1 and s["trips_completed"] == 2
    assert s["travel_time_completed_s"] == pytest.approx((100 + 97) / 2)               # full durations of finished trips only
    assert s["arrivals_in_window"] == 1 and s["throughput_veh_per_h"] == pytest.approx(1 / 0.5)   # the drain arrival is not throughput


def test_drain_accounting_keeps_completed_and_unfinished_separate():
    L = M.TripLedger()
    L.depart("a", 500.0); L.arrive("a", 600.0)                                          # 100 s, completed
    L.depart("b", 2000.0)                                                               # unfinished at run end 2700
    s = L.summary(300.0, 2100.0, run_end_s=2700.0, not_inserted=2)
    assert s["travel_time_completed_s"] == 100.0                                        # not diluted by the unfinished trip
    assert s["unfinished_age_mean_s"] == 700.0                                          # lower bound, reported on its own
    assert s["trips_scheduled"] == 4 and s["trips_not_inserted"] == 2 and s["completion_rate"] == pytest.approx(1 / 4)
    assert s["unfinished_share"] == pytest.approx(1 / 2)


def test_lane_accumulator_per_lane_means():
    acc = M.LaneAccumulator(2)
    acc.add([2, 16], [1, 8], [0.1, 0.8]); acc.add([4, 0], [3, 0], [0.3, 0.0])
    a, b = acc.per_lane()
    assert a["mean_vehicles"] == 3 and a["mean_queue"] == 2 and a["mean_occupancy_pct"] == pytest.approx(20) and a["pct_steps_congested"] == 0
    assert b["mean_vehicles"] == 8 and b["pct_steps_congested"] == 50


@pytest.mark.parametrize("bad", [lambda L: L.depart("a", 1.0), lambda L: L.arrive("zz", 5.0), lambda L: L.arrive("a", 0.5),
                                 lambda L: L.add_wait("zz", 1)])
def test_ledger_refuses_inconsistent_events(bad):
    L = M.TripLedger(); L.depart("a", 1.0)
    with pytest.raises(M.MeasurementError):
        bad(L)


def test_double_arrival_and_wait_after_arrival_refused():
    L = M.TripLedger(); L.depart("a", 1.0); L.arrive("a", 5.0)
    with pytest.raises(M.MeasurementError):
        L.arrive("a", 6.0)
    with pytest.raises(M.MeasurementError):
        L.add_wait("a", 1)


# ------------------------------------------------------------------ lane accumulator
def test_lane_accumulator_by_hand():
    acc = M.LaneAccumulator(4)
    acc.add([2, 0, 16, 4], [1, 0, 8, 0], [0.1, 0.0, 0.8, 0.3])
    acc.add([0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0])
    s = acc.summary()
    assert s["n_lane_obs"] == 8 and s["n_steps_measured"] == 2
    assert s["mean_vehicles_per_lane"] == pytest.approx(22 / 8)
    assert s["mean_queue_per_lane"] == pytest.approx(9 / 8)
    assert s["mean_occupancy_pct"] == pytest.approx(100 * 1.2 / 8)
    assert s["pct_lane_steps_congested"] == pytest.approx(100 * 1 / 8)                   # only lane 3 (occ .8 / 16 veh) congested
    assert s["max_queue_any_lane"] == 8


def test_congestion_threshold_is_occupancy_or_vehicle_count():
    acc = M.LaneAccumulator(2)
    acc.add([16, 3], [0, 0], [0.1, 0.71])
    assert acc.summary()["pct_lane_steps_congested"] == 100.0
    acc2 = M.LaneAccumulator(2); acc2.add([15, 3], [0, 0], [0.7, 0.1])
    assert acc2.summary()["pct_lane_steps_congested"] == 0.0                              # thresholds are strict


@pytest.mark.parametrize("c,h,o", [([1, 1], [0, 0], [0, 0, 0]), ([1], [0], [0]), ([1, 1], [2, 0], [0, 0]),
                                   ([1, 1], [0, 0], [0, 1.5]), ([float("nan"), 1], [0, 0], [0, 0]), ([-1, 1], [0, 0], [0, 0])])
def test_lane_accumulator_refuses_invalid_observations(c, h, o):
    with pytest.raises(M.MeasurementError):
        M.LaneAccumulator(2).add(c, h, o)


def test_empty_accumulator_gives_nan_not_zero():
    assert math.isnan(M.LaneAccumulator(2).summary()["mean_queue_per_lane"])


# ------------------------------------------------------------------ episode measurer with a fake TraCI connection
class _Conn:
    def __init__(self, script):
        self.script, self.k = script, 0
        outer = self
        self.simulation = SimpleNamespace(getDepartedIDList=lambda: outer.cur["dep"], getArrivedIDList=lambda: outer.cur["arr"],
                                          getStartingTeleportNumber=lambda: 0)
        self.vehicle = SimpleNamespace(subscribe=lambda v, vs: None, getAllSubscriptionResults=lambda: {v: {0x40: s} for v, s in outer.cur["spd"].items()})
        self.lane = SimpleNamespace(getLastStepVehicleNumber=lambda l: outer.cur["n"], getLastStepHaltingNumber=lambda l: outer.cur["h"],
                                    getLastStepOccupancy=lambda l: outer.cur["o"])

    @property
    def cur(self):
        return self.script[self.k]


@pytest.fixture
def fake_traci(monkeypatch):
    mod = types.ModuleType("traci"); const = types.ModuleType("traci.constants"); const.VAR_SPEED = 0x40
    mod.constants = const
    monkeypatch.setitem(sys.modules, "traci", mod); monkeypatch.setitem(sys.modules, "traci.constants", const)


def _step(dep=(), arr=(), spd=None, n=0, h=0, o=0.0):
    return {"dep": list(dep), "arr": list(arr), "spd": spd or {}, "n": n, "h": h, "o": o}


def test_measurer_counts_waiting_after_insertion_step_and_window(fake_traci):
    # warm-up 2 s, measure 3 s -> steps starting at 2,3,4 are measured; the run has 5 steps (t = 1..5)
    script = [_step(), _step(), _step(dep=["v"], spd={"v": 0.0}, n=1, h=1, o=0.5),      # v inserted in the step starting at 2
              _step(spd={"v": 0.0}, n=1, h=1, o=0.5), _step(spd={"v": 5.0}, n=1, h=0, o=0.2),
              _step(arr=["v"], n=0, h=0, o=0.0)]
    m = M.EpisodeMeasurer(["l0"], warmup_s=2, measure_s=3)
    conn = _Conn(script)
    for k, t in enumerate(range(1, 7)):
        conn.k = k
        m(conn, float(t))
    assert m.lane_acc.steps == 3                                                           # starts 2,3,4 (start 5 is beyond the window)
    trip = m.ledger.trips["v"]
    assert trip.depart_s == 2.0 and trip.arrive_s == 5.0
    assert trip.wait_s == 1.0                                                              # insertion step skipped, one stopped second counted


def test_measurer_finalize_refuses_incomplete_episodes(fake_traci):
    m = M.EpisodeMeasurer(["l0"], warmup_s=0, measure_s=3)
    conn = _Conn([_step(), _step()])
    for k in range(2):
        conn.k = k; m(conn, float(k + 1))
    with pytest.raises(M.MeasurementError):
        m.finalize(3)
    with pytest.raises(M.MeasurementError):
        m.finalize(2)                                                                      # right step count, but lane window incomplete


def test_measurer_rejects_duplicate_lanes():
    with pytest.raises(M.MeasurementError):
        M.EpisodeMeasurer(["a", "a"], 0, 1)


# ------------------------------------------------------------------ statistics
def test_paired_difference_matches_scipy():
    scipy_stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(0)
    a, b = rng.normal(10, 2, 30), rng.normal(9, 2, 30)
    r = paired_difference(a, b)
    d = a - b
    lo, hi = scipy_stats.t.interval(0.95, 29, loc=d.mean(), scale=scipy_stats.sem(d))
    assert r["mean_diff"] == pytest.approx(d.mean()) and r["ci95_low"] == pytest.approx(lo, rel=1e-3) and r["ci95_high"] == pytest.approx(hi, rel=1e-3)


@pytest.mark.parametrize("df", [1, 5, 29, 30, 31, 60, 200])
def test_t_critical_matches_scipy(df):
    scipy_stats = pytest.importorskip("scipy.stats")
    assert t_critical_95(df) == pytest.approx(scipy_stats.t.ppf(0.975, df), rel=2e-3)


def test_summarize_requires_exactly_matched_seeds():
    row = lambda c, s: {"controller": c, "seed": s, **{k: 1.0 for k in __import__("app.evaluation.runner", fromlist=["x"]).METRIC_KEYS}}
    rows = [row("fixed_time", 1), row("fixed_time", 2), row("rule_based", 1)]
    with pytest.raises(ProtocolError):
        summarize(rows, ["fixed_time", "rule_based"], [1, 2])
    rows.append(row("rule_based", 2))
    out = summarize(rows, ["fixed_time", "rule_based"], [1, 2])
    assert out["paired_vs_fixed_time"]["rule_based"]["wait_per_vehicle_all_s"]["mean_diff"] == 0.0 and "no claim of superiority" in out["note"]


# ------------------------------------------------------------------ seeds
def test_eval_seed_ranges_are_disjoint_from_training_and_validation():
    final, smoke = ES.eval_seeds(30, "final"), ES.eval_seeds(30, "smoke")
    assert len(set(final)) == 30 and final == sorted(final) and final[0] == 4_000_001
    for s in final + smoke:
        with pytest.raises(TS.SeedError):
            TS.assert_not_protected(s)                                                     # training/validation refuse every eval seed
    for s in [TS.train_seed(e) for e in (1, 400)] + TS.val_seeds(20):
        assert not (4_000_000 <= s <= 5_999_999)
    assert not set(final) & set(smoke)


def test_eval_seeds_refuse_other_ranges_and_duplicates():
    with pytest.raises(ES.EvalSeedError):
        ES.assert_seeds_for_mode([3_000_001], "final")
    with pytest.raises(ES.EvalSeedError):
        ES.assert_seeds_for_mode([4_000_001], "smoke")
    with pytest.raises(ES.EvalSeedError):
        ES.assert_seeds_for_mode([4_000_001, 4_000_001], "final")
    with pytest.raises(ES.EvalSeedError):
        ES.eval_seeds(5, "final", base=3_999_998)
    with pytest.raises(ES.EvalSeedError):
        ES.eval_seeds(0, "final")


def test_protocol_validation():
    p = EvalProtocol()
    assert (p.warmup_s, p.measure_s, p.demand_end_s, p.n_seeds) == (300, 1800, 2100, 30)
    for kw in ({"measure_s": 0}, {"warmup_s": -1}, {"decision_interval_s": 7}, {"n_seeds": 0}, {"mode": "x"}):
        with pytest.raises(ProtocolError):
            EvalProtocol(**kw)


# ------------------------------------------------------------------ fixed-time verification
PROG = {"A": [(30.0, "G"), (5.0, "y"), (30.0, "r"), (5.0, "y")]}


def _log(durs, start=0):
    return [{"junction": "A", "phase": (start + i) % 4, "duration_s": d} for i, d in enumerate(durs)]


GOOD = [30, 5, 30, 5] * 3


def test_verification_accepts_the_configured_programme():
    assert verify_fixed_time_timing(_log(GOOD), PROG, ["A"])["ok"]


@pytest.mark.parametrize("durs,start", [([31] + GOOD[1:], 0), ([30, 6] + GOOD[2:], 0), (GOOD[:6], 0), (GOOD, 1)])
def test_verification_rejects_deviations(durs, start):
    with pytest.raises(ProtocolError):
        verify_fixed_time_timing(_log(durs, start), PROG, ["A"])


def test_verification_rejects_skipped_phase_and_unknown_junction():
    log = _log(GOOD); log[3]["phase"] = 0
    with pytest.raises(ProtocolError):
        verify_fixed_time_timing(log, PROG, ["A"])
    with pytest.raises(ProtocolError):
        verify_fixed_time_timing(_log(GOOD), PROG, ["Z"])


def test_configured_programme_is_read_from_the_network_file():
    prog = program_from_net()
    assert set(prog) >= {"junctionA", "junctionB", "junctionC", "junctionD"}
    assert [d for d, _ in prog["junctionA"]] == [30.0, 5.0, 30.0, 5.0]


# ------------------------------------------------------------------ ledger
def test_final_ledger_blocks_repeats_unless_explicit(tmp_path):
    p = tmp_path / "ledger.jsonl"
    assert read_ledger(p) == []
    append_ledger(p, {"mode": "final", "checkpoint_sha256": "abc", "run_id": "r1"})
    append_ledger(p, {"mode": "smoke", "checkpoint_sha256": "def", "run_id": "r2"})
    led = read_ledger(p)
    with pytest.raises(ProtocolError):
        assert_final_not_repeated(led, "abc", False)
    assert_final_not_repeated(led, "abc", True)
    assert_final_not_repeated(led, "def", False)                                            # smoke runs do not use up the final slot
    assert_final_not_repeated(led, "new", False)


# ------------------------------------------------------------------ controllers on a fake environment
class _Env:
    def __init__(self, view):
        self._view = view
        self.cfg = SimpleNamespace(junction_ids=["A"], safety=SignalSafetyConfig())
        self.sim_time = 100.0
        self.topology = {"A": SimpleNamespace(lanes=("l0", "l1", "l2", "l3"), lengths_m=(200.0,) * 4, groups=((0, 1), (2, 3)), green_phases=(0, 2))}
        self.vehicles = {}                                                                  # lane -> [positions]
        pos = {}
        self.conn = SimpleNamespace(
            lane=SimpleNamespace(getLastStepVehicleNumber=lambda l: len(self.vehicles.get(l, [])),
                                 getLastStepVehicleIDs=lambda l: [f"{l}:{i}" for i in range(len(self.vehicles.get(l, [])))]),
            vehicle=SimpleNamespace(getLanePosition=lambda vid: self.vehicles[vid.split(":")[0]][int(vid.split(":")[1])]))

    def phase_view(self, j):
        return self._view


def _masks(view):
    from app.environment.signal_safety import legal_action_mask
    return {"A": legal_action_mask(view, SignalSafetyConfig())}


def test_fixed_time_always_keeps():
    env = _Env(PhaseView(0, True, 12, 18))
    assert FixedTimeController().act(env, {}, _masks(env._view)) == {"A": KEEP}


@pytest.mark.parametrize("d,g", [(0, 20), (19.9, 20), (20, 35), (39.9, 35), (40, 55), (100, 55)])
def test_rule_target_green_thresholds(d, g):
    assert RuleBasedController.target_green(d) == g


def test_rule_based_moves_the_green_toward_its_target_through_safe_actions():
    env = _Env(PhaseView(0, True, 5, 25))                                                    # total 30
    ctrl = RuleBasedController(); ctrl.start_episode(env)
    assert ctrl.act(env, {}, _masks(env._view)) == {"A": REDUCE}                             # empty lanes -> target 20 < 30
    env.vehicles = {"l0": [10] * 10}                                                         # 10 veh / 0.2 km = 50/km -> target 55
    ctrl.start_episode(env)
    assert ctrl.act(env, {}, _masks(env._view)) == {"A": EXTEND}
    env2 = _Env(PhaseView(1, False, 2, 3))
    assert RuleBasedController().act(env2, {}, _masks(env2._view)) == {"A": KEEP}            # yellow is never touched


def test_actuated_gaps_out_extends_and_respects_limits():
    env = _Env(PhaseView(0, True, 15, 15))
    ctrl = ActuatedStyleController()
    env.vehicles = {"l2": [190.0]}                                                           # demand on the other phase only, served empty
    assert ctrl.act(env, {}, _masks(env._view)) == {"A": SWITCH}
    env.vehicles = {"l2": [190.0], "l0": [180.0]}                                            # served approach still has a vehicle at the stop line
    assert ctrl.act(env, {}, _masks(env._view)) == {"A": KEEP}                               # remaining 15 > step: nothing to extend yet
    env2 = _Env(PhaseView(0, True, 25, 5)); env2.vehicles = {"l0": [180.0]}
    assert ctrl.act(env2, {}, _masks(env2._view)) == {"A": EXTEND}
    env3 = _Env(PhaseView(0, True, 45, 5)); env3.vehicles = {"l0": [180.0]}
    assert ctrl.act(env3, {}, _masks(env3._view)) == {"A": KEEP}                             # 45 + 5 + 5 > max 50
    env4 = _Env(PhaseView(0, True, 5, 25)); env4.vehicles = {"l2": [190.0]}
    assert ctrl.act(env4, {}, _masks(env4._view)) == {"A": KEEP}                             # min green not reached


def test_dqn_controller_is_greedy_over_legal_actions():
    calls = []
    agent = SimpleNamespace(greedy=lambda o, m: calls.append((o, m.copy())) or 1)
    env = _Env(PhaseView(0, True, 12, 18))
    assert DQNController(agent).act(env, {"A": np.zeros(11)}, _masks(env._view)) == {"A": 1} and calls


def test_build_controllers_needs_dqn_and_rejects_unknown():
    assert [c.name for c in build_controllers(["fixed_time", "rule_based", "actuated_style"])] == ["fixed_time", "rule_based", "actuated_style"]
    with pytest.raises(Exception):
        build_controllers(["dqn"])
    with pytest.raises(Exception):
        build_controllers(["nope"])


# ------------------------------------------------------------------ checkpoint loader refuses everything except a validation-selected run
def test_loader_refuses_missing_and_legacy_checkpoints(tmp_path):
    with pytest.raises(ProtocolError):
        load_validation_selected_checkpoint(tmp_path)
    from pathlib import Path
    legacy = Path(__file__).resolve().parents[1] / "data" / "models" / "dqn_agent.pt"
    if legacy.exists():
        d = tmp_path / "legacy"; d.mkdir()
        import shutil, hashlib
        shutil.copy(legacy, d / "best.pt"); shutil.copy(legacy, d / "x.pt")
        (d / "best.json").write_text(json.dumps({"file": "x.pt", "score": 1.0}))
        with pytest.raises(ProtocolError, match="legacy|format"):
            load_validation_selected_checkpoint(d)


def test_loader_refuses_altered_selection(tmp_path):
    (tmp_path / "best.json").write_text(json.dumps({"file": "a.pt", "score": 1.0}))
    (tmp_path / "a.pt").write_bytes(b"one"); (tmp_path / "best.pt").write_bytes(b"two")
    with pytest.raises(ProtocolError, match="altered|match"):
        load_validation_selected_checkpoint(tmp_path)


def test_statistics_ignore_undefined_seeds_and_report_how_many_were_used():
    from app.evaluation.runner import describe
    nan = float("nan")
    assert describe([1.0, nan, 3.0])["n"] == 2 and describe([nan, nan])["n"] == 0
    r = paired_difference([2.0, nan, 5.0, 9.0], [1.0, 4.0, 3.0, nan])
    assert r["n_pairs"] == 2 and r["mean_diff"] == pytest.approx(1.5) and r["median_diff"] == pytest.approx(1.5)


def test_paired_median_is_the_median_not_the_mean():
    assert paired_difference([1.0, 2.0, 12.0], [0.0, 0.0, 0.0])["median_diff"] == 2.0


def test_paired_ci_formula_by_hand():
    d = np.array([1.0, 2.0, 3.0, 6.0])
    r = paired_difference(d, np.zeros(4))
    half = 3.182 * d.std(ddof=1) / 2.0                                                    # t(0.975, 3) * sd / sqrt(4)
    assert r["ci95_low"] == pytest.approx(3.0 - half) and r["ci95_high"] == pytest.approx(3.0 + half)


def test_protocol_drain_arithmetic():
    p = EvalProtocol()
    assert (p.demand_end_s, p.drain_max_s, p.horizon_s) == (2100, 600, 2700)
    with pytest.raises(ProtocolError):
        EvalProtocol(drain_max_s=-5)
    with pytest.raises(ProtocolError):
        EvalProtocol(drain_max_s=7)


def test_describe_uses_the_sample_standard_deviation():
    from app.evaluation.runner import describe
    d = describe([1.0, 2.0, 3.0, 4.0])
    assert d["mean"] == 2.5 and d["sd"] == pytest.approx(math.sqrt(5 / 3)) and d["n"] == 4 and (d["min"], d["max"]) == (1.0, 4.0)
    assert math.isnan(describe([1.0])["sd"])
