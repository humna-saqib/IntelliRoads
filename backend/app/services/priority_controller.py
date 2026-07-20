"""
IntelliRoads – Emergency Vehicle Priority Control service (Sprint 2).

A separate decision layer on top of SignalController, not a
modification of it. SignalController keeps computing pure density-based
timing every tick, completely unchanged; this controller takes that
output plus the set of active emergency vehicles and produces the
*final* signal list that the API/dashboard sees — substituting a
priority-GREEN timing for any junction with an active emergency
vehicle, and passing every other junction's normal decision through
untouched.

Because SignalController's own state and the normal signal_decisions
history are never mutated, both the original density-based decision
and the emergency override are always available: the normal decision
from SignalController.get_current_signals(), and the override activity
from this controller's own ACTIVATED/DEACTIVATED event stream. Restoring
normal operation needs no special-case logic — the instant a junction
stops having an active emergency vehicle, this controller simply stops
substituting its timing, and that tick's already-computed density-based
decision is what gets returned.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from app.models.density import DensityResponse
from app.models.emergency import EmergencyVehicleState, PriorityOverrideEvent
from app.models.signal import SignalPhaseType, SignalTiming
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Held GREEN duration when an emergency vehicle is present. Comfortably
# covers a full lane transit (~500-600m at typical speed = ~40-50s).
# Not a permanent constant — tune here as needed.
EMERGENCY_GREEN_DURATION: float = 90.0


class _OverrideState:
    """Tracks one junction's currently-active override, for ACTIVATED/DEACTIVATED detection."""

    __slots__ = ("vehicle_id", "vehicle_type", "normal_duration")

    def __init__(self, vehicle_id: str, vehicle_type: str, normal_duration: Optional[float]) -> None:
        self.vehicle_id = vehicle_id
        self.vehicle_type = vehicle_type
        self.normal_duration = normal_duration


class EmergencyPriorityController:
    """
    Resolves the final per-tick signal list, substituting priority GREEN
    timing for junctions with an active emergency vehicle.
    """

    def __init__(self) -> None:
        self._active_overrides: Dict[str, _OverrideState] = {}
        logger.info(
            f"EmergencyPriorityController initialised "
            f"(EMERGENCY_GREEN_DURATION={EMERGENCY_GREEN_DURATION}s)."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_signals(
        self,
        normal_signals: List[SignalTiming],
        active_emergency_vehicles: List[EmergencyVehicleState],
        density_response: DensityResponse,
        sim_time: float,
    ) -> Tuple[List[SignalTiming], List[PriorityOverrideEvent]]:
        """
        Given this tick's pure density-based decisions and the currently
        active emergency vehicles, return the final signal list (with
        overrides substituted in) and any activation/deactivation events.

        Parameters
        ----------
        normal_signals : List[SignalTiming]
            SignalController.get_current_signals() output for this tick —
            never mutated by this method.
        active_emergency_vehicles : List[EmergencyVehicleState]
            Currently active emergency vehicles (EmergencyVehicleDetector).
        density_response : DensityResponse
            This tick's density snapshot, used only to attach a density
            level to override records for context — not decision-driving.
        sim_time : float
            Current simulation time, for event records.

        Returns
        -------
        tuple[List[SignalTiming], List[PriorityOverrideEvent]]
        """
        now = time.time()
        events: List[PriorityOverrideEvent] = []

        # One active vehicle per junction max; first one wins if several
        # happen to share a junction on the same tick.
        junction_to_vehicle: Dict[str, EmergencyVehicleState] = {}
        for vehicle in active_emergency_vehicles:
            if vehicle.junction_id and vehicle.junction_id not in junction_to_vehicle:
                junction_to_vehicle[vehicle.junction_id] = vehicle

        density_by_lane = {lane.lane_id: lane for lane in density_response.lanes}
        final_signals: List[SignalTiming] = []

        for timing in normal_signals:
            junction_id = timing.junction_id
            vehicle = junction_to_vehicle.get(junction_id)

            if vehicle is not None:
                if junction_id not in self._active_overrides:
                    # ACTIVATED – this junction wasn't overridden last tick.
                    self._active_overrides[junction_id] = _OverrideState(
                        vehicle_id=vehicle.vehicle_id,
                        vehicle_type=(
                            vehicle.vehicle_type if isinstance(vehicle.vehicle_type, str)
                            else vehicle.vehicle_type.value
                        ),
                        normal_duration=timing.duration_seconds,
                    )
                    events.append(
                        PriorityOverrideEvent(
                            junction_id=junction_id,
                            vehicle_id=vehicle.vehicle_id,
                            vehicle_type=vehicle.vehicle_type,
                            event_type="ACTIVATED",
                            normal_duration=timing.duration_seconds,
                            override_duration=EMERGENCY_GREEN_DURATION,
                            timestamp=now,
                            sim_time=sim_time,
                        )
                    )
                    logger.warning(
                        f"PRIORITY ACTIVATED: junction '{junction_id}' forced GREEN "
                        f"for {EMERGENCY_GREEN_DURATION}s (vehicle={vehicle.vehicle_id}, "
                        f"type={vehicle.vehicle_type}); normal decision "
                        f"({timing.duration_seconds}s) suspended."
                    )

                lane_density = density_by_lane.get(vehicle.lane_id)
                density_level = lane_density.level if lane_density else timing.density_level

                final_signals.append(
                    SignalTiming(
                        junction_id=junction_id,
                        phase=SignalPhaseType.GREEN,
                        duration_seconds=EMERGENCY_GREEN_DURATION,
                        density_level=density_level,
                        triggered_at=now,
                        reason=(
                            f"Emergency priority override for {vehicle.vehicle_type} "
                            f"'{vehicle.vehicle_id}'"
                        ),
                        priority_override=True,
                        emergency_vehicle_id=vehicle.vehicle_id,
                        emergency_vehicle_type=(
                            vehicle.vehicle_type if isinstance(vehicle.vehicle_type, str)
                            else vehicle.vehicle_type.value
                        ),
                    )
                )
            else:
                if junction_id in self._active_overrides:
                    # DEACTIVATED – vehicle no longer here; automatically
                    # fall back to this tick's normal density-based decision.
                    prior = self._active_overrides.pop(junction_id)
                    events.append(
                        PriorityOverrideEvent(
                            junction_id=junction_id,
                            vehicle_id=prior.vehicle_id,
                            vehicle_type=prior.vehicle_type,
                            event_type="DEACTIVATED",
                            normal_duration=timing.duration_seconds,
                            override_duration=EMERGENCY_GREEN_DURATION,
                            timestamp=now,
                            sim_time=sim_time,
                        )
                    )
                    logger.info(
                        f"PRIORITY DEACTIVATED: junction '{junction_id}' restored to "
                        f"normal density-based control ({timing.duration_seconds}s)."
                    )

                final_signals.append(timing)  # normal decision, untouched

        return final_signals, events
