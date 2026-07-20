"""
IntelliRoads – Congestion detector service.

Evaluates per-lane density against a fixed threshold and maintains
an internal event log so resolutions can be tracked.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from app.models.congestion import CongestionEvent, CongestionResponse, CongestionStatus
from app.models.density import DensityResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# CD-02: lane_id -> compass direction of approach, derived from each lane's
# geometry in sumo/network/intelliroads.net.xml (which side of the
# intersection the lane approaches from).
# ---------------------------------------------------------------------------
_LANE_DIRECTION: Dict[str, str] = {
    "lane_A_0": "W",
    "lane_B_0": "S",
    "lane_C_0": "E",
    "lane_D_0": "N",
}


class CongestionDetector:
    """
    Detects and tracks congestion events for monitored lanes / intersections.

    A lane is declared **CONGESTED** when its density exceeds
    :attr:`CONGESTION_THRESHOLD` vehicles/km.  Once density drops below
    the threshold the event is *resolved* (``resolved_at`` is set) and
    removed from the active set.

    Attributes
    ----------
    CONGESTION_THRESHOLD : float
        Density (veh/km) above which a lane is considered congested.
    """

    CONGESTION_THRESHOLD: float = 40.0

    def __init__(self) -> None:
        self._active_events: Dict[str, CongestionEvent] = {}
        logger.info(
            f"CongestionDetector initialised "
            f"(threshold={self.CONGESTION_THRESHOLD} veh/km)."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, density_response: DensityResponse) -> CongestionResponse:
        """
        Evaluate all lane densities and update the active-event register.

        Parameters
        ----------
        density_response : DensityResponse
            Latest density snapshot from :class:`DensityCalculator`.

        Returns
        -------
        CongestionResponse
            All events (active and newly resolved within this tick).
        """
        current_events: List[CongestionEvent] = []
        now = time.time()

        for lane in density_response.lanes:
            event = self.detect_for_intersection(lane.lane_id, lane.density)
            current_events.append(event)

        total_congested = sum(
            1
            for e in current_events
            if e.status == CongestionStatus.CONGESTED and e.resolved_at is None
        )

        logger.debug(
            f"detect(): {total_congested} congested lane(s) of "
            f"{len(density_response.lanes)} monitored."
        )

        return CongestionResponse(
            events=current_events,
            total_congested=total_congested,
            timestamp=now,
        )

    def detect_for_intersection(
        self, intersection_id: str, density: float
    ) -> CongestionEvent:
        """
        Check a single intersection/lane for congestion and update state.

        Parameters
        ----------
        intersection_id : str
            Lane or intersection identifier.
        density : float
            Current density in veh/km.

        Returns
        -------
        CongestionEvent
        """
        now = time.time()
        is_over_threshold = density > self.CONGESTION_THRESHOLD
        direction = _LANE_DIRECTION.get(intersection_id)

        if is_over_threshold:
            if intersection_id not in self._active_events:
                # New congestion event
                event = CongestionEvent(
                    intersection_id=intersection_id,
                    status=CongestionStatus.CONGESTED,
                    density_value=density,
                    threshold=self.CONGESTION_THRESHOLD,
                    timestamp=now,
                    resolved_at=None,
                    direction=direction,
                )
                self._active_events[intersection_id] = event
                logger.warning(
                    f"Congestion DETECTED at {intersection_id} "
                    f"(direction={direction or 'unknown'}): "
                    f"density={density:.1f} veh/km "
                    f"(threshold={self.CONGESTION_THRESHOLD})"
                )
            else:
                # Update density on existing event
                existing = self._active_events[intersection_id]
                updated = existing.model_copy(
                    update={"density_value": density, "resolved_at": None}
                )
                self._active_events[intersection_id] = updated
            return self._active_events[intersection_id]
        else:
            if intersection_id in self._active_events:
                # Resolve existing event
                existing = self._active_events.pop(intersection_id)
                resolved_event = existing.model_copy(
                    update={
                        "status": CongestionStatus.CLEAR,
                        "density_value": density,
                        "resolved_at": now,
                    }
                )
                logger.info(
                    f"Congestion RESOLVED at {intersection_id}: "
                    f"density={density:.1f} veh/km"
                )
                return resolved_event
            else:
                # No event – return a clean CLEAR record
                return CongestionEvent(
                    intersection_id=intersection_id,
                    status=CongestionStatus.CLEAR,
                    density_value=density,
                    threshold=self.CONGESTION_THRESHOLD,
                    timestamp=now,
                    resolved_at=None,
                    direction=direction,
                )

    def is_congested(self, lane_id: str) -> bool:
        """
        Return ``True`` if *lane_id* currently has an active congestion event.

        Parameters
        ----------
        lane_id : str

        Returns
        -------
        bool
        """
        return lane_id in self._active_events

    def get_all_active(self) -> List[CongestionEvent]:
        """
        Return all currently active (unresolved) congestion events.

        Returns
        -------
        List[CongestionEvent]
        """
        return list(self._active_events.values())
