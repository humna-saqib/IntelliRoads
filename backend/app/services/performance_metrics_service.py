"""
IntelliRoads – Response Optimization Metrics service (Sprint 2).

Purely observational analytics layer: measures and logs how well the
current rule-based controller and emergency-priority system are
performing, without reading from or influencing either. Intended to
give a quantitative baseline the future DQN controller can later be
compared against.

Throughput uses TraCI's own getArrivedNumber() in live mode (the
authoritative count of vehicles that completed their route this step);
mock mode has no TraCI to query, so it falls back to tracking which
vehicle IDs disappeared between ticks.
"""

from __future__ import annotations

import time
from typing import Dict, List

from app.models.congestion import CongestionResponse
from app.models.density import DensityResponse
from app.models.emergency import PriorityOverrideEvent
from app.models.occupancy import OccupancyResponse
from app.models.performance import PerformanceSnapshot
from app.models.signal import SignalTiming
from app.models.vehicle import VehicleData
from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger

if SUMO_AVAILABLE:
    import traci  # type: ignore

logger = get_logger(__name__)

# Vehicles slower than this are considered queued – matches the
# near-stopped convention used elsewhere (db_logger, kpi history).
_QUEUE_SPEED_THRESHOLD_MS: float = 2.0


class PerformanceMetricsService:
    """
    Tracks controller/system performance metrics every simulation tick.

    Parameters
    ----------
    session : TraCISession
        Used only to check mock-mode and, in live mode, to read
        ``traci.simulation.getArrivedNumber()`` for throughput.
    """

    def __init__(self, session: TraCISession) -> None:
        self._session = session
        self._throughput_total = 0
        self._congestion_event_count = 0
        self._emergency_priority_activations = 0
        self._signal_decision_frequency = 0
        self._prev_vehicle_ids: set[str] = set()
        self._seen_first_tick = False
        self._last_congestion_status: Dict[str, str] = {}
        self._last_signal_duration: Dict[str, float] = {}
        logger.info("PerformanceMetricsService initialised.")

    @property
    def mock_mode(self) -> bool:
        return self._session.mock_mode

    # ------------------------------------------------------------------
    # Public API – called once per simulation tick
    # ------------------------------------------------------------------

    def record_tick(
        self,
        sim_time: float,
        vehicles: List[VehicleData],
        density_response: DensityResponse,
        occupancy_response: OccupancyResponse,
        congestion_response: CongestionResponse,
        normal_signals: List[SignalTiming],
        priority_events: List[PriorityOverrideEvent],
        controller_response_time_ms: float,
        tick_processing_time_ms: float,
    ) -> PerformanceSnapshot:
        """Compute and return this tick's performance snapshot, updating running counters."""
        throughput_tick = self._compute_throughput_tick(vehicles)
        self._throughput_total += throughput_tick

        avg_waiting_time, avg_queue_length = self._compute_queue_and_wait(vehicles)
        self._update_congestion_counter(congestion_response)
        self._update_signal_decision_counter(normal_signals)

        activations_this_tick = sum(1 for e in priority_events if e.event_type == "ACTIVATED")
        self._emergency_priority_activations += activations_this_tick

        return PerformanceSnapshot(
            sim_time=sim_time,
            avg_waiting_time=round(avg_waiting_time, 2),
            avg_queue_length=round(avg_queue_length, 2),
            avg_occupancy=occupancy_response.average_occupancy,
            throughput_total=self._throughput_total,
            throughput_tick=throughput_tick,
            congestion_event_count=self._congestion_event_count,
            emergency_priority_activations=self._emergency_priority_activations,
            signal_decision_frequency=self._signal_decision_frequency,
            controller_response_time_ms=round(controller_response_time_ms, 3),
            tick_processing_time_ms=round(tick_processing_time_ms, 3),
            timestamp=time.time(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_throughput_tick(self, vehicles: List[VehicleData]) -> int:
        """Vehicles that completed/left the simulation this tick."""
        if not self.mock_mode:
            try:
                return int(traci.simulation.getArrivedNumber())
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"getArrivedNumber() failed: {exc}")
                return 0

        # Mock mode: no TraCI arrival count – infer from vehicle IDs that
        # disappeared since last tick. Skip the very first tick since
        # there's no prior snapshot to diff against.
        current_ids = {v.vehicle_id for v in vehicles}
        if not self._seen_first_tick:
            self._seen_first_tick = True
            self._prev_vehicle_ids = current_ids
            return 0
        completed = self._prev_vehicle_ids - current_ids
        self._prev_vehicle_ids = current_ids
        return len(completed)

    @staticmethod
    def _compute_queue_and_wait(vehicles: List[VehicleData]) -> tuple[float, float]:
        if not vehicles:
            return 0.0, 0.0

        avg_waiting_time = sum(v.waiting_time for v in vehicles) / len(vehicles)

        per_lane: Dict[str, List[VehicleData]] = {}
        for v in vehicles:
            per_lane.setdefault(v.lane_id, []).append(v)
        queue_lengths = [
            sum(1 for v in lane_vehicles if v.speed < _QUEUE_SPEED_THRESHOLD_MS)
            for lane_vehicles in per_lane.values()
        ]
        avg_queue_length = sum(queue_lengths) / len(queue_lengths) if queue_lengths else 0.0
        return avg_waiting_time, avg_queue_length

    def _update_congestion_counter(self, congestion_response: CongestionResponse) -> None:
        for event in congestion_response.events:
            status = event.status if isinstance(event.status, str) else event.status.value
            previous = self._last_congestion_status.get(event.intersection_id)
            if status == "CONGESTED" and previous != "CONGESTED":
                self._congestion_event_count += 1
            self._last_congestion_status[event.intersection_id] = status

    def _update_signal_decision_counter(self, normal_signals: List[SignalTiming]) -> None:
        for timing in normal_signals:
            previous_duration = self._last_signal_duration.get(timing.junction_id)
            if previous_duration is None or previous_duration != timing.duration_seconds:
                self._signal_decision_frequency += 1
            self._last_signal_duration[timing.junction_id] = timing.duration_seconds
