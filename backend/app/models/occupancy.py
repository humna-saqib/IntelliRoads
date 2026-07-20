"""
IntelliRoads – Lane Occupancy Pydantic v2 models (Sprint 2).
"""

from __future__ import annotations

import time
from typing import List

from pydantic import BaseModel, Field

from app.models.density import DensityLevel


class LaneOccupancy(BaseModel):
    """Occupancy measurement for a single lane."""

    lane_id: str = Field(..., description="SUMO lane identifier")
    occupancy_percent: float = Field(
        ..., ge=0.0, le=100.0,
        description="Percentage of the lane's length covered by vehicles (raw, for RL)",
    )
    occupancy_level: DensityLevel = Field(..., description="Qualitative occupancy band")
    timestamp: float = Field(
        default_factory=time.time, description="Unix timestamp of this measurement"
    )

    model_config = {"use_enum_values": True}


class OccupancyResponse(BaseModel):
    """Aggregated occupancy data for all monitored lanes."""

    lanes: List[LaneOccupancy] = Field(default_factory=list)
    average_occupancy: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Mean occupancy percent across all lanes"
    )
    timestamp: float = Field(
        default_factory=time.time, description="Unix timestamp of this response"
    )
