"""
IntelliRoads – Lane Occupancy API endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.state_store import InMemoryStateStore
from app.models.occupancy import OccupancyResponse

router = APIRouter(prefix="/occupancy", tags=["occupancy"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("", response_model=OccupancyResponse)
async def get_occupancy(store: InMemoryStateStore = Depends(get_store)) -> OccupancyResponse:
    """
    Get current lane occupancy: raw percentage and qualitative level per lane.
    """
    occupancy = await store.get_occupancy()
    if occupancy is None:
        raise HTTPException(status_code=503, detail="Occupancy data not available yet.")
    return occupancy
