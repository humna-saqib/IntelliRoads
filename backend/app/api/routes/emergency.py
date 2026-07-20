"""
IntelliRoads – Emergency vehicle API endpoint.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.state_store import InMemoryStateStore
from app.models.emergency import EmergencyResponse, EmergencyVehicleState

router = APIRouter(prefix="/emergency", tags=["emergency"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("", response_model=EmergencyResponse)
async def get_emergency(store: InMemoryStateStore = Depends(get_store)) -> EmergencyResponse:
    """
    Get current emergency vehicle status: active vehicles and recent
    detection events (DETECTED / INTERSECTION_CHANGE / CLEARED).
    """
    emergency = await store.get_emergency()
    if emergency is None:
        raise HTTPException(status_code=503, detail="Emergency vehicle data not available yet.")
    return emergency


@router.get("/active", response_model=List[EmergencyVehicleState])
async def get_active_emergency_vehicles(
    store: InMemoryStateStore = Depends(get_store),
) -> List[EmergencyVehicleState]:
    """
    Get only the currently active emergency vehicles.
    """
    emergency = await store.get_emergency()
    if emergency is None:
        raise HTTPException(status_code=503, detail="Emergency vehicle data not available yet.")
    return emergency.active_vehicles
