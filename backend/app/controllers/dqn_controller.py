"""
IntelliRoads – DQN Traffic Light Controller.

Integrates the Deep Q-Network (DQN) agent with SUMO + TraCI simulation:
1. Reads current traffic state using TraCI via SUMOEnvironment.
2. Passes state to DQNAgent to select action.
3. Receives selected action.
4. Applies action to traffic lights through TraCI via SUMOEnvironment.
5. Computes reward and next state.
6. Stores transition in ReplayMemory.

Supports switching between RULE_BASED controller and DQN controller
while keeping the old rule-based controller available for baseline comparison.
"""

from __future__ import annotations

from enum import Enum
import time
from typing import Dict, List, Optional, Tuple, Any

from app.agent.dqn_agent import DQNAgent
from app.environment.sumo_environment import DQNAction, SUMOEnvironment
from app.models.density import DensityLevel, DensityResponse
from app.models.signal import SignalPhaseType, SignalTiming
from app.services.signal_controller import SignalController
from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger, log_signal_change

if SUMO_AVAILABLE:
    import traci  # type: ignore

logger = get_logger(__name__)


class ControllerMode(str, Enum):
    """Selectable Controller Operating Mode."""
    RULE_BASED = "RULE_BASED"
    DQN = "DQN"


class DQNController:
    """
    DQN-based Traffic Light Signal Controller with SUMO + TraCI Integration.

    Parameters
    ----------
    session : TraCISession
        Active TraCI session.
    environment : SUMOEnvironment
        SUMO environment wrapper for state extraction, action execution, and reward calculation.
    agent : DQNAgent
        Deep Q-Network agent instance.
    rule_based_controller : SignalController, optional
        Existing Sprint 1 rule-based controller for comparison and fallback.
    """

    def __init__(
        self,
        session: TraCISession,
        environment: SUMOEnvironment,
        agent: DQNAgent,
        rule_based_controller: Optional[SignalController] = None,
        mode: ControllerMode = ControllerMode.RULE_BASED,
    ) -> None:
        self.session = session
        self.env = environment
        self.agent = agent
        self.rule_based_controller = rule_based_controller
        self.mode = mode

        self._current_signals: Dict[str, SignalTiming] = {}
        self._last_state: Dict[str, List[float]] = {}
        self._last_action: Dict[str, int] = {}
        self._last_durations: Dict[str, float] = {}

        logger.info(
            f"DQNController initialised in mode={self.mode.value}, "
            f"mock_mode={self.session.mock_mode}"
        )

    # ------------------------------------------------------------------
    # Controller Mode Management
    # ------------------------------------------------------------------

    def set_mode(self, mode: ControllerMode | str) -> None:
        """Switch active controller mode (RULE_BASED vs DQN)."""
        if isinstance(mode, str):
            mode = ControllerMode(mode.upper())
        self.mode = mode
        logger.info(f"DQNController mode set to: {self.mode.value}")

    def get_mode(self) -> ControllerMode:
        """Get current active controller mode."""
        return self.mode

    # ------------------------------------------------------------------
    # Core Controller Step Workflow
    # ------------------------------------------------------------------

    def control_step(
        self,
        density_response: DensityResponse,
        vehicles: Optional[List[Any]] = None,
        occupancy_response: Optional[Any] = None,
        throughput: int = 1,
        epsilon: float = 0.1,
    ) -> List[SignalTiming]:
        """
        Execute one control cycle step across all monitored junctions.

        Workflow:
        1. If mode is RULE_BASED: delegate to rule-based controller while collecting DQN state.
        2. If mode is DQN:
           a. Read traffic state using TraCI via SUMOEnvironment.
           b. Pass state vector to DQNAgent to select action.
           c. Execute action on traffic lights through TraCI via SUMOEnvironment.
           d. Compute reward and observe next state.
           e. Store transition (s, a, r, s', done) in agent replay memory.
        3. Return list of SignalTiming objects for API / state store / dashboard consistency.
        """
        # If in RULE_BASED mode, run rule-based controller and return its timing decisions
        if self.mode == ControllerMode.RULE_BASED and self.rule_based_controller is not None:
            self.rule_based_controller.update_all_signals(density_response)
            signals = self.rule_based_controller.get_current_signals()
            # Also observe and store state for baseline matching
            self._observe_state_only(vehicles, density_response, occupancy_response, signals)
            return signals

        # Otherwise, execute DQN control workflow
        timings: List[SignalTiming] = []

        for junction_id in self.env.junction_ids:
            # 1. Read current traffic state using TraCI
            state = self.env.get_state(
                junction_id=junction_id,
                vehicles=vehicles,
                density_response=density_response,
                occupancy_response=occupancy_response,
                signals=None,
            )

            # 2. Pass state to DQN agent to get selected action
            action_index = self.agent.select_action(state, epsilon=epsilon)
            action_enum = DQNAction(action_index)

            # 3. Apply action to traffic lights through TraCI & step environment
            next_state, reward, done, info = self.env.step(
                action=action_index,
                junction_id=junction_id,
                throughput=throughput,
                vehicles=vehicles,
                density_response=density_response,
                occupancy_response=occupancy_response,
                signals=None,
            )

            # 4. Store experience transition in DQN Agent replay memory
            self.agent.store_transition(
                state=state,
                action=action_index,
                reward=reward,
                next_state=next_state,
                done=done,
            )

            # 5. Build SignalTiming object for application compatibility
            current_duration = self._compute_new_duration(junction_id, action_enum, state[4])
            timing = SignalTiming(
                junction_id=junction_id,
                phase=SignalPhaseType.GREEN,
                duration_seconds=current_duration,
                density_level=self._map_density_level(state[0]),
                triggered_at=time.time(),
                reason=f"DQN Action: {action_enum.name} (Reward: {reward:.2f}, Q-State: {state})",
            )

            self._current_signals[junction_id] = timing
            self._last_state[junction_id] = next_state
            self._last_action[junction_id] = action_index
            self._last_durations[junction_id] = current_duration
            timings.append(timing)

        return timings

    def get_current_signals(self) -> List[SignalTiming]:
        """Return the most recently applied signal timings."""
        if self.mode == ControllerMode.RULE_BASED and self.rule_based_controller is not None:
            return self.rule_based_controller.get_current_signals()
        return list(self._current_signals.values())

    # ------------------------------------------------------------------
    # Internal Helper Methods
    # ------------------------------------------------------------------

    def _observe_state_only(
        self,
        vehicles: Optional[List[Any]],
        density_response: DensityResponse,
        occupancy_response: Optional[Any],
        signals: List[SignalTiming],
    ) -> None:
        """Record observational traffic state when in Rule-Based mode."""
        for junction_id in self.env.junction_ids:
            state = self.env.get_state(
                junction_id=junction_id,
                vehicles=vehicles,
                density_response=density_response,
                occupancy_response=occupancy_response,
                signals=None,
            )
            self._last_state[junction_id] = state

    def _compute_new_duration(
        self, junction_id: str, action: DQNAction, prev_duration: float
    ) -> float:
        """Calculate updated green phase duration based on DQN action."""
        last_dur = self._last_durations.get(junction_id, prev_duration or 35.0)

        if action == DQNAction.KEEP_CURRENT_PHASE:
            return last_dur
        elif action == DQNAction.SWITCH_TO_NEXT_PHASE:
            return 20.0
        elif action == DQNAction.EXTEND_GREEN:
            return min(last_dur + 5.0, 90.0)
        elif action == DQNAction.REDUCE_GREEN:
            return max(last_dur - 5.0, 10.0)
        return last_dur

    @staticmethod
    def _map_density_level(vehicle_count: float) -> DensityLevel:
        """Map vehicle count to Low / Medium / High density level enum."""
        if vehicle_count < 10.0:
            return DensityLevel.LOW
        elif vehicle_count <= 25.0:
            return DensityLevel.MEDIUM
        return DensityLevel.HIGH
