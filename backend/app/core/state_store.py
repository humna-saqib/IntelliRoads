"""
IntelliRoads – Thread-safe in-memory state store.

Acts as a local cache for the latest traffic snapshot, allowing REST API
endpoints and WebSockets to read state without blocking the core simulation loop.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from app.models.congestion import CongestionResponse
from app.models.density import DensityResponse
from app.models.emergency import EmergencyResponse
from app.models.kpi import KPIData
from app.models.occupancy import OccupancyResponse
from app.models.performance import PerformanceSnapshot
from app.models.signal import SignalResponse
from app.models.vehicle import VehicleData
from app.utils.logger import get_logger

logger = get_logger(__name__)


class InMemoryStateStore:
    """
    Thread-safe storage for the latest simulation state.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._vehicles: List[VehicleData] = []
        self._density: Optional[DensityResponse] = None
        self._congestion: Optional[CongestionResponse] = None
        self._signals: Optional[SignalResponse] = None
        self._kpis: Optional[KPIData] = None
        self._emergency: Optional[EmergencyResponse] = None
        self._occupancy: Optional[OccupancyResponse] = None
        self._performance: Optional[PerformanceSnapshot] = None
        self._sim_time: float = 0.0
        self._last_update: float = time.time()
        logger.info("InMemoryStateStore initialised.")

    async def update_all(
        self,
        vehicles: List[VehicleData],
        density: DensityResponse,
        congestion: CongestionResponse,
        signals: SignalResponse,
        kpis: KPIData,
        sim_time: float,
        emergency: Optional[EmergencyResponse] = None,
        occupancy: Optional[OccupancyResponse] = None,
        performance: Optional[PerformanceSnapshot] = None,
    ) -> None:
        """
        Atomically update all cached state elements.
        """
        async with self._lock:
            self._vehicles = vehicles
            self._density = density
            self._congestion = congestion
            self._signals = signals
            self._kpis = kpis
            if emergency is not None:
                self._emergency = emergency
            if occupancy is not None:
                self._occupancy = occupancy
            if performance is not None:
                self._performance = performance
            self._sim_time = sim_time
            self._last_update = time.time()
            logger.debug(f"State store updated at sim_time={sim_time:.1f}s")

    async def get_emergency(self) -> Optional[EmergencyResponse]:
        async with self._lock:
            return self._emergency

    async def get_occupancy(self) -> Optional[OccupancyResponse]:
        async with self._lock:
            return self._occupancy

    async def get_performance(self) -> Optional[PerformanceSnapshot]:
        async with self._lock:
            return self._performance

    async def get_vehicles(self) -> List[VehicleData]:
        async with self._lock:
            return list(self._vehicles)

    async def get_density(self) -> Optional[DensityResponse]:
        async with self._lock:
            return self._density

    async def get_congestion(self) -> Optional[CongestionResponse]:
        async with self._lock:
            return self._congestion

    async def get_signals(self) -> Optional[SignalResponse]:
        async with self._lock:
            return self._signals

    async def get_kpis(self) -> Optional[KPIData]:
        async with self._lock:
            return self._kpis

    async def get_simulation_time(self) -> float:
        async with self._lock:
            return self._sim_time

    async def get_full_snapshot(self) -> dict:
        """
        Return the full snapshot as a serializable dictionary.
        """
        async with self._lock:
            # Map Pydantic models to dicts for JSON serialization
            vehicles_dict = [v.model_dump() for v in self._vehicles]
            density_dict = self._density.model_dump() if self._density else {}
            congestion_dict = self._congestion.model_dump() if self._congestion else {}
            signals_dict = self._signals.model_dump() if self._signals else {}
            kpis_dict = self._kpis.model_dump() if self._kpis else {}
            emergency_dict = self._emergency.model_dump() if self._emergency else {}
            occupancy_dict = self._occupancy.model_dump() if self._occupancy else {}
            performance_dict = self._performance.model_dump() if self._performance else {}

            # Build flat mock intersections data for Sprint 1
            intersections = []
            # We have 4 intersections: A, B, C, D
            # Let's match them to their signal timing and density levels
            junctions = ["junctionA", "junctionB", "junctionC", "junctionD"]
            lanes = ["lane_A_0", "lane_B_0", "lane_C_0", "lane_D_0"]
            names = ["Intersection A", "Intersection B", "Intersection C", "Intersection D"]

            for idx, (j_id, lane_id, name) in enumerate(zip(junctions, lanes, names)):
                # Default values
                sig_phase = "GREEN"
                cong_status = "CLEAR"
                v_count = 0
                density_val = 0.0

                # Extract vehicle count and density
                if self._density:
                    for l_dens in self._density.lanes:
                        if l_dens.lane_id == lane_id:
                            v_count = l_dens.vehicle_count
                            density_val = l_dens.density
                            break

                # Extract signal phase
                if self._signals:
                    for sig in self._signals.signals:
                        if sig.junction_id == j_id:
                            sig_phase = sig.phase
                            break

                # Extract congestion status
                if self._congestion:
                    for ev in self._congestion.events:
                        if ev.intersection_id == lane_id:
                            cong_status = ev.status
                            break

                intersections.append({
                    "id": j_id,
                    "name": name,
                    "signal": sig_phase,
                    "congestion_status": cong_status,
                    "vehicle_count": v_count,
                    "density": density_val
                })

            # Calculate classification distributions
            classification_dict = {
                "car": 0,
                "motorcycle": 0,
                "bus": 0,
                "truck": 0,
                "unknown": 0,
                "percentages": {},
                "most_common_type": "car"
            }

            if self._vehicles:
                counts = {"CAR": 0, "MOTORCYCLE": 0, "BUS": 0, "TRUCK": 0, "UNKNOWN": 0}
                for v in self._vehicles:
                    # v.vehicle_type is VehicleType enum (use name/value)
                    v_type_str = str(v.vehicle_type).upper()
                    if v_type_str in counts:
                        counts[v_type_str] += 1
                    else:
                        counts["UNKNOWN"] += 1
                
                classification_dict["car"] = counts["CAR"]
                classification_dict["motorcycle"] = counts["MOTORCYCLE"]
                classification_dict["bus"] = counts["BUS"]
                classification_dict["truck"] = counts["TRUCK"]
                classification_dict["unknown"] = counts["UNKNOWN"]
                
                total = len(self._vehicles)
                if total > 0:
                    classification_dict["percentages"] = {
                        "car": round((counts["CAR"] / total) * 100, 1),
                        "motorcycle": round((counts["MOTORCYCLE"] / total) * 100, 1),
                        "bus": round((counts["BUS"] / total) * 100, 1),
                        "truck": round((counts["TRUCK"] / total) * 100, 1),
                        "unknown": round((counts["UNKNOWN"] / total) * 100, 1),
                    }
                most_common = max(counts, key=counts.get)
                classification_dict["most_common_type"] = most_common.lower()

            return {
                "vehicles": vehicles_dict,
                "classification": classification_dict,
                "density": density_dict,
                "congestion": congestion_dict,
                "signals": signals_dict,
                "kpis": kpis_dict,
                "emergency": emergency_dict,
                "occupancy": occupancy_dict,
                "performance": performance_dict,
                "intersections": intersections,
                "timestamp": self._last_update,
            }
