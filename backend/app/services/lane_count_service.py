"""
IntelliRoads – Lane vehicle-count service.

Groups vehicles by their lane_id and exposes summary statistics.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from app.models.vehicle import VehicleData
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LaneCountService:
    """
    Counts vehicles per lane and provides lane-level statistics.

    This service is stateless – every method operates on the caller-
    supplied ``vehicles`` list.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def count_per_lane(self, vehicles: List[VehicleData]) -> Dict[str, int]:
        """
        Group vehicles by ``lane_id`` and return a count per lane.

        Parameters
        ----------
        vehicles : List[VehicleData]

        Returns
        -------
        Dict[str, int]
            Mapping of ``lane_id`` → vehicle count.  Only lanes with at
            least one vehicle are included.
        """
        counts: Dict[str, int] = defaultdict(int)
        for v in vehicles:
            counts[v.lane_id] += 1

        result = dict(counts)
        logger.debug(f"count_per_lane result: {result}")
        return result

    def get_lane_stats(self, vehicles: List[VehicleData]) -> dict:
        """
        Return per-lane counts plus busiest and emptiest lane identifiers.

        Parameters
        ----------
        vehicles : List[VehicleData]

        Returns
        -------
        dict
            Keys: ``lane_counts``, ``busiest_lane``, ``emptiest_lane``,
            ``total_vehicles``, ``lane_count`` (number of distinct lanes).
        """
        counts = self.count_per_lane(vehicles)

        busiest_lane: Optional[str] = None
        emptiest_lane: Optional[str] = None

        if counts:
            busiest_lane = max(counts, key=lambda k: counts[k])
            emptiest_lane = min(counts, key=lambda k: counts[k])

        stats = {
            "lane_counts": counts,
            "busiest_lane": busiest_lane,
            "emptiest_lane": emptiest_lane,
            "total_vehicles": len(vehicles),
            "lane_count": len(counts),
        }
        logger.debug(
            f"get_lane_stats: busiest={busiest_lane}, emptiest={emptiest_lane}"
        )
        return stats

    def get_total_count(self, vehicles: List[VehicleData]) -> int:
        """
        Return the total number of vehicles across all lanes.

        Parameters
        ----------
        vehicles : List[VehicleData]

        Returns
        -------
        int
        """
        return len(vehicles)
