"""Stage-4 live tests: the evaluation protocol on real SUMO.

Everything runs on *short* episodes (30 s warm-up + 150 s measured) with throw-away outputs in pytest temp dirs. The numbers
produced are protocol checks, never performance results.
"""

from __future__ import annotations

import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("traci")
sumolib = pytest.importorskip("sumolib")

from app.environment.signal_safety import KEEP, SWITCH
from app.environment.traffic_env import EnvConfig, TrafficSignalEnv
from app.evaluation import runner
from app.evaluation.controllers import DQNController, EvalController, FixedTimeController
from app.evaluation.metrics import EpisodeMeasurer, MeasurementError
from app.evaluation.protocol import EvalProtocol, ProtocolError, load_validation_selected_checkpoint, program_from_net, sha256_file
from app.evaluation.seeds import eval_seeds
from app.training.runs import BACKEND, RunDirError
from app.training.trainer import TrainConfig, train

try:
    sumolib.checkBinary("sumo")
except Exception:  # pragma: no cover
    pytest.skip("SUMO binary not available", allow_module_level=True)

TRACKED_ROUTES = BACKEND / "sumo" / "routes" / "intelliroads.rou.xml"
PROTO = EvalProtocol(warmup_s=30, measure_s=150, n_seeds=2, drain_max_s=300, mode="smoke")
DEMAND_END = PROTO.demand_end_s
BASELINES = ["fixed_time", "rule_based", "actuated_style"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def protected():
    files = [TRACKED_ROUTES, BACKEND / "data" / "models" / "dqn_agent.pt", BACKEND / "sumo" / "network" / "intelliroads.net.xml",
             BACKEND / "sumo" / "config" / "intelliroads.sumocfg"]
    files += sorted((BACKEND / "evaluation_results").glob("*")) if (BACKEND / "evaluation_results").exists() else []
    files += sorted((BACKEND / "final_dqn_model").glob("*")) if (BACKEND / "final_dqn_model").exists() else []
    return {str(f): sha(f) for f in files if f.is_file()}


@pytest.fixture(scope="module")
def before():
    return protected()


@pytest.fixture(scope="module")
def run(tmp_path_factory, before):
    out = tmp_path_factory.mktemp("evalruns")
    res = runner.evaluate(PROTO, BASELINES, eval_seeds(2, "smoke"), out, "t1", argv=["test"], progress=lambda s: None)
    res["out"] = out
    return res


def rows_of(run, controller):
    return {r["seed"]: r for r in run["rows"] if r["controller"] == controller}


# ------------------------------------------------------------------ consistent measurement across controllers
def test_all_16_lanes_are_measured_for_every_controller(run):
    assert run["protocol"]["lanes_measured"] == 16
    for r in run["rows"]:
        assert r["n_lane_obs"] == 16 * PROTO.measure_s and r["n_steps_measured"] == PROTO.measure_s and r["n_steps_total"] == DEMAND_END + r["drain_s_used"]


def test_env_has_exactly_16_distinct_incoming_lanes_four_per_junction():
    env = TrafficSignalEnv(EnvConfig(horizon_s=60))
    try:
        env.reset(5_000_001)
        assert len(runner.lanes_of(env)) == 16 and all(len(env.topology[j].lanes) == 4 for j in env.cfg.junction_ids)
    finally:
        env.close()


def test_matched_seeds_give_identical_demand_across_controllers(run):
    seeds = eval_seeds(2, "smoke")
    for s in seeds:
        departed = {c: rows_of(run, c)[s]["trips_scheduled"] for c in BASELINES}
        assert len(set(departed.values())) == 1 and departed["fixed_time"] > 0
    assert rows_of(run, "fixed_time")[seeds[0]]["trips_departed"] != rows_of(run, "fixed_time")[seeds[1]]["trips_departed"] or \
        rows_of(run, "fixed_time")[seeds[0]]["wait_per_vehicle_all_s"] != rows_of(run, "fixed_time")[seeds[1]]["wait_per_vehicle_all_s"]


def test_same_seed_and_controller_reproduce_exactly(run):
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, demand_end_s=DEMAND_END))
    try:
        seed = eval_seeds(2, "smoke")[0]
        again = runner.run_episode(env, FixedTimeController(), seed, PROTO)["row"]
    finally:
        env.close()
    first = rows_of(run, "fixed_time")[seed]
    for k in runner.METRIC_KEYS:
        assert again[k] == first[k] or (np.isnan(again[k]) and np.isnan(first[k])), k


