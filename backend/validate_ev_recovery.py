"""
IntelliRoads - Emergency Vehicle Recovery-Time Comparison (DQN vs Rule-Based)

Addresses the supervisor question this script exists to answer: when an
emergency vehicle triggers a priority override and the override then ends,
how does that affect the OTHER traffic in the network (e.g. in recovery
time), and is DQN faster than Rule-Based at recovering?

Nothing like this existed before this script. The only prior EV-related
validation (validation_results/EV_PRIORITY_VALIDATION_SUMMARY.md) is a
pass/fail mechanical check - "did the override activate and deactivate
correctly" - for Rule-Based only, never run for DQN, and it does not
measure any impact on other traffic or compare the two controllers.

Methodology
-----------
Runs the exact same deterministic emergency scenario
(app.sumo_tools.route_generator.generate_emergency_validation_routefile:
one ambulance on route_top_east through junctionA, sparse fixed-period
background traffic - not the exp() form, so this scenario is unaffected
by the traffic-density bug fixed elsewhere in this project) twice - once
with the live controller in RULE_BASED mode, once in DQN mode
(epsilon=0.0, pure greedy, for reproducibility) - using the exact same
production code path as the live app: DQNController + SignalController +
EmergencyVehicleDetector + EmergencyPriorityController, wired together
identically to app/main.py's control loop. Both runs are fully
deterministic (no randomness anywhere in the scenario), so a single run
per controller is sufficient - there is no random variation to average
over, unlike evaluate_controllers.py's randomized-traffic episodes.

For junctionB, junctionC, and junctionD - the three junctions NOT holding
the override, i.e. the "other traffic" the supervisor's question is
about - this script records average waiting time and queue length (same
TraCI metrics and same per-junction primary-lane mapping as
evaluate_controllers.py, imported directly from there for consistency)
every simulated second across the full run.

"Recovery time" is defined as: seconds from the override's DEACTIVATED
event at junctionA until the mean of {B, C, D}'s waiting time returns to
within RECOVERY_TOLERANCE of its own pre-event baseline AND stays within
that tolerance for RECOVERY_SUSTAIN_SECONDS consecutive seconds - the
sustain requirement exists so a single noisy dip isn't misread as full
recovery. Queue length recovery is computed the same way as a secondary
check.

Usage:
    python validate_ev_recovery.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

_BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_BACKEND_DIR))

# Reuse the exact same TraCI metric helpers and junction/lane mapping used
# throughout the rest of the evaluation, rather than redefining them here.
from evaluate_controllers import (  # noqa: E402
    _collect_junction_metrics,
    make_session,
)

from app.agent.dqn_agent import DEFAULT_MODEL_PATH, DQNAgent  # noqa: E402
from app.controllers.dqn_controller import ControllerMode, DQNController  # noqa: E402
from app.core.threshold_config import threshold_config_service  # noqa: E402
from app.environment.sumo_environment import SUMOEnvironment  # noqa: E402
from app.services.density_calculator import DensityCalculator  # noqa: E402
from app.services.emergency_detector import EmergencyVehicleDetector  # noqa: E402
from app.services.occupancy_calculator import OccupancyCalculator  # noqa: E402
from app.services.priority_controller import EmergencyPriorityController  # noqa: E402
from app.services.signal_controller import SignalController  # noqa: E402
from app.services.vehicle_data_service import VehicleDataService  # noqa: E402
from app.sumo_tools.route_generator import generate_emergency_validation_routefile  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

OTHER_JUNCTIONS: List[str] = ["junctionB", "junctionC", "junctionD"]
OVERRIDE_JUNCTION = "junctionA"

# Delayed vs the function's own default (5.0s) so there's a real settled
# baseline window before the ambulance triggers anything - the network
# needs a little time to populate from empty.
AMBULANCE_DEPART: float = 30.0
DURATION: int = 400

# Baseline window: skip the first 10s (still emptying in), use the rest
# of the pre-ambulance period as the "normal" reference level.
BASELINE_START: float = 10.0
BASELINE_END: float = AMBULANCE_DEPART

RECOVERY_TOLERANCE: float = 0.15          # within 15% of baseline counts as "recovered"
RECOVERY_SUSTAIN_SECONDS: int = 5         # must hold for this many consecutive seconds
WAIT_ABSOLUTE_FLOOR: float = 0.5          # seconds - floor for near-zero baselines
QUEUE_ABSOLUTE_FLOOR: float = 0.5         # vehicles - floor for near-zero baselines

RESULTS_DIR = _BACKEND_DIR / "validation_results"
ROUTE_FILE_PATH = _BACKEND_DIR / "sumo" / "routes" / "intelliroads.rou.xml"


def _find_recovery_time(
    series: List[tuple[float, float]],
    baseline: float,
    override_end: float,
    tolerance: float,
    sustain_seconds: int,
    absolute_floor: float,
) -> Optional[float]:
    """
    series: list of (sim_time, value) pairs, in time order.
    Returns seconds from override_end to sustained recovery, or None if
    the series never recovers within the observed window.

    Tolerance band is max(baseline * tolerance, absolute_floor) on each
    side - a pure percentage band breaks down when baseline is at or
    near zero (common here: the validation scenario's background
    traffic is deliberately sparse, so junctions B/C/D can have a
    genuinely ~0s baseline wait). absolute_floor keeps the check
    meaningful in that case instead of requiring an exact 0.0 match.
    """
    band = max(baseline * tolerance, absolute_floor)
    lo, hi = baseline - band, baseline + band

    post = [(t, v) for t, v in series if t >= override_end]
    consecutive = 0
    for t, v in post:
        if lo <= v <= hi:
            consecutive += 1
            if consecutive >= sustain_seconds:
                recovered_at = t - (sustain_seconds - 1)
                return round(recovered_at - override_end, 1)
        else:
            consecutive = 0
    return None  # never sustained recovery within the run


def run_scenario(mode: ControllerMode) -> Dict:
    """Run the deterministic EV scenario once under the given controller mode."""
    mode_label = mode.value
    logger.info(f"=== Running EV recovery scenario: mode={mode_label} ===")

    generate_emergency_validation_routefile(
        output_path=ROUTE_FILE_PATH,
        ambulance_depart=AMBULANCE_DEPART,
        duration=DURATION,
    )

    session = make_session()
    try:
        data_service = VehicleDataService(session)
        density_calculator = DensityCalculator(threshold_config=threshold_config_service)
        signal_controller = SignalController(session)
        emergency_detector = EmergencyVehicleDetector()
        priority_controller = EmergencyPriorityController()
        occupancy_calculator = OccupancyCalculator(session)

        sumo_env = SUMOEnvironment(session)
        dqn_agent = DQNAgent()
        if DEFAULT_MODEL_PATH.exists():
            dqn_agent.load(DEFAULT_MODEL_PATH)
        dqn_controller = DQNController(
            session=session,
            environment=sumo_env,
            agent=dqn_agent,
            rule_based_controller=signal_controller,
            mode=mode,
        )

        # {junction_id: [(sim_time, avg_wait), ...]}
        wait_series: Dict[str, List[tuple[float, float]]] = {j: [] for j in OTHER_JUNCTIONS}
        queue_series: Dict[str, List[tuple[float, float]]] = {j: [] for j in OTHER_JUNCTIONS}
        override_activated_at: Optional[float] = None
        override_deactivated_at: Optional[float] = None

        for _ in range(DURATION):
            sim_time = session.step()
            vehicles = data_service.collect_all()
            active_emergency, _emergency_events = emergency_detector.detect(vehicles, sim_time)
            density_response = density_calculator.calculate_all_densities(vehicles)
            occupancy_response = occupancy_calculator.calculate_all(vehicles)

            normal_signals = dqn_controller.control_step(
                density_response=density_response,
                vehicles=vehicles,
                occupancy_response=occupancy_response,
                throughput=1,
                epsilon=0.0,  # pure greedy - deterministic, matches evaluate_controllers.py
            )

            _final_signals, priority_events = priority_controller.resolve_signals(
                normal_signals=normal_signals,
                active_emergency_vehicles=active_emergency,
                density_response=density_response,
                sim_time=sim_time,
            )

            for ev in priority_events:
                if ev.junction_id == OVERRIDE_JUNCTION:
                    if ev.event_type == "ACTIVATED" and override_activated_at is None:
                        override_activated_at = ev.sim_time
                    elif ev.event_type == "DEACTIVATED":
                        override_deactivated_at = ev.sim_time

            for jid in OTHER_JUNCTIONS:
                m = _collect_junction_metrics(jid)
                wait_series[jid].append((sim_time, m["avg_wait"]))
                queue_series[jid].append((sim_time, m["queue_len"]))

        if override_deactivated_at is None:
            logger.warning(
                f"[{mode_label}] Override never deactivated within the "
                f"{DURATION}s run - ambulance may not have cleared. "
                f"Cannot compute recovery time for this run."
            )

    finally:
        session.close()

    def _combined(series_by_junction: Dict[str, List[tuple[float, float]]]) -> List[tuple[float, float]]:
        """Mean across the three junctions at each timestep."""
        times = [t for t, _ in series_by_junction[OTHER_JUNCTIONS[0]]]
        combined = []
        for i, t in enumerate(times):
            vals = [series_by_junction[j][i][1] for j in OTHER_JUNCTIONS]
            combined.append((t, statistics.mean(vals)))
        return combined

    combined_wait = _combined(wait_series)
    combined_queue = _combined(queue_series)

    baseline_wait_vals = [v for t, v in combined_wait if BASELINE_START <= t < BASELINE_END]
    baseline_queue_vals = [v for t, v in combined_queue if BASELINE_START <= t < BASELINE_END]
    baseline_wait = statistics.mean(baseline_wait_vals) if baseline_wait_vals else 0.0
    baseline_queue = statistics.mean(baseline_queue_vals) if baseline_queue_vals else 0.0

    recovery_wait = recovery_queue = None
    if override_deactivated_at is not None:
        recovery_wait = _find_recovery_time(
            combined_wait, baseline_wait, override_deactivated_at,
            RECOVERY_TOLERANCE, RECOVERY_SUSTAIN_SECONDS, WAIT_ABSOLUTE_FLOOR,
        )
        recovery_queue = _find_recovery_time(
            combined_queue, baseline_queue, override_deactivated_at,
            RECOVERY_TOLERANCE, RECOVERY_SUSTAIN_SECONDS, QUEUE_ABSOLUTE_FLOOR,
        )

    # Peak disruption during the override window, for context alongside
    # the recovery time itself.
    during = [
        v for t, v in combined_wait
        if override_activated_at is not None
        and override_deactivated_at is not None
        and override_activated_at <= t <= override_deactivated_at
    ]
    peak_wait_during_override = max(during) if during else None

    return {
        "mode": mode_label,
        "override_activated_at": override_activated_at,
        "override_deactivated_at": override_deactivated_at,
        "override_duration_s": (
            round(override_deactivated_at - override_activated_at, 1)
            if override_activated_at is not None and override_deactivated_at is not None
            else None
        ),
        "baseline_avg_wait_s": round(baseline_wait, 3),
        "baseline_avg_queue_veh": round(baseline_queue, 3),
        "peak_avg_wait_during_override_s": (
            round(peak_wait_during_override, 3) if peak_wait_during_override is not None else None
        ),
        "recovery_time_wait_s": recovery_wait,
        "recovery_time_queue_s": recovery_queue,
        "recovery_tolerance": RECOVERY_TOLERANCE,
        "recovery_sustain_seconds": RECOVERY_SUSTAIN_SECONDS,
        "wait_series": combined_wait,
        "queue_series": combined_queue,
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    for mode in (ControllerMode.RULE_BASED, ControllerMode.DQN):
        results[mode.value] = run_scenario(mode)

    out_path = RESULTS_DIR / "ev_recovery_comparison.json"
    # Time series are large and are for optional deeper inspection /
    # plotting later - write them to a separate file so the summary JSON
    # stays small and easy to read directly.
    series_path = RESULTS_DIR / "ev_recovery_series.json"
    summary = {}
    series_out = {}
    for mode_label, r in results.items():
        series_out[mode_label] = {
            "wait_series": r.pop("wait_series"),
            "queue_series": r.pop("queue_series"),
        }
        summary[mode_label] = r

    out_path.write_text(json.dumps(summary, indent=2))
    series_path.write_text(json.dumps(series_out, indent=2))

    print("\n" + "=" * 78)
    print("  EV Priority Override - Recovery Time Comparison (DQN vs Rule-Based)")
    print("=" * 78)
    for mode_label, r in summary.items():
        print(f"\n{mode_label}:")
        print(f"  Override active:            {r['override_activated_at']}s -> {r['override_deactivated_at']}s "
              f"({r['override_duration_s']}s duration)")
        print(f"  Baseline avg wait (B/C/D):  {r['baseline_avg_wait_s']}s")
        print(f"  Peak avg wait during override: {r['peak_avg_wait_during_override_s']}s")
        print(f"  Recovery time (wait):       {r['recovery_time_wait_s']}s after override ended")
        print(f"  Recovery time (queue):      {r['recovery_time_queue_s']}s after override ended")

    rb = summary.get("rule_based", {})
    dqn = summary.get("dqn", {})
    rb_rt, dqn_rt = rb.get("recovery_time_wait_s"), dqn.get("recovery_time_wait_s")
    print("\n" + "-" * 78)
    if rb_rt is not None and dqn_rt is not None:
        faster = "DQN" if dqn_rt < rb_rt else ("Rule-Based" if rb_rt < dqn_rt else "Tied")
        print(f"  Faster to recover (waiting time): {faster}  (DQN={dqn_rt}s, Rule-Based={rb_rt}s)")
    else:
        print("  Could not compare - recovery time undefined for at least one controller "
              "(see warnings above; the run may need a longer DURATION).")
    print("=" * 78)
    print(f"\nSummary written -> {out_path}")
    print(f"Full time series written -> {series_path}")


if __name__ == "__main__":
    main()
