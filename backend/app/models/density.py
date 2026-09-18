"""
IntelliRoads – Density Pydantic v2 models.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DensityLevel(str, Enum):
    """Qualitative traffic-density band."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class LaneDensity(BaseModel):
    """Density measurement for a single lane."""

    lane_id: str = Field(..., description="SUMO lane identifier")
    vehicle_count: int = Field(..., ge=0, description="Number of vehicles in the lane")
    lane_length_km: float = Field(
        ..., gt=0.0, description="Physical length of the lane in kilometres"
    )
    density: float = Field(
        ...,
        ge=0.0,
        description="Calculated density: vehicles / km",
    )
    level: DensityLevel = Field(..., description="Qualitative density band")
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of this measurement",
    )

    model_config = {"use_enum_values": True}


class DensityReading(BaseModel):
    """
    A single historical density reading row from the density_readings table.

    Returned by GET /density/history. Unlike the live LaneDensity model this
    carries sim_time, queue_length, and avg_waiting_time — the extra columns
    that _log_density_readings() persists but the live endpoint does not expose.
    """

    id: Optional[int] = Field(default=None, description="SQLite row ID")
    sim_time: float = Field(..., description="Simulation time of this reading")
    lane_id: str = Field(..., description="SUMO lane identifier")
    vehicle_count: int = Field(..., ge=0, description="Number of vehicles in the lane")
    density: float = Field(..., ge=0.0, description="Calculated density: vehicles / km")
    level: str = Field(..., description="Qualitative density band (LOW / MEDIUM / HIGH)")
    queue_length: int = Field(..., ge=0, description="Number of queued (near-stopped) vehicles")
    avg_waiting_time: float = Field(..., ge=0.0, description="Mean vehicle waiting time in this lane (s)")
    timestamp: float = Field(..., description="Unix timestamp when this reading was logged")


class DensityResponse(BaseModel):
    """Aggregated density data for all monitored lanes."""

    lanes: List[LaneDensity] = Field(default_factory=list)
    average_density: float = Field(
        default=0.0,
        ge=0.0,
        description="Mean density across all lanes",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of this response",
    )
