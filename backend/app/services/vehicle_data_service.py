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
    "ambulance": VehicleType.EMERGENCY,
    "police": VehicleType.EMERGENCY,
    "firetruck": VehicleType.EMERGENCY,
}

# ---------------------------------------------------------------------------
# VDC-03: TraCI fetch must complete within this budget per simulation step
# ---------------------------------------------------------------------------
_FETCH_LATENCY_BUDGET_MS: float = 200.0

# ---------------------------------------------------------------------------
# Mock configuration
# ---------------------------------------------------------------------------
_MOCK_LANES = [
    "lane_A_west_in", "lane_A_north_in", "lane_AB_west", "lane_AD_north",
    "lane_AB_east", "lane_B_north_in", "lane_B_east_in", "lane_BC_north",
    "lane_CD_east", "lane_BC_south", "lane_C_east_in", "lane_C_south_in",
    "lane_D_west_in", "lane_AD_south", "lane_CD_west", "lane_D_south_in"
]
_MOCK_ROADS = [
    "edge_A_west_in", "edge_A_north_in", "edge_AB_west", "edge_AD_north",
    "edge_AB_east", "edge_B_north_in", "edge_B_east_in", "edge_BC_north",
    "edge_CD_east", "edge_BC_south", "edge_C_east_in", "edge_C_south_in",
    "edge_D_west_in", "edge_AD_south", "edge_CD_west", "edge_D_south_in"
]
_MOCK_LANE_LENGTHS_M = {
    "lane_A_west_in": 300.0,
    "lane_A_north_in": 300.0,
    "lane_AB_west": 400.0,
    "lane_AD_north": 400.0,
    
    "lane_AB_east": 400.0,
    "lane_B_north_in": 300.0,
    "lane_B_east_in": 300.0,
    "lane_BC_north": 400.0,
    
    "lane_CD_east": 400.0,
    "lane_BC_south": 400.0,
    "lane_C_east_in": 300.0,
    "lane_C_south_in": 300.0,
    
    "lane_D_west_in": 300.0,
    "lane_AD_south": 400.0,
    "lane_CD_west": 400.0,
    "lane_D_south_in": 300.0,
}
_MOCK_TYPES = list(VehicleType)

# Chance (per tick) that a mock emergency vehicle is present on a random
# lane, so Emergency Vehicle Detection is exercisable without real SUMO.
_MOCK_EMERGENCY_SPAWN_CHANCE: float = 0.05
_MOCK_EMERGENCY_TYPE_IDS = ["ambulance", "police", "firetruck"]

_MOCK_SUMO_TYPE_ID: dict[VehicleType, str] = {
    VehicleType.CAR: "passenger",
    VehicleType.MOTORCYCLE: "motorcycle",
    VehicleType.BUS: "bus",
    VehicleType.EMERGENCY: "ambulance",
}