def test_every_controller_completes_the_episode_with_no_violations(run):
    for r in run["rows"]:
        assert r["decisions"] == (DEMAND_END + r["drain_s_used"]) // PROTO.decision_interval_s and r["drain_s_used"] >= 0
    assert any(r["actions_switch"] + r["actions_extend"] + r["actions_reduce"] > 0 for r in run["rows"] if r["controller"] != "fixed_time")
    for r in run["rows"]:
        if r["controller"] == "fixed_time":
            assert r["actions_switch"] == r["actions_extend"] == r["actions_reduce"] == 0


def test_unfinished_and_completed_trips_are_consistent(run):
    for r in run["rows"]:
        assert r["trips_completed"] + r["trips_unfinished"] == r["trips_departed"]
        assert r["unfinished_share"] == pytest.approx(r["trips_unfinished"] / r["trips_departed"])
        if r["trips_unfinished"] == 0:                              # nothing unfinished -> no unfinished age is reported
            assert np.isnan(r["unfinished_age_mean_s"]) and r["completion_rate"] == 1.0
        assert 0 < r["travel_time_completed_s"] <= PROTO.horizon_s


# ------------------------------------------------------------------ trip metrics agree with SUMO's own tripinfo output
def test_trip_metrics_match_sumo_tripinfo(tmp_path):
    info = tmp_path / "tripinfo.xml"
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, demand_end_s=DEMAND_END, extra_sumo_args=("--tripinfo-output", str(info))))
    seed = eval_seeds(1, "smoke")[0]
    try:
        env.reset(seed)
        m = EpisodeMeasurer(runner.lanes_of(env), 0, PROTO.horizon_s)          # window = whole episode
        env.add_second_hook(m)
        while True:
            r = env.step({j: KEEP for j in env.cfg.junction_ids})
            if r.terminated or r.truncated:
                break
    finally:
        env.close()
    trips = ET.parse(info).getroot().findall("tripinfo")
    assert len(trips) >= 10
    for t in trips:
        mine = m.ledger.trips[t.get("id")]
        assert mine.arrive_s - mine.depart_s == pytest.approx(float(t.get("duration")), abs=1e-6)
        assert mine.depart_s == pytest.approx(float(t.get("depart")), abs=1e-6)                # step-start convention equals SUMO's own depart time
        assert mine.wait_s == pytest.approx(float(t.get("waitingTime")), abs=1e-6)
    assert sum(1 for t in m.ledger.trips.values() if t.arrive_s is not None) == len(trips)


# ------------------------------------------------------------------ fixed-time baseline vs SUMO's configured programme
def test_fixed_time_timings_match_the_network_programme(run):
    checks = json.loads((run["run_dir"] / "timing_check.json").read_text())
    assert checks["checked"] and len(checks["per_seed"]) == 2 and all(c["ok"] for c in checks["per_seed"])
    net = ET.parse(BACKEND / "sumo" / "network" / "intelliroads.net.xml").getroot()
    for tl in net.findall("tlLogic"):
        assert run["protocol"]["configured_programme"][tl.get("id")] == [float(p.get("duration")) for p in tl.findall("phase")]


def test_timing_verification_detects_a_baseline_that_deviates_from_the_programme():
    class Cheater(FixedTimeController):                       # claims to be the fixed-time baseline but switches early
        def act(self, env, obs, masks):
            return {j: SWITCH if masks[j][SWITCH] else KEEP for j in env.cfg.junction_ids}
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, demand_end_s=DEMAND_END))
    try:
        with pytest.raises(ProtocolError, match="configured programme"):
            runner.run_episode(env, Cheater(), eval_seeds(1, "smoke")[0], PROTO)
    finally:
        env.close()


