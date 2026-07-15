"""
IntelliRoads – KPI computation service.

Aggregates simulation data into a single KPIData snapshot.
"""

from __future__ import annotations

import time
from typing import List

from app.models.congestion import CongestionResponse, CongestionStatus
from app.models.density import DensityResponse
from app.models.kpi import KPIData
from app.models.vehicle import VehicleData
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Vehicles with speed below this threshold are counted as "waiting"
_WAIT_SPEED_THRESHOLD_MS: float = 2.0

# Average time a near-stopped vehicle has been waiting (seconds) – mock estimate
_MOCK_WAIT_SECONDS: float = 15.0

# Sprint 1 hard-codes 4 intersections
_ACTIVE_INTERSECTIONS: int = 4


class KPIService:
    """
    Computes Key Performance Indicators for the IntelliRoads dashboard.

    This service is stateless; every :meth:`compute_kpis` call produces
    a fresh :class:`KPIData` from the inputs.
    """

    def __init__(self) -> None:
        logger.info("KPIService initialised.")

    def compute_kpis(
        self,
        vehicles: List[VehicleData],
        density_response: DensityResponse,
        congestion_response: CongestionResponse,
        sim_time: float,
    ) -> KPIData:
        """
        Compute a complete KPI snapshot.

        Parameters
        ----------
        vehicles : List[VehicleData]
            Current vehicle list from :class:`VehicleDataService`.
        density_response : DensityResponse
            Latest density snapshot.
        congestion_response : CongestionResponse
            Latest congestion snapshot.
        sim_time : float
            Current SUMO simulation time (seconds).

        Returns
        -------
        KPIData
        """
        total_vehicles = len(vehicles)

        # Average speed
        average_speed: float = 0.0
        if total_vehicles > 0:
            average_speed = sum(v.speed for v in vehicles) / total_vehicles

        # Average wait time – estimated from near-stopped vehicles
        near_stopped = [v for v in vehicles if v.speed < _WAIT_SPEED_THRESHOLD_MS]
        average_wait_time: float = 0.0
        if near_stopped:
            # Simple heuristic: the more vehicles waiting, the longer the avg wait
            average_wait_time = _MOCK_WAIT_SECONDS * (
                len(near_stopped) / max(total_vehicles, 1)
            ) * 10  # scale to seconds

        # Active alerts = currently CONGESTED intersections
        active_alerts = congestion_response.total_congested

        # Congestion percentage
        total_lanes = len(density_response.lanes)
        congested_lanes = sum(
            1
            for e in congestion_response.events
            if e.status == CongestionStatus.CONGESTED and e.resolved_at is None
        )
        congestion_percentage: float = 0.0
        if total_lanes > 0:
            congestion_percentage = (congested_lanes / total_lanes) * 100.0

        kpis = KPIData(
            total_vehicles=total_vehicles,
            active_intersections=_ACTIVE_INTERSECTIONS,
            average_speed=round(average_speed, 2),
            average_wait_time=round(average_wait_time, 2),
            active_alerts=active_alerts,
            congestion_percentage=round(congestion_percentage, 2),
            simulation_time=sim_time,
            timestamp=time.time(),
        )

        logger.debug(
            f"KPIs: vehicles={total_vehicles}, "
            f"avg_speed={kpis.average_speed:.2f} m/s, "
            f"alerts={active_alerts}, "
            f"congestion={kpis.congestion_percentage:.1f}%"
        )
        return kpis
