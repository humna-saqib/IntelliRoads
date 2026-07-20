"""
IntelliRoads – Response Optimization Metrics Pydantic v2 models (Sprint 2).
"""

from __future__ import annotations

import time
from typing import List, Optional

from pydantic import BaseModel, Field


class PerformanceSnapshot(BaseModel):
    """Controller/system performance metrics for a single simulation tick."""

    sim_time: float = Field(..., description="Simulation time of this snapshot")
    avg_waiting_time: float = Field(..., ge=0.0, description="Mean vehicle waiting time (s)")
    avg_queue_length: float = Field(..., ge=0.0, description="Mean queued vehicles per lane")
    avg_occupancy: float = Field(..., ge=0.0, le=100.0, description="Mean lane occupancy (%)")
    throughput_total: int = Field(
        ..., ge=0, description="Cumulative vehicles that have completed/left the simulation"
    )
    throughput_tick: int = Field(..., ge=0, description="Vehicles completed this tick")
    congestion_event_count: int = Field(
        ..., ge=0, description="Cumulative count of CLEAR->CONGESTED transitions"
    )
    emergency_priority_activations: int = Field(
        ..., ge=0, description="Cumulative count of emergency priority ACTIVATED events"
    )
    signal_decision_frequency: int = Field(
        ..., ge=0, description="Cumulative count of real (changed) signal decisions"
    )
    controller_response_time_ms: float = Field(
        ..., ge=0.0, description="Wall time for signal + priority control decisions this tick"
    )
    tick_processing_time_ms: float = Field(
        ..., ge=0.0, description="Total simulation loop processing time this tick"
    )
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of this snapshot")


class PerformanceSummary(BaseModel):
    """Aggregated performance metrics over a time window (per-minute or whole-simulation)."""

    period_label: str = Field(..., description="e.g. 'minute_0', 'simulation_total'")
    sample_count: int = Field(..., ge=0, description="Number of ticks aggregated")
    avg_waiting_time: float = Field(..., ge=0.0)
    avg_queue_length: float = Field(..., ge=0.0)
    avg_occupancy: float = Field(..., ge=0.0, le=100.0)
    total_throughput: int = Field(..., ge=0, description="Vehicles completed within this window")
    total_congestion_events: int = Field(..., ge=0)
    total_emergency_activations: int = Field(..., ge=0)
    total_signal_decisions: int = Field(..., ge=0)
    avg_controller_response_time_ms: float = Field(..., ge=0.0)
    avg_tick_processing_time_ms: float = Field(..., ge=0.0)
    start_sim_time: float = Field(..., ge=0.0)
    end_sim_time: float = Field(..., ge=0.0)


class PerformanceResponse(BaseModel):
    """Full performance payload for the API/dashboard."""

    current: Optional[PerformanceSnapshot] = None
    per_minute: List[PerformanceSummary] = Field(default_factory=list)
    simulation_summary: Optional[PerformanceSummary] = None
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of this response")
