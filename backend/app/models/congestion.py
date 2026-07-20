"""
IntelliRoads – Congestion Pydantic v2 models.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CongestionStatus(str, Enum):
    """Whether a monitored intersection is currently congested."""

    CLEAR = "CLEAR"
    CONGESTED = "CONGESTED"


class CongestionEvent(BaseModel):
    """A congestion event recorded for a specific intersection / lane."""

    intersection_id: str = Field(
        ..., description="Identifier of the affected intersection or lane"
    )
    status: CongestionStatus = Field(..., description="Current congestion status")
    density_value: float = Field(
        ..., ge=0.0, description="Density reading that triggered this event (veh/km)"
    )
    threshold: float = Field(
        ..., gt=0.0, description="Density threshold above which CONGESTED is declared"
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when the event was first detected",
    )
    resolved_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp when congestion was cleared (None if still active)",
    )
    direction: Optional[str] = Field(
        default=None,
        description="Compass direction (N/S/E/W) of the congested lane's approach, if known",
    )

    model_config = {"use_enum_values": True}


class CongestionResponse(BaseModel):
    """Aggregated congestion status for all monitored intersections."""

    events: List[CongestionEvent] = Field(default_factory=list)
    total_congested: int = Field(
        default=0,
        ge=0,
        description="Number of intersections currently in CONGESTED state",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of this response",
    )
