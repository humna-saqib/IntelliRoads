"""
IntelliRoads – SQLite database connection management (Sprint 2).

Owns the single aiosqlite connection used to persist simulation
telemetry, and creates the schema (tables + indexes) on first connect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiosqlite

from app.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH: Path = Path(__file__).resolve().parent.parent.parent / "data" / "intelliroads.db"

# ---------------------------------------------------------------------------
# Schema
#
# - vehicle_counts / density_readings: logged every simulation tick.
# - signal_decisions: logged only when the computed decision changes,
#   with the density/queue/wait state that produced it (state-action
#   pair for future RL training).
# - congestion_events: logged only on CLEAR<->CONGESTED transitions.
# - occupancy_readings: logged every tick by OccupancyCalculator (real
#   TraCI getLastStepOccupancy() in live mode, derived estimate in mock
#   mode) — purely observational, not read by signal control.
# - emergency_events: logged only on DETECTED / INTERSECTION_CHANGE /
#   CLEARED transitions (never per-tick) by EmergencyVehicleDetector.
# - emergency_priority_events: ACTIVATED/DEACTIVATED transitions from
#   EmergencyPriorityController. Kept separate from signal_decisions so
#   normal density-based control history stays pure and distinguishable
#   from emergency-override history (important for later DQN training).
# - performance_metrics: logged every tick by PerformanceMetricsService —
#   observational analytics on controller/system performance, used later
#   to compare the rule-based controller against the DQN controller.
# - rl_experiences: (state, action, reward, next_state) transitions from
#   RLEnvironment — observational only, the rule-based controller stays
#   fully in control.
# - dqn_training_stats: per-epoch training metrics from the standalone
#   offline train_dqn.py script (not written by the live backend).
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicle_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    lane_id TEXT NOT NULL,
    vehicle_count INTEGER NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vehicle_counts_timestamp ON vehicle_counts(timestamp);
CREATE INDEX IF NOT EXISTS idx_vehicle_counts_sim_time ON vehicle_counts(sim_time);
CREATE INDEX IF NOT EXISTS idx_vehicle_counts_lane_id ON vehicle_counts(lane_id);

CREATE TABLE IF NOT EXISTS density_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    lane_id TEXT NOT NULL,
    vehicle_count INTEGER NOT NULL,
    density REAL NOT NULL,
    level TEXT NOT NULL,
    queue_length INTEGER NOT NULL,
    avg_waiting_time REAL NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_density_readings_timestamp ON density_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_density_readings_sim_time ON density_readings(sim_time);
CREATE INDEX IF NOT EXISTS idx_density_readings_lane_id ON density_readings(lane_id);

CREATE TABLE IF NOT EXISTS signal_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    junction_id TEXT NOT NULL,
    lane_id TEXT,
    old_duration REAL,
    new_duration REAL NOT NULL,
    action TEXT NOT NULL,
    density_level TEXT NOT NULL,
    density REAL NOT NULL,
    queue_length INTEGER NOT NULL,
    avg_waiting_time REAL NOT NULL,
    reason TEXT,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_timestamp ON signal_decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_sim_time ON signal_decisions(sim_time);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_junction_id ON signal_decisions(junction_id);

CREATE TABLE IF NOT EXISTS congestion_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    intersection_id TEXT NOT NULL,
    direction TEXT,
    status TEXT NOT NULL,
    density_value REAL NOT NULL,
    threshold REAL NOT NULL,
    timestamp REAL NOT NULL,
    resolved_at REAL
);
CREATE INDEX IF NOT EXISTS idx_congestion_events_timestamp ON congestion_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_congestion_events_sim_time ON congestion_events(sim_time);
CREATE INDEX IF NOT EXISTS idx_congestion_events_intersection_id ON congestion_events(intersection_id);

CREATE TABLE IF NOT EXISTS occupancy_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    lane_id TEXT NOT NULL,
    occupancy_percent REAL NOT NULL,
    occupancy_level TEXT NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_occupancy_readings_timestamp ON occupancy_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_occupancy_readings_sim_time ON occupancy_readings(sim_time);
CREATE INDEX IF NOT EXISTS idx_occupancy_readings_lane_id ON occupancy_readings(lane_id);

CREATE TABLE IF NOT EXISTS emergency_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    vehicle_id TEXT NOT NULL,
    vehicle_type TEXT NOT NULL,
    lane_id TEXT NOT NULL,
    junction_id TEXT,
    event_type TEXT NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emergency_events_timestamp ON emergency_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_emergency_events_sim_time ON emergency_events(sim_time);
CREATE INDEX IF NOT EXISTS idx_emergency_events_junction_id ON emergency_events(junction_id);
CREATE INDEX IF NOT EXISTS idx_emergency_events_vehicle_id ON emergency_events(vehicle_id);

CREATE TABLE IF NOT EXISTS emergency_priority_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    junction_id TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    vehicle_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    normal_duration REAL,
    override_duration REAL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emergency_priority_events_timestamp ON emergency_priority_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_emergency_priority_events_sim_time ON emergency_priority_events(sim_time);
CREATE INDEX IF NOT EXISTS idx_emergency_priority_events_junction_id ON emergency_priority_events(junction_id);

CREATE TABLE IF NOT EXISTS performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    avg_waiting_time REAL NOT NULL,
    avg_queue_length REAL NOT NULL,
    avg_occupancy REAL NOT NULL,
    throughput_total INTEGER NOT NULL,
    throughput_tick INTEGER NOT NULL,
    congestion_event_count INTEGER NOT NULL,
    emergency_priority_activations INTEGER NOT NULL,
    signal_decision_frequency INTEGER NOT NULL,
    controller_response_time_ms REAL NOT NULL,
    tick_processing_time_ms REAL NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_timestamp ON performance_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_sim_time ON performance_metrics(sim_time);

CREATE TABLE IF NOT EXISTS rl_experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_time REAL NOT NULL,
    junction_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    action TEXT NOT NULL,
    reward REAL NOT NULL,
    next_state_json TEXT NOT NULL,
    done INTEGER NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rl_experiences_timestamp ON rl_experiences(timestamp);
CREATE INDEX IF NOT EXISTS idx_rl_experiences_sim_time ON rl_experiences(sim_time);
CREATE INDEX IF NOT EXISTS idx_rl_experiences_junction_id ON rl_experiences(junction_id);

CREATE TABLE IF NOT EXISTS dqn_training_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    epoch INTEGER NOT NULL,
    avg_loss REAL NOT NULL,
    avg_q_value REAL NOT NULL,
    avg_reward REAL NOT NULL,
    epsilon REAL NOT NULL,
    buffer_size INTEGER NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dqn_training_stats_epoch ON dqn_training_stats(epoch);
CREATE INDEX IF NOT EXISTS idx_dqn_training_stats_timestamp ON dqn_training_stats(timestamp);
"""


class Database:
    """Owns the single aiosqlite connection used by the simulation loop."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    async def connect(self) -> None:
        """Open the connection, enable WAL mode, and ensure the schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        logger.info(f"SQLite database connected at {self.db_path}")

    async def close(self) -> None:
        """Close the connection if open."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("SQLite database connection closed.")
