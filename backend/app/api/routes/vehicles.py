"""
IntelliRoads – Vehicles API endpoint.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.state_store import InMemoryStateStore
from app.models.vehicle import VehicleData, VehicleListResponse

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("", response_model=VehicleListResponse)
async def get_vehicles(store: InMemoryStateStore = Depends(get_store)) -> VehicleListResponse:
    """
    Get all active vehicles in the simulation.
    """
    vehicles = await store.get_vehicles()
    return VehicleListResponse(vehicles=vehicles, total=len(vehicles))


@router.get("/{vehicle_id}", response_model=VehicleData)
async def get_vehicle_by_id(
    vehicle_id: str,
    store: InMemoryStateStore = Depends(get_store),
) -> VehicleData:
    """
    Get telemetry for a specific vehicle by ID.
    """
    vehicles = await store.get_vehicles()
    for v in vehicles:
        if v.vehicle_id == vehicle_id:
            return v
    raise HTTPException(status_code=404, detail=f"Vehicle '{vehicle_id}' not found.")


@router.get("/lane/{lane_id}", response_model=VehicleListResponse)
async def get_vehicles_by_lane(
    lane_id: str,
    store: InMemoryStateStore = Depends(get_store),
) -> VehicleListResponse:
    """
    Get all active vehicles on a specific lane.
    """
    vehicles = await store.get_vehicles()
    filtered = [v for v in vehicles if v.lane_id == lane_id]
    return VehicleListResponse(vehicles=filtered, total=len(filtered))
