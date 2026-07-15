"""
IntelliRoads – Vehicle data collection service.

Reads vehicle state from a live TraCI session or generates realistic
mock data when SUMO is unavailable.
"""

from __future__ import annotations

import random
import time
from typing import List

from app.models.vehicle import VehicleData, VehicleType
from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger

if SUMO_AVAILABLE:
    import traci  # type: ignore

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Mapping from SUMO vehicle-type string to our VehicleType enum
# ---------------------------------------------------------------------------
_TYPE_MAP: dict[str, VehicleType] = {
    "passenger": VehicleType.CAR,
    "car": VehicleType.CAR,
    "private": VehicleType.CAR,
    "motorcycle": VehicleType.MOTORCYCLE,
    "moped": VehicleType.MOTORCYCLE,
    "bicycle": VehicleType.MOTORCYCLE,
    "bus": VehicleType.BUS,
    "coach": VehicleType.BUS,
    "truck": VehicleType.TRUCK,
    "trailer": VehicleType.TRUCK,
    "delivery": VehicleType.TRUCK,
}

# ---------------------------------------------------------------------------
# Mock configuration
# ---------------------------------------------------------------------------
_MOCK_LANES = ["lane_A_0", "lane_B_0", "lane_C_0", "lane_D_0"]
_MOCK_ROADS = ["road_A", "road_B", "road_C", "road_D"]
_MOCK_TYPES = list(VehicleType)


def _mock_vehicle_type() -> VehicleType:
    """Return a weighted random vehicle type (cars most common)."""
    return random.choices(
        [VehicleType.CAR, VehicleType.MOTORCYCLE, VehicleType.BUS, VehicleType.TRUCK],
        weights=[65, 15, 10, 10],
        k=1,
    )[0]


class VehicleDataService:
    """
    Collects vehicle state from TraCI or produces synthetic mock data.

    Parameters
    ----------
    session : TraCISession
        An initialised (started) TraCI session.
    """

    def __init__(self, session: TraCISession) -> None:
        self._session = session
        logger.info("VehicleDataService initialised.")

    @property
    def mock_mode(self) -> bool:
        """Dynamically check if we should run in mock mode."""
        return self._session.mock_mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_all(self) -> List[VehicleData]:
        """
        Collect data for every vehicle currently in the simulation.

        Returns
        -------
        List[VehicleData]
            Snapshot list ordered by vehicle_id.
        """
        if self.mock_mode:
            return self._generate_mock_vehicles()

        return self._collect_from_traci()

    def collect_for_junction(self, junction_id: str) -> List[VehicleData]:
        """
        Return vehicles on lanes that are adjacent to *junction_id*.

        In live mode this filters by lane prefix; in mock mode it
        returns vehicles whose lane_id contains the junction letter.

        Parameters
        ----------
        junction_id : str
            Identifier of the target junction (e.g. ``'A'``).

        Returns
        -------
        List[VehicleData]
        """
        all_vehicles = self.collect_all()
        return [
            v
            for v in all_vehicles
            if junction_id.lower() in v.lane_id.lower()
            or junction_id.lower() in v.road_id.lower()
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_from_traci(self) -> List[VehicleData]:
        """Fetch live vehicle data via the TraCI API."""
        vehicles: List[VehicleData] = []
        try:
            vehicle_ids: list[str] = traci.vehicle.getIDList()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"TraCI getIDList() failed: {exc}")
            return vehicles

        ts = time.time()
        for vid in vehicle_ids:
            try:
                speed: float = traci.vehicle.getSpeed(vid)
                lane_id: str = traci.vehicle.getLaneID(vid)
                pos: tuple[float, float] = traci.vehicle.getPosition(vid)
                type_id: str = traci.vehicle.getTypeID(vid).lower()
                road_id: str = traci.vehicle.getRoadID(vid)

                v_type = _TYPE_MAP.get(type_id, VehicleType.UNKNOWN)

                vehicles.append(
                    VehicleData(
                        vehicle_id=vid,
                        speed=speed,
                        lane_id=lane_id,
                        position_x=pos[0],
                        position_y=pos[1],
                        vehicle_type=v_type,
                        road_id=road_id,
                        timestamp=ts,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Could not read vehicle '{vid}': {exc}")

        logger.debug(f"Collected {len(vehicles)} vehicles from TraCI.")
        return vehicles

    def _generate_mock_vehicles(self) -> List[VehicleData]:
        """
        Generate 10-50 synthetic vehicles spread across 4 lanes.

        Each vehicle gets:
        - A deterministic but slightly varying position to simulate movement
        - A realistic speed (0–16 m/s)
        - A weighted random vehicle type
        """
        sim_time = self._session.get_simulation_time()
        count = random.randint(10, 50)
        vehicles: List[VehicleData] = []
        ts = time.time()

        for i in range(count):
            lane_index = i % len(_MOCK_LANES)
            lane_id = _MOCK_LANES[lane_index]
            road_id = _MOCK_ROADS[lane_index]

            # Speed between 0 and 16 m/s, slightly correlated with sim time
            speed = max(0.0, random.gauss(8.0, 4.0))
            speed = min(speed, 16.0)

            pos_x = random.uniform(0.0, 500.0)
            pos_y = random.uniform(0.0, 500.0)

            vehicles.append(
                VehicleData(
                    vehicle_id=f"veh_{i:04d}",
                    speed=round(speed, 2),
                    lane_id=lane_id,
                    position_x=round(pos_x, 2),
                    position_y=round(pos_y, 2),
                    vehicle_type=_mock_vehicle_type(),
                    road_id=road_id,
                    timestamp=ts,
                )
            )

        logger.debug(
            f"Generated {len(vehicles)} mock vehicles at sim_time={sim_time:.1f}s"
        )
        return vehicles
