"""
IntelliRoads – Emergency Vehicle Detector service (Sprint 2).

Identifies ambulances, police vehicles, and fire trucks from live (or
mock) vehicle telemetry each simulation tick, tracks which are
currently active, and emits events only on real state transitions
(first detected, changed intersection, or left the simulation) so
downstream consumers (DB logger, future Priority Control) never see
per-tick duplicates.

Detection uses TraCI's vClass ("emergency") as the primary signal,
with the vType id (ambulance/police/firetruck) distinguishing the
specific kind — SUMO has no separate vClass per emergency service.
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

from app.models.emergency import EmergencyEvent, EmergencyVehicleState, EmergencyVehicleType
from app.models.vehicle import VehicleData
from app.services.signal_controller import _LANE_TO_JUNCTION
from app.utils.logger import get_logger

logger = get_logger(__name__)

_EMERGENCY_VCLASS = "emergency"

_EMERGENCY_TYPE_MAP: Dict[str, EmergencyVehicleType] = {
    "ambulance": EmergencyVehicleType.AMBULANCE,
    "police": EmergencyVehicleType.POLICE,
    "firetruck": EmergencyVehicleType.FIRETRUCK,
    "fire_truck": EmergencyVehicleType.FIRETRUCK,
    "firebrigade": EmergencyVehicleType.FIRETRUCK,
}


def _classify_emergency_type(vehicle: VehicleData) -> EmergencyVehicleType | None:
    """Return the emergency vehicle kind, or None if not an emergency vehicle."""
    if vehicle.sumo_vclass.lower() != _EMERGENCY_VCLASS:
        return None
    return _EMERGENCY_TYPE_MAP.get(vehicle.sumo_type_id.lower(), EmergencyVehicleType.UNKNOWN)


class EmergencyVehicleDetector:
    """
    Detects emergency vehicles each tick and tracks active state.

    Designed to be called once per simulation tick with the same
    ``vehicles`` list already fetched by :class:`VehicleDataService` —
    no extra TraCI round-trip needed. The returned active-vehicle list
    is the extension point for Emergency Vehicle Priority Control
    (Sprint 2, next feature): that feature can inspect
    ``get_active()`` for any vehicle whose ``junction_id`` matches a
    controlled junction and override normal signal timing accordingly.
    """

    def __init__(self) -> None:
        self._active: Dict[str, EmergencyVehicleState] = {}
        logger.info("EmergencyVehicleDetector initialised.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self, vehicles: List[VehicleData], sim_time: float
    ) -> Tuple[List[EmergencyVehicleState], List[EmergencyEvent]]:
        """
        Scan *vehicles* for emergency vehicles and update active state.

        Returns
        -------
        tuple[list[EmergencyVehicleState], list[EmergencyEvent]]
            The current active emergency vehicles, and any events
            (DETECTED / INTERSECTION_CHANGE / CLEARED) produced this tick.
        """
        now = time.time()
        events: List[EmergencyEvent] = []
        seen_ids: set[str] = set()

        for vehicle in vehicles:
            ev_type = _classify_emergency_type(vehicle)
            if ev_type is None:
                continue

            seen_ids.add(vehicle.vehicle_id)
            junction_id = _LANE_TO_JUNCTION.get(vehicle.lane_id)
            existing = self._active.get(vehicle.vehicle_id)

            if existing is None:
                state = EmergencyVehicleState(
                    vehicle_id=vehicle.vehicle_id,
                    vehicle_type=ev_type,
                    lane_id=vehicle.lane_id,
                    junction_id=junction_id,
                    speed=vehicle.speed,
                    first_detected_at=now,
                    last_seen_at=now,
                    sim_time=sim_time,
                )
                self._active[vehicle.vehicle_id] = state
                events.append(
                    EmergencyEvent(
                        vehicle_id=vehicle.vehicle_id,
                        vehicle_type=ev_type,
                        lane_id=vehicle.lane_id,
                        junction_id=junction_id,
                        event_type="DETECTED",
                        timestamp=now,
                        sim_time=sim_time,
                    )
                )
                logger.warning(
                    f"Emergency vehicle DETECTED: {vehicle.vehicle_id} "
                    f"({ev_type.value if hasattr(ev_type, 'value') else ev_type}) "
                    f"on {vehicle.lane_id} (junction={junction_id or 'unknown'})"
                )
            else:
                intersection_changed = existing.junction_id != junction_id
                self._active[vehicle.vehicle_id] = existing.model_copy(
                    update={
                        "lane_id": vehicle.lane_id,
                        "junction_id": junction_id,
                        "speed": vehicle.speed,
                        "last_seen_at": now,
                        "sim_time": sim_time,
                    }
                )
                if intersection_changed:
                    events.append(
                        EmergencyEvent(
                            vehicle_id=vehicle.vehicle_id,
                            vehicle_type=ev_type,
                            lane_id=vehicle.lane_id,
                            junction_id=junction_id,
                            event_type="INTERSECTION_CHANGE",
                            timestamp=now,
                            sim_time=sim_time,
                        )
                    )
                    logger.info(
                        f"Emergency vehicle {vehicle.vehicle_id} changed intersection: "
                        f"{existing.junction_id or 'unknown'} -> {junction_id or 'unknown'}"
                    )

        # Vehicles previously active but no longer present have left the simulation.
        gone_ids = set(self._active.keys()) - seen_ids
        for vid in gone_ids:
            state = self._active.pop(vid)
            events.append(
                EmergencyEvent(
                    vehicle_id=vid,
                    vehicle_type=state.vehicle_type,
                    lane_id=state.lane_id,
                    junction_id=state.junction_id,
                    event_type="CLEARED",
                    timestamp=now,
                    sim_time=sim_time,
                )
            )
            logger.info(f"Emergency vehicle CLEARED: {vid} (left simulation).")

        return list(self._active.values()), events

    def get_active(self) -> List[EmergencyVehicleState]:
        """Return the currently active emergency vehicles without re-scanning."""
        return list(self._active.values())