# ------------------------------------------------------------------ episode completion
def test_run_episode_refuses_an_episode_that_does_not_reach_the_protocol_horizon():
    env = TrafficSignalEnv(EnvConfig(horizon_s=100))          # protocol says 180 s
    try:
        with pytest.raises(ProtocolError):
            runner.run_episode(env, FixedTimeController(), eval_seeds(1, "smoke")[0], PROTO)
    finally:
        env.close()


def test_run_episode_refuses_an_illegal_action():
    class Rogue(EvalController):
        name = "rogue"
        def act(self, env, obs, masks):
            return {j: SWITCH for j in env.cfg.junction_ids}  # illegal before min green
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, demand_end_s=DEMAND_END))
    try:
        with pytest.raises(Exception):
            runner.run_episode(env, Rogue(), eval_seeds(1, "smoke")[0], PROTO)
    finally:
        env.close()


# ------------------------------------------------------------------ route-file and result integrity
def test_evaluation_never_touches_tracked_routes_or_existing_results(run, before):
    assert protected() == before
    assert TRACKED_ROUTES.read_bytes() == TRACKED_ROUTES.read_bytes() and sha(TRACKED_ROUTES) == before[str(TRACKED_ROUTES)]


def test_run_directory_is_new_and_outputs_are_complete(run):
    d = run["run_dir"]
    assert d.parent == run["out"] and {p.name for p in d.iterdir()} == {"protocol.json", "episodes.csv", "lanes.csv", "summary.json", "timing_check.json", "timing.json"}
    with open(d / "episodes.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6 and [r["seed"] for r in rows[:3]] == [r["seed"] for r in rows[:1]] * 3            # seed-major, matched
    assert (run["out"] / "ledger.jsonl").exists()
    with pytest.raises(RunDirError):
        runner.evaluate(PROTO, ["fixed_time"], eval_seeds(2, "smoke"), run["out"], "t1", progress=lambda s: None)


def test_evaluation_output_cannot_go_into_protected_directories():
    for d in (BACKEND / "evaluation_results", BACKEND / "data" / "models", BACKEND / "final_dqn_model", BACKEND / "sumo" / "routes"):
        with pytest.raises(RunDirError):
            runner.create_run_dir(d, "x_should_not_exist")
        assert not (d / "x_should_not_exist").exists()


# ------------------------------------------------------------------ seed / mode separation
def test_final_mode_needs_confirmation_and_the_final_seed_range(tmp_path):
    final = EvalProtocol(n_seeds=2, mode="final", warmup_s=30, measure_s=150)
    with pytest.raises(ProtocolError, match="confirm"):
        runner.evaluate(final, ["fixed_time"], eval_seeds(2, "final"), tmp_path, "f", progress=lambda s: None)
    with pytest.raises(Exception):
        runner.evaluate(final, ["fixed_time"], eval_seeds(2, "smoke"), tmp_path, "f", confirm_final=True, progress=lambda s: None)
    with pytest.raises(Exception):
        runner.evaluate(PROTO, ["fixed_time"], eval_seeds(2, "final"), tmp_path, "f", progress=lambda s: None)
    assert not (tmp_path / "f").exists()


# ------------------------------------------------------------------ DQN path with a throw-away smoke checkpoint (no learning claim)
@pytest.fixture(scope="module")
def smoke_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("trainsmoke")
    cfg = TrainConfig(run_id="r", out_root=out, seed=7, episodes=2, horizon_s=60, val_every=1, val_n=1, warmup=32, batch_size=16, buffer_size=2000,
                      updates_per_decision=1, target_update_steps=5, eps_decay_decisions=20, smoke=True)
    train(cfg)
    return out / "r"


def test_dqn_protocol_path_runs_with_a_validation_selected_checkpoint_and_refuses_it_for_final(smoke_run, tmp_path):
    agent, info = load_validation_selected_checkpoint(smoke_run)
    assert info["smoke_training_run"] and info["sha256"] == sha256_file(smoke_run / "best.pt")
    res = runner.evaluate(PROTO, ["fixed_time", "dqn"], eval_seeds(2, "smoke"), tmp_path, "d1", dqn=DQNController(agent, info), progress=lambda s: None)
    assert {r["controller"] for r in res["rows"]} == {"fixed_time", "dqn"}
    assert all(r["n_lane_obs"] == 16 * PROTO.measure_s for r in res["rows"])
    final = EvalProtocol(n_seeds=2, mode="final", warmup_s=30, measure_s=150)
    with pytest.raises(ProtocolError, match="smoke"):
        runner.evaluate(final, ["dqn"], eval_seeds(2, "final"), tmp_path, "d2", dqn=DQNController(agent, info), confirm_final=True, progress=lambda s: None)


def test_selection_files_of_a_training_run_are_not_modified_by_evaluation(smoke_run, tmp_path):
    h = {p.name: sha(p) for p in smoke_run.iterdir() if p.is_file()}
    load_validation_selected_checkpoint(smoke_run)
    assert {p.name: sha(p) for p in smoke_run.iterdir() if p.is_file()} == h


# ------------------------------------------------------------------ legacy evaluate_controllers.py no longer writes tracked files
def test_legacy_script_helpers_refuse_the_tracked_route_and_use_temp_files(tmp_path, before):
    import evaluate_controllers as legacy
    with pytest.raises(RuntimeError, match="tracked"):
        legacy.assert_not_tracked_route(TRACKED_ROUTES)
    cfg = legacy.make_episode_config(tmp_path, 1_000_001)
    text = cfg.read_text()
    assert str(tmp_path) in text and str(TRACKED_ROUTES) not in text and (tmp_path / "episode_1000001.rou.xml").exists()
    assert protected() == before


def test_legacy_script_smoke_writes_only_to_its_new_output_directory(tmp_path, before):
    import evaluate_controllers as legacy
    if not legacy.CHECKPOINT_PATH.exists():
        pytest.skip("legacy checkpoint not present")
    legacy.main(["--episodes", "1", "--steps", "5", "--output-dir", str(tmp_path / "legacy_out")])
    assert {p.name for p in (tmp_path / "legacy_out").iterdir()} == {"eval_raw.csv", "eval_summary.csv", "eval_summary.json"}
    assert protected() == before
    with pytest.raises(RunDirError):
        legacy.main(["--episodes", "1", "--steps", "5", "--output-dir", str(tmp_path / "legacy_out")])    # never reuse a result directory


# ------------------------------------------------------------------ measurement window, demand cut-off and drain
def test_route_generator_duration_only_moves_the_flow_end_not_the_random_draws(tmp_path):
    from app.sumo_tools.route_generator import generate_routefile
    a, b = tmp_path / "a.rou.xml", tmp_path / "b.rou.xml"
    generate_routefile(seed=5_000_001, output_path=a, duration=3600)
    generate_routefile(seed=5_000_001, output_path=b, duration=DEMAND_END)
    ra, rb = a.read_text(), b.read_text()
    assert ra != rb and ra.replace('end="3600"', f'end="{DEMAND_END}"') == rb               # same flows, same periods, earlier end
    assert 'end="3600"' not in rb


def test_the_episode_route_stops_demand_at_the_end_of_the_measured_window():
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, demand_end_s=DEMAND_END))
    try:
        env.reset(eval_seeds(1, "smoke")[0])
        flows = ET.parse(env.route_file).getroot().findall("flow")
        assert flows and {int(f.get("end")) for f in flows} == {DEMAND_END}
        assert env.route_file.resolve() != TRACKED_ROUTES.resolve()
    finally:
        env.close()


