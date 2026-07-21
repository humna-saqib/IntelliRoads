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
    "lane_A_west_in": "junctionA",
    "lane_B_east_in": "junctionB",
    "lane_C_east_in": "junctionC",
    "lane_D_west_in": "junctionD",
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
        self._last_phase_indices: Dict[str, int] = {}
        self._mock_phase: int = 0
        self._mock_step_count: int = 0
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

    def get_density_level_for_active_direction(
        self, junction_id: str, current_phase: int, density_response: DensityResponse
    ) -> DensityLevel:
        # Determine active lanes based on phase (0/1 is WE, 2/3 is NS)
        lanes_to_check: List[str] = []
        if current_phase in (0, 1):
            if junction_id == "junctionA":
                lanes_to_check = ["lane_A_west_in", "lane_AB_west"]
            elif junction_id == "junctionB":
                lanes_to_check = ["lane_AB_east", "lane_B_east_in"]
            elif junction_id == "junctionC":
                lanes_to_check = ["lane_CD_east", "lane_C_east_in"]
            elif junction_id == "junctionD":
                lanes_to_check = ["lane_D_west_in", "lane_CD_west"]
        else:  # Phase 2 or 3
            if junction_id == "junctionA":
                lanes_to_check = ["lane_A_north_in", "lane_AD_north"]
            elif junction_id == "junctionB":
                lanes_to_check = ["lane_B_north_in", "lane_BC_north"]
            elif junction_id == "junctionC":
                lanes_to_check = ["lane_BC_south", "lane_C_south_in"]
            elif junction_id == "junctionD":
                lanes_to_check = ["lane_AD_south", "lane_D_south_in"]

        max_density = -1.0
        max_level = DensityLevel.LOW

        # Map lane_id to lane info
        lane_map = {lane.lane_id: lane for lane in density_response.lanes}

        for lane_id in lanes_to_check:
            lane_data = lane_map.get(lane_id)
            if lane_data:
                if lane_data.density > max_density:
                    max_density = lane_data.density
                    max_level = DensityLevel(lane_data.level) if isinstance(lane_data.level, str) else lane_data.level

        return max_level

    def compute_timing(
        self, junction_id: str, density_level: DensityLevel, active_phase: SignalPhaseType
    ) -> SignalTiming:
        """
        Compute the optimal green-phase timing for *junction_id*.
        """
        duration = self.TIMING_RULES.get(density_level, 20.0)
        direction_label = "West/East" if active_phase == SignalPhaseType.GREEN else "North/South"
        reason = f"{density_level} density on {direction_label} approach → {duration}s green phase"

        return SignalTiming(
            junction_id=junction_id,
            phase=active_phase,
            duration_seconds=duration,
            density_level=density_level,
            triggered_at=time.time(),
            reason=reason,
        )

    def apply_signal(self, junction_id: str, timing: SignalTiming, current_phase: int) -> None:
        """
        Apply *timing* to the given junction.
        """
        old_phase: str = "NONE"
        if junction_id in self._current_signals:
            old_phase = self._current_signals[junction_id].phase

        # Apply via TraCI when available and only when a new phase starts
        if not self.mock_mode and SUMO_AVAILABLE:
            try:
                last_phase = self._last_phase_indices.get(junction_id)
                if current_phase != last_phase:
                    # Only set the duration if it is one of the green phases (0 or 2)
                    if current_phase in (0, 2):
                        traci.trafficlight.setPhaseDuration(
                            junction_id, timing.duration_seconds
                        )
                        logger.info(
                            f"TraCI: updated junction '{junction_id}' phase {current_phase} "
                            f"duration to {timing.duration_seconds}s"
                        )
                    self._last_phase_indices[junction_id] = current_phase
            except Exception as exc:
                logger.warning(
                    f"TraCI setPhaseDuration failed for {junction_id}: {exc}"
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
        Recompute and apply signals for every junction.
        """
        junctions = ["junctionA", "junctionB", "junctionC", "junctionD"]
        
        # Advance mock phase if in mock mode
        if self.mock_mode:
            self._mock_step_count += 1
            # Mock phase cycle: Phase 0 (WE Green) = 30s, Phase 1 (WE Yellow) = 5s,
            # Phase 2 (NS Green) = 30s, Phase 3 (NS Yellow) = 5s. Total cycle = 70s.
            if self._mock_step_count >= 70:
                self._mock_step_count = 0
            
            if self._mock_step_count < 30:
                current_phase = 0
            elif self._mock_step_count < 35:
                current_phase = 1
            elif self._mock_step_count < 65:
                current_phase = 2
            else:
                current_phase = 3
        else:
            current_phase = 0 # Fallback
            
        for junction_id in junctions:
            # 1. Get current phase index from SUMO if available
            if not self.mock_mode and SUMO_AVAILABLE:
                try:
                    current_phase = traci.trafficlight.getPhase(junction_id)
                except Exception as exc:
                    logger.warning(f"Failed to get phase for {junction_id}: {exc}")
            
            # 2. Get density level for the active direction (WE or NS)
            density_level = self.get_density_level_for_active_direction(
                junction_id, current_phase, density_response
            )
            
            # 3. Map SUMO phase to SignalPhaseType for the monitored West/East approach
            if current_phase == 0:
                active_phase_type = SignalPhaseType.GREEN
            elif current_phase == 1:
                active_phase_type = SignalPhaseType.YELLOW
            else:
                active_phase_type = SignalPhaseType.RED
                
            # 4. Compute timing
            timing = self.compute_timing(junction_id, density_level, active_phase_type)
            
            # 5. Apply signal
            self.apply_signal(junction_id, timing, current_phase)
            
        logger.debug(
            f"update_all_signals: updated {len(junctions)} junction(s)."
        )

    def get_current_signals(self) -> List[SignalTiming]:
        """
        Return the most recently applied timing for every junction.

        Returns
        -------
        List[SignalTiming]
        """
        return list(self._current_signals.values())
