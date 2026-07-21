"""
IntelliRoads – SUMO + TraCI Reinforcement Learning Environment Wrapper.

Provides a modular RL environment interface for traffic signal control on SUMO:
- Reset simulation state
- State Space retrieval via TraCI (vehicle count, queue length, waiting time, occupancy, current phase)
- Action Space execution via TraCI (Keep phase, Switch phase, Extend green, Reduce green)
- Reward Function calculation (penalising waiting time, queues, congestion; rewarding throughput)
- Next State extraction
- Done flag determination
"""

from __future__ import annotations

import time
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger

if SUMO_AVAILABLE:
    import traci  # type: ignore

logger = get_logger(__name__)


class DQNAction(IntEnum):
    """
    Discrete action space for the DQN Traffic Light Controller:
    - 0: KEEP_CURRENT_PHASE   (Maintain current phase timing)
    - 1: SWITCH_TO_NEXT_PHASE (Advance traffic light to the next phase)
    - 2: EXTEND_GREEN         (Extend green phase duration by +5 seconds)
    - 3: REDUCE_GREEN         (Reduce green phase duration by -5 seconds, min 10s)
    """
    KEEP_CURRENT_PHASE = 0
    SWITCH_TO_NEXT_PHASE = 1
    EXTEND_GREEN = 2
    REDUCE_GREEN = 3


# ---------------------------------------------------------------------------
# Default Reward Weights
# Formula:
#   Reward = - (w_wait * avg_waiting_time)
#            - (w_queue * queue_length)
#            - (w_cong * is_congested)
#            + (w_tp * throughput)
#            - (w_action * action_change_penalty)
#
# Rationale:
#   - Penalise long delays (avg_waiting_time) to minimize driver wait time.
#   - Penalise queue lengths to avoid spillback into upstream junctions.
#   - Penalise active congestion states (density > 40 v/km).
#   - Reward throughput (number of vehicles that crossed junction during step).
#   - Add a minor penalty for unnecessary action changes to avoid rapid phase flickering.
# ---------------------------------------------------------------------------
REWARD_WEIGHT_WAITING_TIME: float = 1.0
REWARD_WEIGHT_QUEUE_LENGTH: float = 2.0
REWARD_WEIGHT_CONGESTION: float = 10.0
REWARD_WEIGHT_THROUGHPUT: float = 5.0
REWARD_WEIGHT_ACTION_CHANGE: float = 0.5

# Speed threshold below which a vehicle is considered queued / halted (m/s)
_QUEUE_SPEED_THRESHOLD_MS: float = 2.0