def test_drain_lets_measured_trips_finish_and_keeps_drain_out_of_the_lane_metrics(run):
    for r in run["rows"]:
        assert r["drain_s_used"] > 0                                                         # the window ends with vehicles still travelling
        assert r["drain_exhausted"] == 0 and r["trips_unfinished"] == 0 and r["completion_rate"] == 1.0
        assert r["n_steps_total"] > PROTO.warmup_s + PROTO.measure_s and r["n_steps_measured"] == PROTO.measure_s   # drain steps not measured
        assert r["trips_completed"] == r["trips_departed"] and r["vehicles_left_at_end"] == 0


def test_without_drain_unfinished_trips_are_reported_separately_never_mixed(tmp_path):
    p0 = EvalProtocol(warmup_s=30, measure_s=150, n_seeds=1, drain_max_s=0, mode="smoke")
    env = TrafficSignalEnv(EnvConfig(horizon_s=p0.horizon_s, demand_end_s=p0.demand_end_s))
    try:
        r = runner.run_episode(env, FixedTimeController(), eval_seeds(1, "smoke")[0], p0)["row"]
    finally:
        env.close()
    assert r["drain_exhausted"] == 1 and r["drain_s_used"] == 0 and r["trips_unfinished"] > 0 and r["vehicles_left_at_end"] > 0
    assert r["trips_completed"] + r["trips_unfinished"] == r["trips_departed"] and r["completion_rate"] < 1.0
    assert r["unfinished_age_mean_s"] > 0 and r["travel_time_completed_s"] <= p0.measure_s       # finished trips only; no partial durations inside


