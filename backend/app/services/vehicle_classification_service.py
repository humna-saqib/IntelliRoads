"""
IntelliRoads – Vehicle classification service.

Aggregates a list of VehicleData snapshots into counts, percentages,
and summary statistics by vehicle type.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List

from app.models.vehicle import VehicleData, VehicleType
from app.utils.logger import get_logger

logger = get_logger(__name__)


class VehicleClassificationService:
    """
    Classifies and summarises vehicle data by type.

    This service is stateless – every method operates purely on the
    ``vehicles`` argument supplied by the caller.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_vehicles(self, vehicles: List[VehicleData]) -> Dict[str, int]:
        """
        Count vehicles by type.

        Parameters
        ----------
        vehicles : List[VehicleData]
            The vehicle snapshots to classify.

        Returns
        -------
        Dict[str, int]
            Keys are lowercase type names (``"car"``, ``"motorcycle"``,
            ``"bus"``, ``"truck"``, ``"unknown"``), values are counts.
        """
        counts: Dict[str, int] = {
            "car": 0,
            "motorcycle": 0,
            "bus": 0,
            "truck": 0,
            "unknown": 0,
        }
        for v in vehicles:
            key = v.vehicle_type.lower() if isinstance(v.vehicle_type, str) else v.vehicle_type.value.lower()
            if key in counts:
                counts[key] += 1
            else:
                counts["unknown"] += 1

        logger.debug(f"classify_vehicles: {counts}")
        return counts

    def get_type_distribution(self, vehicles: List[VehicleData]) -> Dict[str, float]:
        """
        Return the percentage share of each vehicle type.

        Parameters
        ----------
        vehicles : List[VehicleData]

        Returns
        -------
        Dict[str, float]
            Percentages (0–100) for each type.  All values sum to ~100.
        """
        counts = self.classify_vehicles(vehicles)
        total = len(vehicles)

        if total == 0:
            return {k: 0.0 for k in counts}

        return {k: round(v / total * 100, 2) for k, v in counts.items()}

    def get_statistics(self, vehicles: List[VehicleData]) -> dict:
        """
        Return a comprehensive statistics dictionary.

        Parameters
        ----------
        vehicles : List[VehicleData]

        Returns
        -------
        dict
            Keys: ``counts``, ``percentages``, ``most_common_type``,
            ``total``.
        """
        counts = self.classify_vehicles(vehicles)
        percentages = self.get_type_distribution(vehicles)
        total = len(vehicles)

        most_common_type: str = "none"
        if total > 0:
            most_common_type = max(counts, key=lambda k: counts[k])

        stats = {
            "total": total,
            "counts": counts,
            "percentages": percentages,
            "most_common_type": most_common_type,
        }
        logger.debug(f"Vehicle statistics computed: total={total}")
        return stats
