"""
IntelliRoads – Signal controller service.

Computes adaptive traffic-signal timings based on per-lane density
levels and applies them to SUMO via TraCI (or logs them in mock mode).
"""

from __future__ import annotations

import time
from typing import Dict, List

from app.models.density import DensityLevel, DensityResponse
from app.models.signal import SignalPhaseType, SignalResponse, SignalTiming
from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger, log_signal_change

if SUMO_AVAILABLE:
    import traci  # type: ignore

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lane → Junction mapping for Sprint 1 (hard-coded for 4 intersections)
# ---------------------------------------------------------------------------
_LANE_TO_JUNCTION: Dict[str, str] = {
    "lane_A_0": "junctionA",
    "lane_B_0": "junctionB",
    "lane_C_0": "junctionC",
    "lane_D_0": "junctionD",
}

# SUMO traffic-light phase indices for GREEN (0) and RED (2)
_SUMO_PHASE_INDEX: Dict[SignalPhaseType, int] = {
    SignalPhaseType.GREEN: 0,
    SignalPhaseType.YELLOW: 1,
    SignalPhaseType.RED: 2,
}


class SignalController:
    """
    Adaptive traffic-signal controller.

    Timing rules (green-phase duration)
    ------------------------------------
    LOW    density  → 20 s
    MEDIUM density  → 35 s
    HIGH   density  → 55 s

    Parameters
    ----------
    session : TraCISession
        An active TraCI session (may be in mock mode).
    """

    TIMING_RULES: Dict[DensityLevel, float] = {
        DensityLevel.LOW: 20.0,
        DensityLevel.MEDIUM: 35.0,
        DensityLevel.HIGH: 55.0,
    }

    def __init__(self, session: TraCISession) -> None:
        self._session = session
        self._current_signals: Dict[str, SignalTiming] = {}
        self._last_seen_phase: Dict[str, int] = {}
        logger.info(
            f"SignalController initialised, "
            f"rules={self.TIMING_RULES}"
        )

    @property
    def mock_mode(self) -> bool:
        """Dynamically check if we should run in mock mode."""
        return self._session.mock_mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_timing(
        self, junction_id: str, density_level: DensityLevel
    ) -> SignalTiming:
        """
        Compute the optimal green-phase timing for *junction_id*.

        Parameters
        ----------
        junction_id : str
        density_level : DensityLevel

        Returns
        -------
        SignalTiming
        """
        duration = self.TIMING_RULES.get(density_level, 20.0)
        reason = f"{density_level} density detected → {duration}s green phase"

        return SignalTiming(
            junction_id=junction_id,
            phase=SignalPhaseType.GREEN,
            duration_seconds=duration,
            density_level=density_level,
            triggered_at=time.time(),
            reason=reason,
        )

    def apply_signal(self, junction_id: str, timing: SignalTiming) -> None:
        """
        Apply *timing* to the given junction.

        If SUMO is available the TraCI API is called.  In all cases the
        internal state is updated and a structured log entry is written to
        ``logs/signals.log``.

        Parameters
        ----------
        junction_id : str
        timing : SignalTiming
        """
        old_phase: str = "NONE"
        if junction_id in self._current_signals:
            old_phase = self._current_signals[junction_id].phase

        # Apply via TraCI when available
        if not self.mock_mode and SUMO_AVAILABLE:
            try:
                phase_index = _SUMO_PHASE_INDEX.get(
                    SignalPhaseType(timing.phase), 0
                )
                traci.trafficlight.setPhase(junction_id, phase_index)
                traci.trafficlight.setPhaseDuration(
                    junction_id, timing.duration_seconds
                )
                logger.debug(
                    f"TraCI: set junction '{junction_id}' to phase "
                    f"{phase_index} for {timing.duration_seconds}s"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"TraCI setPhase failed for {junction_id}: {exc}"
                )

        # Update internal state
        self._current_signals[junction_id] = timing

        # Write to signals.log
        log_signal_change(
            junction_id=junction_id,
            old_phase=old_phase,
            new_phase=timing.phase if isinstance(timing.phase, str) else timing.phase.value,
            duration=timing.duration_seconds,
            reason=timing.reason,
        )

    def update_all_signals(self, density_response: DensityResponse) -> None:
        """
        Recompute and apply signals for every lane in *density_response*.

        Parameters
        ----------
        density_response : DensityResponse
        """
        for lane in density_response.lanes:
            junction_id = _LANE_TO_JUNCTION.get(
                lane.lane_id,
                f"junction_{lane.lane_id}",
            )
            density_level = DensityLevel(lane.level) if isinstance(lane.level, str) else lane.level
            timing = self.compute_timing(junction_id, density_level)
            self.apply_signal(junction_id, timing)

        logger.info(
            f"update_all_signals: updated {len(density_response.lanes)} junction(s)."
        )

    def get_current_signals(self) -> List[SignalTiming]:
        """
        Return the most recently applied timing for every junction.

        Returns
        -------
        List[SignalTiming]
        """
        return list(self._current_signals.values())
