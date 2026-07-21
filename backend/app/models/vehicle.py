"""
IntelliRoads – Vehicle Pydantic v2 models.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator


class VehicleType(str, Enum):
    """Classification of a simulated vehicle."""

    CAR = "CAR"
    MOTORCYCLE = "MOTORCYCLE"
    BUS = "BUS"
    EMERGENCY = "EMERGENCY"
    UNKNOWN = "UNKNOWN"


class VehicleData(BaseModel):
    """Single vehicle snapshot as reported by TraCI / mock data."""

    vehicle_id: str = Field(..., description="Unique SUMO vehicle identifier")
    speed: float = Field(..., ge=0.0, description="Current speed in m/s")
    lane_id: str = Field(..., description="Lane the vehicle is currently on")
    lane_position: float = Field(
        default=0.0, ge=0.0, description="Distance travelled along the lane in metres (TraCI getLanePosition)"
    )
    position_x: float = Field(..., description="X coordinate in the SUMO network")
    position_y: float = Field(..., description="Y coordinate in the SUMO network")
    vehicle_type: VehicleType = Field(
        default=VehicleType.UNKNOWN,
        description="Classified vehicle type",
    )
    road_id: str = Field(..., description="Edge/road identifier in the SUMO network")
    waiting_time: float = Field(
        default=0.0, ge=0.0, description="Accumulated waiting time in seconds (TraCI getWaitingTime)"
    )
    sumo_type_id: str = Field(
        default="", description="Raw SUMO vType id (e.g. 'ambulance', 'passenger') from getTypeID()"
    )
    sumo_vclass: str = Field(
        default="", description="Raw SUMO vClass (e.g. 'emergency', 'passenger') from getVehicleClass()"
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when this snapshot was captured",
    )

    model_config = {"use_enum_values": True}


class VehicleListResponse(BaseModel):
    """Paginated / full list of vehicles returned by the API."""

    vehicles: List[VehicleData] = Field(default_factory=list)
    total: int = Field(..., ge=0, description="Total number of vehicles in the list")
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of this response",
    )

    @model_validator(mode="after")
    def _sync_total(self) -> "VehicleListResponse":
        """Ensure *total* always matches the actual list length."""
        self.total = len(self.vehicles)
        return self
