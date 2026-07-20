"""
IntelliRoads – Database logging service (Sprint 2).

Persists simulation telemetry into SQLite each tick so historical data
is available for analysis and, later, DQN training. Vehicle counts and
density/queue/wait metrics are logged every tick; signal decisions
only when the computed decision actually changes; congestion events
only on CLEAR<->CONGESTED transitions.
"""

from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Tuple

from app.core.database import Database
from app.models.congestion import CongestionResponse
from app.models.density import DensityResponse
from app.models.emergency import EmergencyEvent, PriorityOverrideEvent
from app.models.occupancy import OccupancyResponse
from app.models.performance import PerformanceSnapshot, PerformanceSummary
from app.models.rl import RLExperience, RLStats, STATE_FEATURE_NAMES
from app.models.signal import SignalResponse
from app.models.vehicle import VehicleData
from app.services.signal_controller import _LANE_TO_JUNCTION
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Vehicles slower than this are considered queued – matches the
# near-stopped convention used elsewhere for wait-time estimation.
_QUEUE_SPEED_THRESHOLD_MS: float = 2.0

LaneMetrics = Dict[str, Tuple[int, float]]  # lane_id -> (queue_length, avg_waiting_time)


class DBLogger:
    """Writes one row set per simulation tick to the SQLite database."""

    def __init__(self, db: Database) -> None:
        self._db = db
        # Last-written green-phase duration per junction, to detect
        # real decision changes (avoids a row every tick).
        self._last_signal_duration: Dict[str, float] = {}
        # Last-known congestion status per intersection, to detect
        # CLEAR<->CONGESTED transitions.
        self._last_congestion_status: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API – called once per simulation tick
    # ------------------------------------------------------------------

    async def log_tick(
        self,
        sim_time: float,
        vehicles: List[VehicleData],
        density_response: DensityResponse,
        congestion_response: CongestionResponse,
        signals_response: SignalResponse,
        occupancy_response: Optional[OccupancyResponse] = None,
    ) -> None:
        """Persist one simulation tick's worth of telemetry."""
        ts = time.time()
        lane_metrics = self._compute_lane_metrics(vehicles)

        await self._log_vehicle_counts(sim_time, density_response, ts)
        await self._log_density_readings(sim_time, density_response, lane_metrics, ts)
        await self._log_signal_decisions(sim_time, signals_response, density_response, lane_metrics, ts)
        await self._log_congestion_events(sim_time, congestion_response, ts)
        if occupancy_response is not None:
            await self._log_occupancy_readings(sim_time, occupancy_response, ts)
        await self._db.connection.commit()

    async def log_emergency_events(self, events: List[EmergencyEvent]) -> None:
        """
        Persist emergency-vehicle events (DETECTED / INTERSECTION_CHANGE /
        CLEARED). Callers only need to pass events for ticks where a real
        transition happened — :class:`EmergencyVehicleDetector` already
        guarantees that, so no extra dedup is needed here.
        """
        if not events:
            return
        rows = [
            (
                e.sim_time, e.vehicle_id,
                e.vehicle_type if isinstance(e.vehicle_type, str) else e.vehicle_type.value,
                e.lane_id, e.junction_id,
                e.event_type, e.timestamp,
            )
            for e in events
        ]
        await self._db.connection.executemany(
            "INSERT INTO emergency_events "
            "(sim_time, vehicle_id, vehicle_type, lane_id, junction_id, event_type, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        await self._db.connection.commit()

    async def log_priority_events(self, events: List[PriorityOverrideEvent]) -> None:
        """
        Persist emergency signal-priority ACTIVATED/DEACTIVATED events.
        Kept in a dedicated table, separate from signal_decisions, so
        normal density-based control history and emergency-override
        history stay clearly distinguishable for later DQN training.
        """
        if not events:
            return
        rows = [
            (
                e.sim_time, e.junction_id, e.vehicle_id,
                e.vehicle_type if isinstance(e.vehicle_type, str) else e.vehicle_type.value,
                e.event_type, e.normal_duration, e.override_duration, e.timestamp,
            )
            for e in events
        ]
        await self._db.connection.executemany(
            "INSERT INTO emergency_priority_events "
            "(sim_time, junction_id, vehicle_id, vehicle_type, event_type, "
            " normal_duration, override_duration, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        await self._db.connection.commit()

    async def log_performance_metrics(self, snapshot: PerformanceSnapshot) -> None:
        """Persist one tick's Response Optimization Metrics snapshot."""
        await self._db.connection.execute(
            "INSERT INTO performance_metrics "
            "(sim_time, avg_waiting_time, avg_queue_length, avg_occupancy, "
            " throughput_total, throughput_tick, congestion_event_count, "
            " emergency_priority_activations, signal_decision_frequency, "
            " controller_response_time_ms, tick_processing_time_ms, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot.sim_time, snapshot.avg_waiting_time, snapshot.avg_queue_length,
                snapshot.avg_occupancy, snapshot.throughput_total, snapshot.throughput_tick,
                snapshot.congestion_event_count, snapshot.emergency_priority_activations,
                snapshot.signal_decision_frequency, snapshot.controller_response_time_ms,
                snapshot.tick_processing_time_ms, snapshot.timestamp,
            ),
        )
        await self._db.connection.commit()

    # ------------------------------------------------------------------
    # Performance aggregation queries – read-side, for /api/performance.
    # Windowed totals for the three cumulative counters (congestion,
    # emergency activations, signal decisions) use MAX-MIN within the
    # window: since those columns are monotonically increasing running
    # totals, that delta is the count of new events within the window.
    # throughput_tick is already a per-tick delta, so it's summed directly.
    # ------------------------------------------------------------------

    _SUMMARY_SELECT = """
        SELECT
            COUNT(*) AS sample_count,
            AVG(avg_waiting_time) AS avg_waiting_time,
            AVG(avg_queue_length) AS avg_queue_length,
            AVG(avg_occupancy) AS avg_occupancy,
            SUM(throughput_tick) AS total_throughput,
            MAX(congestion_event_count) - MIN(congestion_event_count) AS total_congestion_events,
            MAX(emergency_priority_activations) - MIN(emergency_priority_activations) AS total_emergency_activations,
            MAX(signal_decision_frequency) - MIN(signal_decision_frequency) AS total_signal_decisions,
            AVG(controller_response_time_ms) AS avg_controller_response_time_ms,
            AVG(tick_processing_time_ms) AS avg_tick_processing_time_ms,
            MIN(sim_time) AS start_sim_time,
            MAX(sim_time) AS end_sim_time
        FROM performance_metrics
    """

    async def get_minute_summary(self, limit: int = 60) -> List[PerformanceSummary]:
        """
        Aggregate performance metrics into simulation-time-minute buckets
        (not wall-clock minutes, since sim speed can vary independently
        of real time). Returns the most recent *limit* minutes, oldest first.
        """
        grouped_query = """
            SELECT
                CAST(sim_time / 60 AS INTEGER) AS minute_bucket,
                COUNT(*) AS sample_count,
                AVG(avg_waiting_time) AS avg_waiting_time,
                AVG(avg_queue_length) AS avg_queue_length,
                AVG(avg_occupancy) AS avg_occupancy,
                SUM(throughput_tick) AS total_throughput,
                MAX(congestion_event_count) - MIN(congestion_event_count) AS total_congestion_events,
                MAX(emergency_priority_activations) - MIN(emergency_priority_activations) AS total_emergency_activations,
                MAX(signal_decision_frequency) - MIN(signal_decision_frequency) AS total_signal_decisions,
                AVG(controller_response_time_ms) AS avg_controller_response_time_ms,
                AVG(tick_processing_time_ms) AS avg_tick_processing_time_ms,
                MIN(sim_time) AS start_sim_time,
                MAX(sim_time) AS end_sim_time
            FROM performance_metrics
            GROUP BY minute_bucket
            ORDER BY minute_bucket DESC
            LIMIT ?
        """
        cursor = await self._db.connection.execute(grouped_query, (limit,))
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        summaries = [
            PerformanceSummary(
                period_label=f"minute_{int(row_dict['minute_bucket'])}",
                sample_count=row_dict["sample_count"],
                avg_waiting_time=round(row_dict["avg_waiting_time"] or 0.0, 2),
                avg_queue_length=round(row_dict["avg_queue_length"] or 0.0, 2),
                avg_occupancy=round(row_dict["avg_occupancy"] or 0.0, 2),
                total_throughput=row_dict["total_throughput"] or 0,
                total_congestion_events=row_dict["total_congestion_events"] or 0,
                total_emergency_activations=row_dict["total_emergency_activations"] or 0,
                total_signal_decisions=row_dict["total_signal_decisions"] or 0,
                avg_controller_response_time_ms=round(row_dict["avg_controller_response_time_ms"] or 0.0, 3),
                avg_tick_processing_time_ms=round(row_dict["avg_tick_processing_time_ms"] or 0.0, 3),
                start_sim_time=row_dict["start_sim_time"] or 0.0,
                end_sim_time=row_dict["end_sim_time"] or 0.0,
            )
            for row_dict in (dict(zip(columns, r)) for r in rows)
        ]
        return list(reversed(summaries))  # oldest first

    async def get_simulation_summary(self) -> Optional[PerformanceSummary]:
        """Aggregate performance metrics across the entire simulation run so far."""
        cursor = await self._db.connection.execute(self._SUMMARY_SELECT)
        row = await cursor.fetchone()
        if row is None or row[0] == 0:
            return None
        columns = [d[0] for d in cursor.description]
        row_dict = dict(zip(columns, row))
        return PerformanceSummary(
            period_label="simulation_total",
            sample_count=row_dict["sample_count"],
            avg_waiting_time=round(row_dict["avg_waiting_time"] or 0.0, 2),
            avg_queue_length=round(row_dict["avg_queue_length"] or 0.0, 2),
            avg_occupancy=round(row_dict["avg_occupancy"] or 0.0, 2),
            total_throughput=row_dict["total_throughput"] or 0,
            total_congestion_events=row_dict["total_congestion_events"] or 0,
            total_emergency_activations=row_dict["total_emergency_activations"] or 0,
            total_signal_decisions=row_dict["total_signal_decisions"] or 0,
            avg_controller_response_time_ms=round(row_dict["avg_controller_response_time_ms"] or 0.0, 3),
            avg_tick_processing_time_ms=round(row_dict["avg_tick_processing_time_ms"] or 0.0, 3),
            start_sim_time=row_dict["start_sim_time"] or 0.0,
            end_sim_time=row_dict["end_sim_time"] or 0.0,
        )

    async def log_rl_experiences(self, experiences: List[RLExperience]) -> None:
        """Persist RL (state, action, reward, next_state) transitions."""
        if not experiences:
            return
        rows = [
            (
                e.sim_time, e.junction_id, json.dumps(e.state),
                e.action if isinstance(e.action, str) else e.action.value,
                e.reward, json.dumps(e.next_state), int(e.done), e.timestamp,
            )
            for e in experiences
        ]
        await self._db.connection.executemany(
            "INSERT INTO rl_experiences "
            "(sim_time, junction_id, state_json, action, reward, next_state_json, done, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        await self._db.connection.commit()

    async def get_rl_stats(self) -> RLStats:
        """
        Evaluation utility: inspect collected state vectors, rewards, and
        transition counts across all RL experiences stored so far.
        """
        cursor = await self._db.connection.execute(
            "SELECT action, reward, state_json FROM rl_experiences"
        )
        rows = await cursor.fetchall()

        if not rows:
            return RLStats(
                transition_count=0, reward_min=0.0, reward_max=0.0, reward_mean=0.0,
                action_distribution={}, state_feature_stats={},
            )

        action_distribution: Dict[str, int] = {}
        rewards: List[float] = []
        feature_values: Dict[str, List[float]] = {name: [] for name in STATE_FEATURE_NAMES}

        for action, reward, state_json in rows:
            action_distribution[action] = action_distribution.get(action, 0) + 1
            rewards.append(reward)
            try:
                state = json.loads(state_json)
                for name, value in zip(STATE_FEATURE_NAMES, state):
                    feature_values[name].append(value)
            except (json.JSONDecodeError, TypeError):
                continue

        state_feature_stats = {
            name: {
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "mean": round(sum(values) / len(values), 3),
            }
            for name, values in feature_values.items()
            if values
        }

        return RLStats(
            transition_count=len(rows),
            reward_min=round(min(rewards), 4),
            reward_max=round(max(rewards), 4),
            reward_mean=round(sum(rewards) / len(rewards), 4),
            action_distribution=action_distribution,
            state_feature_stats=state_feature_stats,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_lane_metrics(self, vehicles: List[VehicleData]) -> LaneMetrics:
        """
        Return {lane_id: (queue_length, avg_waiting_time)} — the queue
        length and waiting-time features the future RL state space needs,
        computed from live per-vehicle telemetry.
        """
        per_lane: Dict[str, List[VehicleData]] = {}
        for v in vehicles:
            per_lane.setdefault(v.lane_id, []).append(v)

        metrics: LaneMetrics = {}
        for lane_id, lane_vehicles in per_lane.items():
            queue_length = sum(1 for v in lane_vehicles if v.speed < _QUEUE_SPEED_THRESHOLD_MS)
            avg_wait = sum(v.waiting_time for v in lane_vehicles) / len(lane_vehicles)
            metrics[lane_id] = (queue_length, avg_wait)
        return metrics

    async def _log_vehicle_counts(
        self, sim_time: float, density_response: DensityResponse, ts: float
    ) -> None:
        rows = [
            (sim_time, lane.lane_id, lane.vehicle_count, ts)
            for lane in density_response.lanes
        ]
        if not rows:
            return
        await self._db.connection.executemany(
            "INSERT INTO vehicle_counts (sim_time, lane_id, vehicle_count, timestamp) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )

    async def _log_occupancy_readings(
        self, sim_time: float, occupancy_response: OccupancyResponse, ts: float
    ) -> None:
        rows = [
            (
                sim_time, lane.lane_id, lane.occupancy_percent,
                lane.occupancy_level if isinstance(lane.occupancy_level, str) else lane.occupancy_level.value,
                ts,
            )
            for lane in occupancy_response.lanes
        ]
        if not rows:
            return
        await self._db.connection.executemany(
            "INSERT INTO occupancy_readings "
            "(sim_time, lane_id, occupancy_percent, occupancy_level, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )

    async def _log_density_readings(
        self,
        sim_time: float,
        density_response: DensityResponse,
        lane_metrics: LaneMetrics,
        ts: float,
    ) -> None:
        rows = []
        for lane in density_response.lanes:
            queue_length, avg_wait = lane_metrics.get(lane.lane_id, (0, 0.0))
            level = lane.level if isinstance(lane.level, str) else lane.level.value
            rows.append((
                sim_time, lane.lane_id, lane.vehicle_count, lane.density, level,
                queue_length, avg_wait, ts,
            ))
        if not rows:
            return
        await self._db.connection.executemany(
            "INSERT INTO density_readings "
            "(sim_time, lane_id, vehicle_count, density, level, queue_length, avg_waiting_time, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    async def _log_signal_decisions(
        self,
        sim_time: float,
        signals_response: SignalResponse,
        density_response: DensityResponse,
        lane_metrics: LaneMetrics,
        ts: float,
    ) -> None:
        density_by_lane = {lane.lane_id: lane for lane in density_response.lanes}

        for lane_id, junction_id in _LANE_TO_JUNCTION.items():
            timing = next(
                (s for s in signals_response.signals if s.junction_id == junction_id), None
            )
            if timing is None:
                continue

            new_duration = timing.duration_seconds
            old_duration = self._last_signal_duration.get(junction_id)

            if old_duration is not None and new_duration == old_duration:
                continue  # No real decision change – skip logging this tick.

            if old_duration is None:
                action = "INITIAL"
            elif new_duration > old_duration:
                action = "INCREASE_GREEN"
            elif new_duration < old_duration:
                action = "DECREASE_GREEN"
            else:
                action = "KEEP_SAME"

            lane_density = density_by_lane.get(lane_id)
            queue_length, avg_wait = lane_metrics.get(lane_id, (0, 0.0))
            density_level = (
                lane_density.level if lane_density and isinstance(lane_density.level, str)
                else (lane_density.level.value if lane_density else "")
            )

            await self._db.connection.execute(
                "INSERT INTO signal_decisions "
                "(sim_time, junction_id, lane_id, old_duration, new_duration, action, "
                " density_level, density, queue_length, avg_waiting_time, reason, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sim_time, junction_id, lane_id, old_duration, new_duration, action,
                    density_level, lane_density.density if lane_density else 0.0,
                    queue_length, avg_wait, timing.reason, ts,
                ),
            )
            self._last_signal_duration[junction_id] = new_duration

    async def _log_congestion_events(
        self, sim_time: float, congestion_response: CongestionResponse, ts: float
    ) -> None:
        for event in congestion_response.events:
            status = event.status if isinstance(event.status, str) else event.status.value
            previous_status = self._last_congestion_status.get(event.intersection_id)

            if previous_status == status:
                continue  # No transition – skip logging this tick.

            if previous_status is not None or status == "CONGESTED":
                # Log CLEAR->CONGESTED (start) and CONGESTED->CLEAR (resolved),
                # but not the very first CLEAR baseline reading (no event yet).
                await self._db.connection.execute(
                    "INSERT INTO congestion_events "
                    "(sim_time, intersection_id, direction, status, density_value, "
                    " threshold, timestamp, resolved_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sim_time, event.intersection_id, event.direction, status,
                        event.density_value, event.threshold, ts, event.resolved_at,
                    ),
                )

            self._last_congestion_status[event.intersection_id] = status
