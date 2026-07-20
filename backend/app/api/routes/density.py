"""
IntelliRoads – Density API endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.state_store import InMemoryStateStore
from app.models.density import DensityResponse, LaneDensity

router = APIRouter(prefix="/density", tags=["density"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("", response_model=DensityResponse)
async def get_density(store: InMemoryStateStore = Depends(get_store)) -> DensityResponse:
    """
    Get current density calculations for all monitored lanes.
    """
    density = await store.get_density()
    if not density:
        raise HTTPException(status_code=503, detail="Density calculations not available yet.")
    return density


@router.get("/{lane_id}", response_model=LaneDensity)
async def get_lane_density(
    lane_id: str,
    store: InMemoryStateStore = Depends(get_store),
) -> LaneDensity:
    """
    Get density calculations for a specific lane.
    """
    density = await store.get_density()
    if not density:
        raise HTTPException(status_code=503, detail="Density calculations not available yet.")
    
    for lane in density.lanes:
        if lane.lane_id == lane_id:
            return lane
            
    raise HTTPException(status_code=404, detail=f"Lane '{lane_id}' not found.")
