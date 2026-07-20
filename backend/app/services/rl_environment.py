"""
IntelliRoads – RL Environment Preparation service (Sprint 2).

Converts the current simulation state into a DQN-ready state
representation and produces (state, action, reward, next_state)
transitions from the rule-based controller's *observed* behaviour.
Purely observational: reads already-computed density/occupancy/
congestion/signal data, never influences SignalController or
EmergencyPriorityController. The goal at this stage is clean training
data collection and validation of the state/action/reward design —
no DQN model exists yet.

Transition formalism
---------------------
Because the rule-based controller computes its decision and the
resulting metrics within the *same* tick, a transition is built by
bridging two ticks per junction:

    state      = that junction's state vector from the PREVIOUS tick
    action     = this tick's decision, relative to the previous tick's
                 duration (DECREASE_GREEN / KEEP_SAME / INCREASE_GREEN)
    reward     = computed from THIS tick's resulting metrics — i.e.
                 the consequence of taking that action
    next_state = this tick's own state vector (becomes `state` for the
                 next transition)
    done       = always False for now; episode boundaries aren't
                 defined at this prep stage

The very first tick for any junction produces no experience, since
there is no prior state to pair it with.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from app.models.congestion import CongestionResponse
from app.models.density import DensityResponse
from app.models.occupancy import OccupancyResponse
from app.models.rl import RLAction, RLExperience
from app.models.signal import SignalTiming
from app.models.vehicle import VehicleData
from app.services.signal_controller import _LANE_TO_JUNCTION
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Vehicles slower than this are considered queued – matches the
# near-stopped convention used elsewhere (db_logger, performance metrics).
_QUEUE_SPEED_THRESHOLD_MS: float = 2.0

# ---------------------------------------------------------------------------
# Reward weights – initial defaults, intended to be tuned once actual DQN
# training begins. Not permanent constants.
# ---------------------------------------------------------------------------
REWARD_WEIGHT_WAITING_TIME: float = 1.0
REWARD_WEIGHT_QUEUE_LENGTH: float = 2.0
REWARD_WEIGHT_CONGESTION: float = 10.0
REWARD_WEIGHT_THROUGHPUT: float = 5.0
REWARD_WEIGHT_SIGNAL_CHANGE: float = 0.5

StateVector = List[float]


class RLEnvironment:
    """
    Produces per-junction (state, action, reward, next_state) transitions
    from the rule-based controller's observed behaviour, every tick.
    """

    def __init__(self) -> None:
        self._previous_state: Dict[str, StateVector] = {}
        self._previous_duration: Dict[str, float] = {}
        self._transition_count: int = 0
        logger.info("RLEnvironment initialised (observation-only, no control).")

    # ------------------------------------------------------------------
    # Public API – called once per simulation tick
    # ------------------------------------------------------------------

    def step(
        self,
        sim_time: float,
        vehicles: List[VehicleData],
        density_response: DensityResponse,
        occupancy_response: OccupancyResponse,
        congestion_response: CongestionResponse,
        normal_signals: List[SignalTiming],
        throughput_tick: int,
    ) -> List[RLExperience]:
        """
        Compute this tick's state vector for every monitored junction and
        emit an experience for any junction that had a state recorded
        last tick.
        """
        lane_metrics = self._compute_lane_metrics(vehicles)
        density_by_lane = {lane.lane_id: lane for lane in density_response.lanes}
        occupancy_by_lane = {lane.lane_id: lane for lane in occupancy_response.lanes}
        congested_lanes = {
            e.intersection_id
            for e in congestion_response.events
            if (e.status if isinstance(e.status, str) else e.status.value) == "CONGESTED"
            and e.resolved_at is None
        }

        experiences: List[RLExperience] = []

        for timing in normal_signals:
            junction_id = timing.junction_id
            lane_id = next(
                (lid for lid, jid in _LANE_TO_JUNCTION.items() if jid == junction_id), None
            )
            if lane_id is None:
                continue

            density = density_by_lane[lane_id].density if lane_id in density_by_lane else 0.0
            occupancy_percent = (
                occupancy_by_lane[lane_id].occupancy_percent if lane_id in occupancy_by_lane else 0.0
            )
            queue_length, avg_waiting_time = lane_metrics.get(lane_id, (0, 0.0))
            current_duration = timing.duration_seconds

            next_state: StateVector = [
                density, float(queue_length), avg_waiting_time, occupancy_percent, current_duration,
            ]

            previous_duration = self._previous_duration.get(junction_id)
            action = self._derive_action(previous_duration, current_duration)

            if junction_id in self._previous_state:
                is_congested = lane_id in congested_lanes
                reward = self._compute_reward(
                    avg_waiting_time=avg_waiting_time,
                    queue_length=queue_length,
                    is_congested=is_congested,
                    throughput_tick=throughput_tick,
                    action=action,
                )
                experience = RLExperience(
                    sim_time=sim_time,
                    junction_id=junction_id,
                    state=self._previous_state[junction_id],
                    action=action,
                    reward=reward,
                    next_state=next_state,
                    done=False,
                )
                experiences.append(experience)
                self._transition_count += 1

            self._previous_state[junction_id] = next_state
            self._previous_duration[junction_id] = current_duration

        return experiences

    def get_transition_count(self) -> int:
        """Total experiences produced so far (live in-memory counter)."""
        return self._transition_count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_action(previous_duration: float | None, current_duration: float) -> RLAction:
        if previous_duration is None or current_duration == previous_duration:
            return RLAction.KEEP_SAME
        if current_duration > previous_duration:
            return RLAction.INCREASE_GREEN
        return RLAction.DECREASE_GREEN

    @staticmethod
    def _compute_reward(
        avg_waiting_time: float,
        queue_length: int,
        is_congested: bool,
        throughput_tick: int,
        action: RLAction,
    ) -> float:
        reward = (
            -REWARD_WEIGHT_WAITING_TIME * avg_waiting_time
            - REWARD_WEIGHT_QUEUE_LENGTH * queue_length
            - REWARD_WEIGHT_CONGESTION * (1.0 if is_congested else 0.0)
            + REWARD_WEIGHT_THROUGHPUT * throughput_tick
            - REWARD_WEIGHT_SIGNAL_CHANGE * (0.0 if action == RLAction.KEEP_SAME else 1.0)
        )
        return round(reward, 4)

    @staticmethod
    def _compute_lane_metrics(vehicles: List[VehicleData]) -> Dict[str, Tuple[int, float]]:
        per_lane: Dict[str, List[VehicleData]] = {}
        for v in vehicles:
            per_lane.setdefault(v.lane_id, []).append(v)

        metrics: Dict[str, Tuple[int, float]] = {}
        for lane_id, lane_vehicles in per_lane.items():
            queue_length = sum(1 for v in lane_vehicles if v.speed < _QUEUE_SPEED_THRESHOLD_MS)
            avg_wait = sum(v.waiting_time for v in lane_vehicles) / len(lane_vehicles)
            metrics[lane_id] = (queue_length, avg_wait)
        return metrics