def _mock_vehicle_type() -> VehicleType:
    """Return a weighted random vehicle type (cars most common)."""
    return random.choices(
        [VehicleType.CAR, VehicleType.MOTORCYCLE, VehicleType.BUS, VehicleType.EMERGENCY],
        weights=[70, 15, 10, 5],
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
        self.last_fetch_latency_ms: float = 0.0
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
        fetch_start = time.perf_counter()
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
                lane_position: float = traci.vehicle.getLanePosition(vid)
                pos: tuple[float, float] = traci.vehicle.getPosition(vid)
                road_id: str = traci.vehicle.getRoadID(vid)
                waiting_time: float = traci.vehicle.getWaitingTime(vid)

                # VDC-02: classify via getVehicleClass() per spec (falls back
                # to the vType id if the class string is unrecognised). Also
                # keep the raw vclass/type_id strings so the Emergency
                # Vehicle Detector can identify ambulance/police/firetruck
                # without a second TraCI round-trip.
                v_type, sumo_vclass, sumo_type_id = self._classify_vehicle(vid)

                vehicles.append(
                    VehicleData(
                        vehicle_id=vid,
                        speed=speed,
                        lane_id=lane_id,
                        lane_position=lane_position,
                        position_x=pos[0],
                        position_y=pos[1],
                        vehicle_type=v_type,
                        road_id=road_id,
                        waiting_time=waiting_time,
                        sumo_type_id=sumo_type_id,
                        sumo_vclass=sumo_vclass,
                        timestamp=ts,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Could not read vehicle '{vid}': {exc}")

        # VDC-03: fetch must complete within 200ms per simulation step.
        self.last_fetch_latency_ms = (time.perf_counter() - fetch_start) * 1000.0
        if self.last_fetch_latency_ms > _FETCH_LATENCY_BUDGET_MS:
            logger.warning(
                f"TraCI fetch latency {self.last_fetch_latency_ms:.1f}ms "
                f"exceeded {_FETCH_LATENCY_BUDGET_MS:.0f}ms budget "
                f"({len(vehicle_ids)} vehicles)."
            )

        logger.debug(
            f"Collected {len(vehicles)} vehicles from TraCI in "
            f"{self.last_fetch_latency_ms:.1f}ms."
        )
        return vehicles

    @staticmethod
    def _classify_vehicle(vid: str) -> tuple[VehicleType, str, str]:
        """
        Classify a vehicle using TraCI's ``getVehicleClass()`` (VDC-02
        acceptance criterion). Falls back to the vType id if the SUMO
        vClass string isn't one we recognise.

        Returns
        -------
        tuple[VehicleType, str, str]
            ``(vehicle_type, raw_vclass, raw_type_id)`` — the raw strings
            are kept so the Emergency Vehicle Detector can distinguish
            ambulance/police/firetruck (all share vClass "emergency").
        """
        try:
            vclass: str = traci.vehicle.getVehicleClass(vid).lower()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"getVehicleClass() failed for '{vid}': {exc}")
            vclass = ""

        try:
            type_id: str = traci.vehicle.getTypeID(vid).lower()
        except Exception:  # noqa: BLE001
            type_id = ""

        v_type = _TYPE_MAP.get(vclass, VehicleType.UNKNOWN)
        if v_type is VehicleType.UNKNOWN:
            v_type = _TYPE_MAP.get(type_id, VehicleType.UNKNOWN)
        return v_type, vclass, type_id

    def _generate_mock_vehicles(self) -> List[VehicleData]:
        """
        Generate 10-50 synthetic vehicles spread across 4 lanes.

        Each vehicle gets:
        - A deterministic but slightly varying position to simulate movement
        - A realistic speed (0–16 m/s)
        - A weighted random vehicle type
        """
        fetch_start = time.perf_counter()
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
            lane_length_m = _MOCK_LANE_LENGTHS_M.get(lane_id, 500.0)
            lane_position = random.uniform(0.0, lane_length_m)
            # Near-stopped vehicles accumulate mock waiting time.
            waiting_time = round(random.uniform(5.0, 40.0), 1) if speed < 2.0 else 0.0
            v_type = _mock_vehicle_type()
            sumo_type_id = _MOCK_SUMO_TYPE_ID.get(v_type, "")

            vehicles.append(
                VehicleData(
                    vehicle_id=f"veh_{i:04d}",
                    speed=round(speed, 2),
                    lane_id=lane_id,
                    lane_position=round(lane_position, 2),
                    position_x=round(pos_x, 2),
                    position_y=round(pos_y, 2),
                    waiting_time=waiting_time,
                    vehicle_type=v_type,
                    road_id=road_id,
                    sumo_type_id=sumo_type_id,
                    sumo_vclass=sumo_type_id,
                    timestamp=ts,
                )
            )

        # Occasionally include a mock emergency vehicle so Emergency
        # Vehicle Detection is exercisable without real SUMO installed.
        if random.random() < _MOCK_EMERGENCY_SPAWN_CHANCE:
            lane_index = random.randrange(len(_MOCK_LANES))
            lane_id = _MOCK_LANES[lane_index]
            road_id = _MOCK_ROADS[lane_index]
            emergency_type_id = random.choice(_MOCK_EMERGENCY_TYPE_IDS)
            speed = round(max(0.0, random.gauss(12.0, 3.0)), 2)
            lane_length_m = _MOCK_LANE_LENGTHS_M.get(lane_id, 500.0)

            vehicles.append(
                VehicleData(
                    vehicle_id=f"{emergency_type_id}_{int(sim_time):04d}",
                    speed=speed,
                    lane_id=lane_id,
                    lane_position=round(random.uniform(0.0, lane_length_m), 2),
                    position_x=round(random.uniform(0.0, 500.0), 2),
                    position_y=round(random.uniform(0.0, 500.0), 2),
                    waiting_time=0.0,
                    vehicle_type=VehicleType.UNKNOWN,
                    road_id=road_id,
                    sumo_type_id=emergency_type_id,
                    sumo_vclass="emergency",
                    timestamp=ts,
                )
            )

        self.last_fetch_latency_ms = (time.perf_counter() - fetch_start) * 1000.0
        logger.debug(
            f"Generated {len(vehicles)} mock vehicles at sim_time={sim_time:.1f}s "
            f"in {self.last_fetch_latency_ms:.1f}ms (MOCK)."
        )
        return vehicles
