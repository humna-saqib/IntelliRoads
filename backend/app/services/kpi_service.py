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
        mock_mode: bool = True,
        fetch_latency_ms: float = 0.0,
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
        mock_mode : bool
            Whether this snapshot was produced without a live SUMO/TraCI
            connection. Surfaced to the dashboard so mock data is never
            mistaken for a real simulation run.
        fetch_latency_ms : float
            Latency of the last TraCI vehicle-data fetch (VDC-03).

        Returns
        -------
        KPIData
        """
        total_vehicles = len(vehicles)

        # Average speed
        average_speed: float = 0.0
        if total_vehicles > 0:
            average_speed = sum(v.speed for v in vehicles) / total_vehicles

        # Average wait time – real TraCI getWaitingTime() per vehicle
        # (or the equivalent mock value generated alongside mock vehicles).
        average_wait_time: float = 0.0
        if total_vehicles > 0:
            average_wait_time = sum(v.waiting_time for v in vehicles) / total_vehicles

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

        # Active intersections = number of distinct junctions currently
        # monitored, derived from the live density snapshot rather than a
        # hardcoded constant.
        active_intersections = total_lanes

        kpis = KPIData(
            total_vehicles=total_vehicles,
            active_intersections=active_intersections,
            average_speed=round(average_speed, 2),
            average_wait_time=round(average_wait_time, 2),
            active_alerts=active_alerts,
            congestion_percentage=round(congestion_percentage, 2),
            simulation_time=sim_time,
            data_source="MOCK" if mock_mode else "LIVE",
            fetch_latency_ms=round(fetch_latency_ms, 1),
            timestamp=time.time(),
        )

        logger.debug(
            f"KPIs: vehicles={total_vehicles}, "
            f"avg_speed={kpis.average_speed:.2f} m/s, "
            f"avg_wait={kpis.average_wait_time:.2f}s, "
            f"alerts={active_alerts}, "
            f"congestion={kpis.congestion_percentage:.1f}%, "
            f"source={kpis.data_source}"
        )
        return kpis
