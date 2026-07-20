"""
IntelliRoads – Emergency vehicle Pydantic v2 models (Sprint 2).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class EmergencyVehicleType(str, Enum):
    """Kind of emergency vehicle. All share SUMO vClass 'emergency'."""

    AMBULANCE = "AMBULANCE"
    POLICE = "POLICE"
    FIRETRUCK = "FIRETRUCK"
    UNKNOWN = "UNKNOWN"


class EmergencyVehicleState(BaseModel):
    """Current state of one active (currently-in-simulation) emergency vehicle."""

    vehicle_id: str = Field(..., description="Unique SUMO vehicle identifier")
    vehicle_type: EmergencyVehicleType = Field(..., description="Ambulance / police / firetruck")
    lane_id: str = Field(..., description="Lane the vehicle is currently on")
    junction_id: Optional[str] = Field(
        default=None, description="Junction the vehicle's lane feeds into, if known"
    )
    speed: float = Field(..., ge=0.0, description="Current speed in m/s")
    first_detected_at: float = Field(..., description="Unix timestamp this vehicle was first seen")
    last_seen_at: float = Field(..., description="Unix timestamp this vehicle was last seen")
    sim_time: float = Field(..., description="Simulation time of the last observation")

    model_config = {"use_enum_values": True}


class EmergencyEvent(BaseModel):
    """A loggable state transition: a vehicle appeared, changed intersection, or left."""

    vehicle_id: str = Field(..., description="Unique SUMO vehicle identifier")
    vehicle_type: EmergencyVehicleType = Field(..., description="Ambulance / police / firetruck")
    lane_id: str = Field(..., description="Lane the vehicle was on at event time")
    junction_id: Optional[str] = Field(
        default=None, description="Junction the vehicle's lane feeds into, if known"
    )
    event_type: str = Field(
        ..., description="One of 'DETECTED', 'INTERSECTION_CHANGE', 'CLEARED'"
    )
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of the event")
    sim_time: float = Field(..., description="Simulation time of the event")

    model_config = {"use_enum_values": True}


class EmergencyResponse(BaseModel):
    """Aggregated emergency-vehicle status for the dashboard/API."""

    active_vehicles: List[EmergencyVehicleState] = Field(default_factory=list)
    recent_events: List[EmergencyEvent] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of this response")


class PriorityOverrideEvent(BaseModel):
    """
    An emergency signal-priority activation or deactivation at a junction.

    Logged separately from normal signal_decisions history so
    density-based and emergency-driven control actions stay clearly
    distinguishable (important for later DQN training/evaluation).
    """

    junction_id: str = Field(..., description="Junction where the override activated/deactivated")
    vehicle_id: str = Field(..., description="Emergency vehicle that triggered the override")
    vehicle_type: EmergencyVehicleType = Field(..., description="Ambulance / police / firetruck")
    event_type: str = Field(..., description="One of 'ACTIVATED', 'DEACTIVATED'")
    normal_duration: Optional[float] = Field(
        default=None, description="The density-based green duration that was suspended, if known"
    )
    override_duration: Optional[float] = Field(
        default=None, description="The priority green duration applied while active"
    )
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of the event")
    sim_time: float = Field(..., description="Simulation time of the event")

    model_config = {"use_enum_values": True}