def test_drain_makes_more_trips_complete_than_no_drain_on_the_same_seed():
    seed = eval_seeds(1, "smoke")[0]
    out = {}
    for d in (0, 300):
        p = EvalProtocol(warmup_s=30, measure_s=150, n_seeds=1, drain_max_s=d, mode="smoke")
        env = TrafficSignalEnv(EnvConfig(horizon_s=p.horizon_s, demand_end_s=p.demand_end_s))
        try:
            out[d] = runner.run_episode(env, FixedTimeController(), seed, p)["row"]
        finally:
            env.close()
    assert out[0]["trips_scheduled"] == out[300]["trips_scheduled"]                          # same cohort
    assert out[300]["trips_completed"] > out[0]["trips_completed"]
    assert out[0]["n_lane_obs"] == out[300]["n_lane_obs"] and out[0]["mean_queue_per_lane"] == out[300]["mean_queue_per_lane"]   # lane metrics ignore the drain


def test_lane_csv_has_one_row_per_lane_per_episode(run):
    with open(run["run_dir"] / "lanes.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 16 * len(run["rows"]) and {r["junction"] for r in rows} == {"junctionA", "junctionB", "junctionC", "junctionD"}
    assert len({r["lane"] for r in rows}) == 16


def test_fixed_time_run_refuses_a_programme_that_differs_from_the_configured_one():
    prog = {j: list(v) for j, v in program_from_net().items()}
    prog["junctionA"][0] = (prog["junctionA"][0][0] + 1.0, prog["junctionA"][0][1])         # pretend the network file says 31 s
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, demand_end_s=DEMAND_END))
    try:
        with pytest.raises(ProtocolError, match="network file configures"):
            runner.run_episode(env, FixedTimeController(), eval_seeds(1, "smoke")[0], PROTO, program=prog)
    finally:
        env.close()


