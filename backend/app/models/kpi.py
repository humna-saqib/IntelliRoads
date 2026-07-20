"""
IntelliRoads – KPI Pydantic v2 model.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field


class KPIData(BaseModel):
    """Key performance indicators snapshot for the running simulation."""

    total_vehicles: int = Field(
        ..., ge=0, description="Total number of vehicles currently in the simulation"
    )
    active_intersections: int = Field(
        ..., ge=0, description="Number of intersections being actively monitored"
    )
    average_speed: float = Field(
        ..., ge=0.0, description="Mean vehicle speed across all lanes (m/s)"
    )
    average_wait_time: float = Field(
        ..., ge=0.0, description="Estimated mean wait time for near-stopped vehicles (s)"
    )
    active_alerts: int = Field(
        ..., ge=0, description="Number of currently active congestion alerts"
    )
    congestion_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of monitored lanes that are congested",
    )
    simulation_time: float = Field(
        ..., ge=0.0, description="Current SUMO simulation time (seconds from start)"
    )
    data_source: str = Field(
        default="MOCK",
        description="'LIVE' when sourced from a real connected SUMO/TraCI session, 'MOCK' otherwise",
    )
    fetch_latency_ms: float = Field(
        default=0.0, ge=0.0, description="Last TraCI vehicle-data fetch latency in milliseconds (VDC-03)"
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when these KPIs were computed",
    )
