"""
IntelliRoads – Traffic-signal Pydantic v2 models.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.density import DensityLevel


class SignalPhaseType(str, Enum):
    """Traffic-light phase."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class SignalTiming(BaseModel):
    """Computed signal timing for a single junction."""

    junction_id: str = Field(..., description="SUMO traffic-light junction identifier")
    phase: SignalPhaseType = Field(..., description="Current (or target) signal phase")
    duration_seconds: float = Field(
        ..., gt=0.0, description="How long this phase should run (seconds)"
    )
    density_level: DensityLevel = Field(
        ..., description="Density level that produced this timing decision"
    )
    triggered_at: float = Field(
        default_factory=time.time,
        description="Unix timestamp when this timing was computed",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation of why this timing was chosen",
    )
    priority_override: bool = Field(
        default=False,
        description="True when this timing was forced by Emergency Vehicle Priority Control",
    )
    emergency_vehicle_id: Optional[str] = Field(
        default=None,
        description="Vehicle ID that triggered the priority override, if any",
    )
    emergency_vehicle_type: Optional[str] = Field(
        default=None,
        description="AMBULANCE / POLICE / FIRETRUCK that triggered the priority override, if any",
    )

    model_config = {"use_enum_values": True}


class SignalResponse(BaseModel):
    """Current signal timings for all monitored junctions."""

    signals: List[SignalTiming] = Field(default_factory=list)
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of this response",
    )
