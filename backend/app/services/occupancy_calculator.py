"""
IntelliRoads – Lane Occupancy Calculator service (Sprint 2).

Computes real occupancy percentage per monitored lane every tick.

Live mode uses TraCI's own ``getLastStepOccupancy()`` — the authoritative
value SUMO itself computes from actual vehicle length + minGap footprint
on the lane, not a hand-rolled approximation. Mock mode has no TraCI to
query, so it derives occupancy from vehicle count/type and lane length,
using the same real vehicle lengths defined in the route file and the
same real lane lengths DensityCalculator already uses.

Kept completely independent from signal control: this is purely
observational data collection for analytics and future RL state
features (Lane Occupancy Integration / DQN prep come later).
"""

from __future__ import annotations

import time
from typing import Dict, List

from app.models.density import DensityLevel
from app.models.occupancy import LaneOccupancy, OccupancyResponse
from app.models.vehicle import VehicleData, VehicleType
from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger

if SUMO_AVAILABLE:
    import traci  # type: ignore

logger = get_logger(__name__)

# Sprint 1/2 scope: the 4 monitored intersection lanes (matches
# DensityCalculator.LANE_LENGTHS and the real net.xml lane lengths).
_MONITORED_LANE_LENGTHS_M: Dict[str, float] = {
    "lane_A_0": 500.0,
    "lane_B_0": 600.0,
    "lane_C_0": 400.0,
    "lane_D_0": 500.0,
}

# Average vehicle length (m), used only for mock-mode occupancy estimation
# (no TraCI available to query real footprints). Matches the vType
# lengths defined in intelliroads.rou.xml.
_AVG_VEHICLE_LENGTH_M: Dict[VehicleType, float] = {
    VehicleType.CAR: 5.0,
    VehicleType.MOTORCYCLE: 2.0,
    VehicleType.BUS: 12.0,
    VehicleType.TRUCK: 15.0,
    VehicleType.UNKNOWN: 6.0,  # covers emergency vehicles in mock mode
}

# Occupancy-specific thresholds (distinct from DensityCalculator's
# 20/40 v/km thresholds — occupancy is a 0-100% scale of its own).
LOW_THRESHOLD: float = 30.0
HIGH_THRESHOLD: float = 60.0


class OccupancyCalculator:
    """
    Calculates lane occupancy percentage and qualitative level.

    Parameters
    ----------
    session : TraCISession
        An initialised TraCI session (may be in mock mode).
    """

    def __init__(self, session: TraCISession) -> None:
        self._session = session
        logger.info(
            f"OccupancyCalculator initialised "
            f"(thresholds: LOW<{LOW_THRESHOLD}%, HIGH>{HIGH_THRESHOLD}%)."
        )

    @property
    def mock_mode(self) -> bool:
        """Dynamically check if we should run in mock mode."""
        return self._session.mock_mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_all(self, vehicles: List[VehicleData]) -> OccupancyResponse:
        """
        Compute occupancy for every monitored lane this tick.

        Parameters
        ----------
        vehicles : List[VehicleData]
            Current vehicle snapshot (used only in mock mode; live mode
            queries TraCI directly).

        Returns
        -------
        OccupancyResponse
        """
        if self.mock_mode:
            lanes = self._calculate_mock(vehicles)
        else:
            lanes = self._calculate_live()

        avg = sum(l.occupancy_percent for l in lanes) / len(lanes) if lanes else 0.0
        return OccupancyResponse(
            lanes=lanes, average_occupancy=round(avg, 2), timestamp=time.time()
        )

    def get_level(self, occupancy_percent: float) -> DensityLevel:
        """Map a raw occupancy percentage to a qualitative band."""
        if occupancy_percent < LOW_THRESHOLD:
            return DensityLevel.LOW
        if occupancy_percent < HIGH_THRESHOLD:
            return DensityLevel.MEDIUM
        return DensityLevel.HIGH

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_live(self) -> List[LaneOccupancy]:
        """Fetch real occupancy via TraCI's getLastStepOccupancy()."""
        ts = time.time()
        lanes: List[LaneOccupancy] = []
        for lane_id in _MONITORED_LANE_LENGTHS_M:
            try:
                # Despite its docstring claiming "in %", getLastStepOccupancy()
                # empirically returns a 0-1 fraction (verified: 5 vehicles on a
                # 500m lane gave 0.086, matching ~7.5m occupied footprint per
                # vehicle / 500m = 0.075 — not a plausible "8.6%" reading).
                occ_percent = float(traci.lane.getLastStepOccupancy(lane_id)) * 100.0
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"getLastStepOccupancy() failed for '{lane_id}': {exc}")
                occ_percent = 0.0

            occ_percent = max(0.0, min(100.0, occ_percent))
            lanes.append(
                LaneOccupancy(
                    lane_id=lane_id,
                    occupancy_percent=round(occ_percent, 2),
                    occupancy_level=self.get_level(occ_percent),
                    timestamp=ts,
                )
            )
        return lanes

    def _calculate_mock(self, vehicles: List[VehicleData]) -> List[LaneOccupancy]:
        """Derive occupancy from vehicle count/type and lane length (no TraCI)."""
        ts = time.time()
        per_lane: Dict[str, List[VehicleData]] = {}
        for v in vehicles:
            if v.lane_id in _MONITORED_LANE_LENGTHS_M:
                per_lane.setdefault(v.lane_id, []).append(v)

        lanes: List[LaneOccupancy] = []
        for lane_id, lane_length_m in _MONITORED_LANE_LENGTHS_M.items():
            lane_vehicles = per_lane.get(lane_id, [])
            occupied_length_m = sum(
                _AVG_VEHICLE_LENGTH_M.get(v.vehicle_type, 5.0) for v in lane_vehicles
            )
            occ_percent = max(0.0, min(100.0, (occupied_length_m / lane_length_m) * 100.0))
            lanes.append(
                LaneOccupancy(
                    lane_id=lane_id,
                    occupancy_percent=round(occ_percent, 2),
                    occupancy_level=self.get_level(occ_percent),
                    timestamp=ts,
                )
            )
        return lanes