def test_fixed_time_follows_30_5_30_5_through_the_whole_episode_including_the_drain(run):
    checks = json.loads((run["run_dir"] / "timing_check.json").read_text())["per_seed"]
    for c in checks:
        for j in ("junctionA", "junctionB", "junctionC", "junctionD"):
            assert c[j]["configured_durations"] == [30.0, 5.0, 30.0, 5.0]
            assert c[j]["completed_phases"] >= (DEMAND_END // 35) * 2 - 2                       # phases keep being recorded past the window


# ------------------------------------------------------------------ the two guards that must DETECT wrong behaviour
def _custom_routes(body: str):
    """Route factory writing the standard types/routes plus ``body`` (flows or vehicles) into the episode's temp dir."""
    from app.sumo_tools.route_generator import ROUTES_XML, VTYPES_XML

    def factory(seed, out_dir):
        path = Path(out_dir) / f"custom_{seed}.rou.xml"
        path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<routes>\n' + VTYPES_XML + "\n" + ROUTES_XML + "\n" + body + "\n</routes>\n")
        return path
    return factory


def test_a_network_that_empties_before_the_demand_period_ends_is_detected():
    # one vehicle only: it finishes its trip long before t = DEMAND_END, so SUMO reports an empty network (termination)
    one_car = '<vehicle id="only" type="passenger" route="route_top_east" depart="40"/>'
    p1 = EvalProtocol(warmup_s=30, measure_s=300, n_seeds=1, drain_max_s=300, mode="smoke")                # demand would run to 330 s
    env = TrafficSignalEnv(EnvConfig(horizon_s=p1.horizon_s, demand_end_s=p1.demand_end_s), route_factory=_custom_routes(one_car))
    try:
        with pytest.raises(ProtocolError, match="network empty at t=.*before the demand ended"):
            runner.run_episode(env, FixedTimeController(), eval_seeds(1, "smoke")[0], p1)
        assert env.sim_time < p1.demand_end_s                                                       # the early end really happened
    finally:
        env.close()


def test_an_episode_that_empties_only_after_the_demand_ended_is_accepted():
    # a flow that runs to DEMAND_END keeps SUMO "expecting" vehicles until then, so the same check does not fire
    flow = f'<flow id="f" type="passenger" route="route_top_east" begin="0" end="{DEMAND_END}" period="20"/>'
    env = TrafficSignalEnv(EnvConfig(horizon_s=PROTO.horizon_s, demand_end_s=DEMAND_END), route_factory=_custom_routes(flow))
    try:
        row = runner.run_episode(env, FixedTimeController(), eval_seeds(1, "smoke")[0], PROTO)["row"]
    finally:
        env.close()
    assert row["drain_s_used"] > 0 and row["trips_unfinished"] == 0 and row["trips_not_inserted"] == 0


def test_vehicles_not_inserted_when_the_drain_limit_is_reached_are_counted_exactly():
    # 70 cars want to enter one lane at the same second: the lane holds only part of them, the rest wait for insertion.
    # With no drain the episode ends at once, so the waiting cars must show up as `trips_not_inserted`.
    n_cars = 70
    body = "\n".join(f'<vehicle id="c{i}" type="passenger" route="route_top_east" depart="{PROTO.warmup_s + 5}"/>' for i in range(n_cars))
    p0 = EvalProtocol(warmup_s=30, measure_s=150, n_seeds=1, drain_max_s=0, mode="smoke")
    env = TrafficSignalEnv(EnvConfig(horizon_s=p0.horizon_s, demand_end_s=p0.demand_end_s), route_factory=_custom_routes(body))
    try:
        r = runner.run_episode(env, FixedTimeController(), eval_seeds(1, "smoke")[0], p0)["row"]
        waiting_in_sumo = len(env.conn.simulation.getPendingVehicles())                         # independent read of SUMO's own queue
    finally:
        env.close()
    assert r["drain_exhausted"] == 1 and waiting_in_sumo > 0, "the scenario must really leave vehicles waiting"
    assert r["trips_not_inserted"] == waiting_in_sumo                                          # exactly SUMO's queue, not 0
    assert r["trips_scheduled"] == n_cars == r["trips_departed"] + r["trips_not_inserted"]     # nobody is lost from the cohort
    assert r["trips_departed"] < n_cars
    assert r["completion_rate"] == pytest.approx(r["trips_completed"] / n_cars)                # not-inserted cars count as not completed
    assert r["completion_rate"] < r["trips_completed"] / r["trips_departed"] if r["trips_completed"] else True
    assert r["unfinished_share"] == pytest.approx(r["trips_unfinished"] / r["trips_departed"])  # the share is over inserted trips only


def _backlog_row(drain_max_s: int, n_cars: int = 70):
    body = "\n".join(f'<vehicle id="c{i}" type="passenger" route="route_top_east" depart="{PROTO.warmup_s + 5}"/>' for i in range(n_cars))
    p = EvalProtocol(warmup_s=30, measure_s=150, n_seeds=1, drain_max_s=drain_max_s, mode="smoke")
    env = TrafficSignalEnv(EnvConfig(horizon_s=p.horizon_s, demand_end_s=p.demand_end_s), route_factory=_custom_routes(body))
    try:
        return runner.run_episode(env, FixedTimeController(), eval_seeds(1, "smoke")[0], p)["row"]
    finally:
        env.close()


def test_with_a_long_enough_drain_the_same_backlog_is_inserted_and_finishes():
    short, long_ = _backlog_row(0), _backlog_row(600)
    assert short["trips_not_inserted"] > 0
    assert long_["trips_scheduled"] == short["trips_scheduled"] == 70 and long_["trips_not_inserted"] == 0 and long_["trips_departed"] == 70
    assert long_["drain_exhausted"] == 0 and long_["completion_rate"] == 1.0
    assert long_["departed_after_window"] == short["trips_not_inserted"]                        # the same cars, inserted late, stay in the cohort