class SUMOEnvironment:
    """
    Modular RL Environment wrapping SUMO + TraCI simulation.

    State Space Vector per junction (5 features):
    ---------------------------------------------
    1. vehicle_count: Total vehicles on incoming lanes
    2. queue_length: Number of halted/queued vehicles (speed < 2.0 m/s)
    3. avg_waiting_time: Average waiting time across incoming vehicles (seconds)
    4. lane_occupancy: Lane occupancy percentage (0.0 to 100.0)
    5. current_phase: Current traffic light phase index (or active green duration)

    Action Space:
    -------------
    0: KEEP_CURRENT_PHASE
    1: SWITCH_TO_NEXT_PHASE
    2: EXTEND_GREEN (+5s)
    3: REDUCE_GREEN (-5s)

    Parameters
    ----------
    session : TraCISession
        Active TraCI session (or mock mode wrapper).
    junction_ids : List[str], optional
        List of junction IDs to monitor and control. Defaults to ['junctionA'].
    """

    def __init__(
        self,
        session: TraCISession,
        junction_ids: Optional[List[str]] = None,
    ) -> None:
        self.session = session
        self.junction_ids = junction_ids or ["junctionA", "junctionB", "junctionC", "junctionD"]
        self._step_count: int = 0
        self._max_steps: int = 3600
        self._last_throughput: Dict[str, int] = {j: 0 for j in self.junction_ids}
        logger.info(
            f"SUMOEnvironment initialised with junctions={self.junction_ids}, "
            f"mock_mode={self.session.mock_mode}"
        )

    # ------------------------------------------------------------------
    # Environment Core API: reset, get_state, step, compute_reward, is_done
    # ------------------------------------------------------------------

    def reset(self) -> Dict[str, List[float]]:
        """
        Reset simulation environment metrics and return initial state dictionary.

        Returns
        -------
        Dict[str, List[float]]
            Initial state vectors keyed by junction_id.
        """
        self._step_count = 0
        self._last_throughput = {j: 0 for j in self.junction_ids}
        logger.info("SUMOEnvironment reset called.")

        states: Dict[str, List[float]] = {}
        for junction_id in self.junction_ids:
            states[junction_id] = self.get_state(junction_id)
        return states

    def get_state(
        self,
        junction_id: str = "junctionA",
        vehicles: Optional[List[Any]] = None,
        density_response: Optional[Any] = None,
        occupancy_response: Optional[Any] = None,
        signals: Optional[Any] = None,
    ) -> List[float]:
        """
        Read the current traffic state for *junction_id* using TraCI or simulation objects.

        If TraCI is available in live mode, reads directly from TraCI API calls:
        - traci.lane.getLastStepVehicleNumber
        - traci.lane.getHaltingNumber
        - traci.lane.getWaitingTime
        - traci.lane.getLastStepOccupancy
        - traci.trafficlight.getPhase

        If TraCI is not connected or in mock mode, calculates from passed telemetry objects
        or generates plausible fallback metrics.

        Parameters
        ----------
        junction_id : str
            Target junction identifier.
        vehicles : List[VehicleData], optional
        density_response : DensityResponse, optional
        occupancy_response : OccupancyResponse, optional
        signals : SignalResponse, optional

        Returns
        -------
        List[float]
            5-element state vector:
            [vehicle_count, queue_length, avg_waiting_time, lane_occupancy, current_phase]
        """
        # Map junction to incoming lane ID convention
        lane_id = f"lane_{junction_id[-1]}_0" if junction_id.startswith("junction") else junction_id

        vehicle_count: float = 0.0
        queue_length: float = 0.0
        avg_waiting_time: float = 0.0
        lane_occupancy: float = 0.0
        current_phase: float = 0.0

        if not self.session.mock_mode and SUMO_AVAILABLE:
            try:
                # 1. Vehicle count per lane via TraCI
                vehicle_count = float(traci.lane.getLastStepVehicleNumber(lane_id))
            except Exception:
                vehicle_count = 5.0

            try:
                # 2. Queue length (halting vehicles with speed < threshold) via TraCI
                queue_length = float(traci.lane.getHaltingNumber(lane_id))
            except Exception:
                queue_length = 2.0

            try:
                # 3. Average waiting time via TraCI
                total_wait = float(traci.lane.getWaitingTime(lane_id))
                avg_waiting_time = total_wait / max(vehicle_count, 1.0)
            except Exception:
                avg_waiting_time = 12.0

            try:
                # 4. Lane occupancy (percentage 0 - 100%) via TraCI
                lane_occupancy = float(traci.lane.getLastStepOccupancy(lane_id)) * 100.0
            except Exception:
                lane_occupancy = 35.0

            try:
                # 5. Current traffic light phase via TraCI
                current_phase = float(traci.trafficlight.getPhase(junction_id))
            except Exception:
                current_phase = 0.0
        else:
            # Fallback for mock mode or object-passed state calculation
            if vehicles:
                junction_vehicles = [v for v in vehicles if v.lane_id == lane_id]
                vehicle_count = float(len(junction_vehicles))
                queue_length = float(sum(1 for v in junction_vehicles if v.speed < _QUEUE_SPEED_THRESHOLD_MS))
                avg_waiting_time = (
                    sum(v.waiting_time for v in junction_vehicles) / vehicle_count
                    if vehicle_count > 0 else 0.0
                )
            else:
                vehicle_count = 8.0
                queue_length = 3.0
                avg_waiting_time = 14.5

            if occupancy_response and hasattr(occupancy_response, "lanes"):
                for lane in occupancy_response.lanes:
                    if lane.lane_id == lane_id:
                        lane_occupancy = float(lane.occupancy_percent)
                        break
                else:
                    lane_occupancy = 40.0
            else:
                lane_occupancy = 40.0

            if signals and hasattr(signals, "signals"):
                for sig in signals.signals:
                    if sig.junction_id == junction_id:
                        current_phase = float(sig.duration_seconds)
                        break

        state_vector = [
            round(vehicle_count, 2),
            round(queue_length, 2),
            round(avg_waiting_time, 2),
            round(lane_occupancy, 2),
            round(current_phase, 2),
        ]
        return state_vector

    def step(
        self,
        action: int | DQNAction,
        junction_id: str = "junctionA",
        throughput: int = 1,
        vehicles: Optional[List[Any]] = None,
        density_response: Optional[Any] = None,
        occupancy_response: Optional[Any] = None,
        signals: Optional[Any] = None,
    ) -> Tuple[List[float], float, bool, Dict[str, Any]]:
        """
        Execute selected action in the SUMO environment via TraCI.

        Parameters
        ----------
        action : int | DQNAction
            Action to execute (0: KEEP, 1: SWITCH, 2: EXTEND, 3: REDUCE).
        junction_id : str
            Target junction.
        throughput : int
            Number of vehicles that crossed junction during this step.
        vehicles : List[VehicleData], optional
        density_response : DensityResponse, optional
        occupancy_response : OccupancyResponse, optional
        signals : SignalResponse, optional

        Returns
        -------
        Tuple[List[float], float, bool, Dict[str, Any]]
            (next_state, reward, done, info_dict)
        """
        action_enum = DQNAction(action)
        self._step_count += 1

        # 1. Apply action to SUMO traffic lights through TraCI
        self._apply_action_to_sumo(junction_id, action_enum)

        # 2. Extract current state & metrics
        next_state = self.get_state(
            junction_id=junction_id,
            vehicles=vehicles,
            density_response=density_response,
            occupancy_response=occupancy_response,
            signals=signals,
        )

        avg_waiting_time = next_state[2]
        queue_length = next_state[1]
        lane_occupancy = next_state[3]
        is_congested = (lane_occupancy > 70.0) or (next_state[0] > 15.0)

        # 3. Compute reward
        reward = self.compute_reward(
            avg_waiting_time=avg_waiting_time,
            queue_length=queue_length,
            is_congested=is_congested,
            throughput=throughput,
            action=action_enum,
        )

        # 4. Determine done status
        done = self.is_done()

        info = {
            "junction_id": junction_id,
            "action_taken": action_enum.name,
            "step": self._step_count,
            "sim_time": self.session.get_simulation_time(),
        }

        return next_state, reward, done, info

    def compute_reward(
        self,
        avg_waiting_time: float,
        queue_length: float,
        is_congested: bool,
        throughput: int,
        action: int | DQNAction,
    ) -> float:
        """
        Calculate reward signal based on traffic optimization objectives.

        Reward Formula:
        ---------------
        R = - (w_wait * avg_waiting_time)
            - (w_queue * queue_length)
            - (w_cong * (1.0 if is_congested else 0.0))
            + (w_tp * throughput)
            - (w_action * (0.0 if action == KEEP else 1.0))

        Docstring details:
        - Encourages lower vehicle waiting times (-1.0 * avg_waiting_time).
        - Encourages shorter queue lengths (-2.0 * queue_length).
        - Encourages high vehicle throughput (+5.0 * throughput).
        - Penalizes traffic congestion (-10.0 if congested).
        - Penalizes unnecessary signal phase alterations (-0.5 if action != KEEP).
        """
        act = DQNAction(action)
        action_penalty = 0.0 if act == DQNAction.KEEP_CURRENT_PHASE else 1.0

        reward = (
            - REWARD_WEIGHT_WAITING_TIME * avg_waiting_time
            - REWARD_WEIGHT_QUEUE_LENGTH * queue_length
            - REWARD_WEIGHT_CONGESTION * (1.0 if is_congested else 0.0)
            + REWARD_WEIGHT_THROUGHPUT * float(throughput)
            - REWARD_WEIGHT_ACTION_CHANGE * action_penalty
        )
        return round(reward, 4)

    def get_next_state(
        self,
        junction_id: str = "junctionA",
        vehicles: Optional[List[Any]] = None,
        density_response: Optional[Any] = None,
        occupancy_response: Optional[Any] = None,
        signals: Optional[Any] = None,
    ) -> List[float]:
        """Helper to get updated state vector."""
        return self.get_state(junction_id, vehicles, density_response, occupancy_response, signals)

    def is_done(self) -> bool:
        """
        Return True if the simulation run has terminated or max steps exceeded.
        """
        if not self.session.is_connected():
            return True
        if self._step_count >= self._max_steps:
            return True
        return False

    # ------------------------------------------------------------------
    # Private Helpers for TraCI Interaction
    # ------------------------------------------------------------------

    def _apply_action_to_sumo(self, junction_id: str, action: DQNAction) -> None:
        """
        Apply selected DQN action directly to SUMO traffic light via TraCI.
        """
        if self.session.mock_mode or not SUMO_AVAILABLE:
            logger.debug(f"Mock apply action '{action.name}' to {junction_id}")
            return

        try:
            current_phase = traci.trafficlight.getPhase(junction_id)
            current_duration = traci.trafficlight.getPhaseDuration(junction_id)

            if action == DQNAction.KEEP_CURRENT_PHASE:
                # Do nothing, maintain current phase
                pass
            elif action == DQNAction.SWITCH_TO_NEXT_PHASE:
                # Advance to next phase index
                next_phase = (current_phase + 1) % 4
                traci.trafficlight.setPhase(junction_id, next_phase)
                logger.info(f"DQN Action: Switched {junction_id} phase to {next_phase}")
            elif action == DQNAction.EXTEND_GREEN:
                # Extend current green duration by +5s
                new_duration = min(current_duration + 5.0, 90.0)
                traci.trafficlight.setPhaseDuration(junction_id, new_duration)
                logger.info(f"DQN Action: Extended {junction_id} green duration to {new_duration}s")
            elif action == DQNAction.REDUCE_GREEN:
                # Reduce current green duration by -5s (min bound 10s)
                new_duration = max(current_duration - 5.0, 10.0)
                traci.trafficlight.setPhaseDuration(junction_id, new_duration)
                logger.info(f"DQN Action: Reduced {junction_id} green duration to {new_duration}s")

        except Exception as exc:
            logger.warning(f"TraCI error applying DQN action '{action.name}' to {junction_id}: {exc}")
