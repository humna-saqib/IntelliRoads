"""
IntelliRoads - Emergency Vehicle Priority validation.

Runs a deterministic scenario (one guaranteed ambulance, light background
traffic - see app/sumo_tools/route_generator.py:generate_emergency_validation_routefile)
and confirms the full priority-override flow actually happens end to end:

    detection -> signal override (forced GREEN) -> vehicle clears ->
    override deactivates -> normal control resumes

This exercises the real EmergencyVehicleDetector and EmergencyPriorityController
services exactly as main.py's live loop does - not a mock or simulation of
the logic, the actual production code.

By default runs against the rule-based SignalController only, since the
override is applied as a layer *after* whichever controller (rule-based or
DQN) produces its normal decision - see priority_controller.py's module
docstring. Pass --use-dqn to additionally validate the same flow with the
DQN controller active, to directly evidence that the override holds
regardless of which controller is running (relevant since DQN is now the
live default - see main.py).

Usage:
    python validate_emergency_priority.py
    python validate_emergency_priority.py --use-dqn
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_BACKEND_DIR))

# Headless by default - same fix as main.py/train_dqn.py. This script is
# standalone (not launched through either of those), so it needs its own
# copy of this setdefault or it silently inherits traci_session.py's
# GUI-preferring default and fails in any headless environment.
os.environ.setdefault("SUMO_USE_GUI", "false")

from app.core.database import DB_PATH  # noqa: E402 (path setup above must run first)
from app.services.congestion_detector import CongestionDetector  # noqa: E402
from app.services.density_calculator import DensityCalculator  # noqa: E402
from app.services.emergency_detector import EmergencyVehicleDetector  # noqa: E402
from app.services.priority_controller import EmergencyPriorityController  # noqa: E402
from app.services.signal_controller import SignalController  # noqa: E402
from app.services.traci_session import TraCISession  # noqa: E402
from app.services.vehicle_data_service import VehicleDataService  # noqa: E402
from app.sumo_tools.route_generator import generate_emergency_validation_routefile  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

ROUTE_FILE_PATH = _BACKEND_DIR / "sumo" / "routes" / "intelliroads.rou.xml"
SUMO_CONFIG_PATH = _BACKEND_DIR / "sumo" / "config" / "intelliroads.sumocfg"
RESULTS_DIR = _BACKEND_DIR / "validation_results"
STEPS = 250  # ambulance alone takes ~172s to clear its route (confirmed via
             # a direct SUMO test); this gives margin for detection, the
             # override, clearing, and resumption to all be observed


def run_validation(use_dqn: bool = False) -> Dict[str, Any]:
    controller_label = "DQN" if use_dqn else "Rule-Based"
    print(f"\n{'='*70}\n  EV Priority Validation - {controller_label} controller\n{'='*70}\n")

    generate_emergency_validation_routefile(output_path=ROUTE_FILE_PATH)
    print(f"Generated deterministic validation scenario at {ROUTE_FILE_PATH}")

    session = TraCISession(config_path=SUMO_CONFIG_PATH, step_length=1.0)
    session.start()

    density_calculator = DensityCalculator()
    congestion_detector = CongestionDetector()
    data_service = VehicleDataService(session)
    emergency_detector = EmergencyVehicleDetector()
    priority_controller = EmergencyPriorityController()

    if use_dqn:
        # Imported lazily: only needed for --use-dqn, and this is the one
        # import path that needs torch + a trained checkpoint present.
        from app.agent.dqn_agent import DEFAULT_MODEL_PATH, DQNAgent
        from app.controllers.dqn_controller import ControllerMode, DQNController
        from app.environment.sumo_environment import SUMOEnvironment

        rule_based_controller = SignalController(session)
        sumo_env = SUMOEnvironment(session=session)
        dqn_agent = DQNAgent()
        if DEFAULT_MODEL_PATH.exists():
            dqn_agent.load(DEFAULT_MODEL_PATH)
            print(f"Loaded trained DQN checkpoint from {DEFAULT_MODEL_PATH}")
        else:
            print(f"WARNING: no checkpoint at {DEFAULT_MODEL_PATH} - using untrained weights")
        signal_controller = DQNController(
            session=session,
            environment=sumo_env,
            agent=dqn_agent,
            rule_based_controller=rule_based_controller,
            mode=ControllerMode.DQN,
        )
    else:
        signal_controller = SignalController(session)

    timeline: List[Dict[str, Any]] = []
    all_emergency_events: List[Dict[str, Any]] = []
    all_priority_events: List[Dict[str, Any]] = []

    try:
        for step in range(STEPS):
            session.step()
            sim_time = float(step)

            vehicles = data_service.collect_all()
            density_response = density_calculator.calculate_all_densities(vehicles)
            congestion_detector.detect(density_response)

            if use_dqn:
                normal_signals = signal_controller.control_step(
                    density_response=density_response, vehicles=vehicles, occupancy_response=None,
                )
            else:
                signal_controller.update_all_signals(density_response)
                normal_signals = signal_controller.get_current_signals()

            active_vehicles, emergency_events = emergency_detector.detect(vehicles, sim_time)
            final_signals, priority_events = priority_controller.resolve_signals(
                normal_signals=normal_signals,
                active_emergency_vehicles=active_vehicles,
                density_response=density_response,
                sim_time=sim_time,
            )

            for ev in emergency_events:
                record = {"sim_time": sim_time, "event_type": ev.event_type,
                          "vehicle_id": ev.vehicle_id, "junction_id": ev.junction_id}
                all_emergency_events.append(record)
                print(f"  [t={sim_time:5.0f}s] EMERGENCY {ev.event_type:<20} "
                      f"vehicle={ev.vehicle_id} junction={ev.junction_id}")

            for ev in priority_events:
                record = {"sim_time": sim_time, "event_type": ev.event_type,
                          "junction_id": ev.junction_id, "vehicle_id": ev.vehicle_id}
                all_priority_events.append(record)
                print(f"  [t={sim_time:5.0f}s] PRIORITY  {ev.event_type:<20} "
                      f"junction={ev.junction_id} vehicle={ev.vehicle_id}")

            junction_a_signal = next((s for s in final_signals if s.junction_id == "junctionA"), None)
            if junction_a_signal is not None:
                timeline.append({
                    "sim_time": sim_time,
                    "junctionA_phase": str(junction_a_signal.phase),
                    "junctionA_duration": junction_a_signal.duration_seconds,
                    "junctionA_priority_override": junction_a_signal.priority_override,
                })
    finally:
        session.close()

    # ---- Verdict ----------------------------------------------------------
    detected = any(e["event_type"] == "DETECTED" for e in all_emergency_events)
    activated = [e for e in all_priority_events if e["event_type"] == "ACTIVATED"]
    deactivated = [e for e in all_priority_events if e["event_type"] == "DEACTIVATED"]
    cleared = any(e["event_type"] == "CLEARED" for e in all_emergency_events)

    forced_green_ticks = [t for t in timeline if t["junctionA_priority_override"]]
    resumed_normal_ticks = [
        t for t in timeline
        if not t["junctionA_priority_override"]
        and deactivated
        and t["sim_time"] > deactivated[0]["sim_time"]
    ]

    checks = {
        "1_detection_occurred": detected,
        "2_override_activated_with_forced_green": bool(activated) and bool(forced_green_ticks),
        "3_vehicle_cleared_and_override_deactivated": cleared and bool(deactivated),
        "4_normal_control_resumed_after": bool(resumed_normal_ticks),
    }
    all_passed = all(checks.values())

    print(f"\n{'-'*70}\n  Verdict ({controller_label})\n{'-'*70}")
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print(f"\n  OVERALL: {'PASS' if all_passed else 'FAIL'}\n")

    return {
        "controller": controller_label,
        "checks": checks,
        "all_passed": all_passed,
        "emergency_events": all_emergency_events,
        "priority_events": all_priority_events,
        "junctionA_timeline": timeline,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate emergency vehicle priority override")
    parser.add_argument("--use-dqn", action="store_true",
                         help="Also validate with the DQN controller active (needs a trained checkpoint)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = [run_validation(use_dqn=False)]
    if args.use_dqn:
        results.append(run_validation(use_dqn=True))

    out_path = RESULTS_DIR / "ev_priority_validation.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nFull evidence written to {out_path}")

    if not all(r["all_passed"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
