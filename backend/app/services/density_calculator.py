"""
IntelliRoads – Density calculator service.

Converts per-lane vehicle counts into density measurements (veh/km)
and qualitative density levels.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from app.models.density import DensityLevel, DensityResponse, LaneDensity
from app.models.vehicle import VehicleData
from app.services.lane_count_service import LaneCountService
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default lane lengths (km) – used when the caller does not supply a mapping
# ---------------------------------------------------------------------------
_DEFAULT_LANE_LENGTH_KM: float = 0.5


class DensityCalculator:
    """
    Calculates traffic density per lane and across all lanes.

    Density = vehicle_count / lane_length_km

    Thresholds
    ----------
    LOW    : density < 20 veh/km
    MEDIUM : 20 ≤ density < 40 veh/km
    HIGH   : density ≥ 40 veh/km

    Parameters
    ----------
    lane_lengths : Optional[Dict[str, float]]
        Mapping of lane_id → length in km.  Unknown lanes fall back to
        ``_DEFAULT_LANE_LENGTH_KM``.
    """

    LANE_LENGTHS: Dict[str, float] = {
        "lane_A_0": 0.5,
        "lane_B_0": 0.6,
        "lane_C_0": 0.4,
        "lane_D_0": 0.5,
    }

    LOW_THRESHOLD: float = 20.0
    MEDIUM_THRESHOLD: float = 40.0

    def __init__(
        self, lane_lengths: Optional[Dict[str, float]] = None
    ) -> None:
        if lane_lengths:
            self.LANE_LENGTHS = {**self.LANE_LENGTHS, **lane_lengths}

        self._lane_count_service = LaneCountService()
        logger.info(
            f"DensityCalculator initialised with {len(self.LANE_LENGTHS)} lane(s)."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_lane_density(
        self, lane_id: str, vehicle_count: int
    ) -> LaneDensity:
        """
        Calculate density for a single lane.

        Parameters
        ----------
        lane_id : str
        vehicle_count : int

        Returns
        -------
        LaneDensity
        """
        length_km = self.LANE_LENGTHS.get(lane_id, _DEFAULT_LANE_LENGTH_KM)
        density = vehicle_count / length_km if length_km > 0 else 0.0
        level = self.get_density_level(density)

        return LaneDensity(
            lane_id=lane_id,
            vehicle_count=vehicle_count,
            lane_length_km=length_km,
            density=round(density, 3),
            level=level,
            timestamp=time.time(),
        )

    def calculate_all_densities(
        self, vehicles: List[VehicleData]
    ) -> DensityResponse:
        """
        Calculate density for every lane present in *vehicles*.

        Parameters
        ----------
        vehicles : List[VehicleData]

        Returns
        -------
        DensityResponse
        """
        counts = self._lane_count_service.count_per_lane(vehicles)

        # Sprint 1 scope is the 4 monitored intersection lanes only
        # (lane_A_0..lane_D_0). Unmonitored lanes such as outgoing/exit
        # lanes (e.g. lane_out_A_0) are intentionally excluded so they
        # can't be mistaken for extra intersections downstream (signals,
        # congestion, KPIs all derive their lane set from this response).
        all_lane_ids = set(self.LANE_LENGTHS.keys())

        densities: List[LaneDensity] = []
        for lane_id in sorted(all_lane_ids):
            count = counts.get(lane_id, 0)
            densities.append(self.calculate_lane_density(lane_id, count))

        avg = self.get_average_density(densities)
        logger.debug(
            f"calculate_all_densities: {len(densities)} lane(s), avg={avg:.2f}"
        )
        return DensityResponse(
            lanes=densities,
            average_density=round(avg, 3),
            timestamp=time.time(),
        )

    def get_density_level(self, density: float) -> DensityLevel:
        """
        Map a numeric density to a qualitative :class:`DensityLevel`.

        Parameters
        ----------
        density : float
            Vehicles per kilometre.

        Returns
        -------
        DensityLevel
        """
        if density < self.LOW_THRESHOLD:
            return DensityLevel.LOW
        if density < self.MEDIUM_THRESHOLD:
            return DensityLevel.MEDIUM
        return DensityLevel.HIGH

    def get_average_density(self, densities: List[LaneDensity]) -> float:
        """
        Compute the arithmetic mean density across a list of lanes.

        Parameters
        ----------
        densities : List[LaneDensity]

        Returns
        -------
        float
            0.0 if the list is empty.
        """
        if not densities:
            return 0.0
        return sum(d.density for d in densities) / len(densities)
