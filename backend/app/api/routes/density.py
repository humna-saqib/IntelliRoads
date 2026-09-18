"""
IntelliRoads – Density API endpoint.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.state_store import InMemoryStateStore
from app.models.density import DensityReading, DensityResponse, LaneDensity

router = APIRouter(prefix="/density", tags=["density"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


def get_db_logger(request: Request):
    return getattr(request.app.state, "db_logger", None)


@router.get("", response_model=DensityResponse)
async def get_density(store: InMemoryStateStore = Depends(get_store)) -> DensityResponse:
    """
    Get current density calculations for all monitored lanes.
    """
    density = await store.get_density()
    if not density:
        raise HTTPException(status_code=503, detail="Density calculations not available yet.")
    return density


@router.get("/history", response_model=List[DensityReading])
async def get_density_history(
    lane_id: Optional[str] = Query(None, description="Lane ID filter (exact or partial match)"),
    start_time: Optional[float] = Query(None, description="Start unix timestamp filter"),
    end_time: Optional[float] = Query(None, description="End unix timestamp filter"),
    level: Optional[str] = Query(None, description="Density level filter (LOW, MEDIUM, HIGH, ALL)"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    db_logger=Depends(get_db_logger),
) -> List[DensityReading]:
    """
    Query historical per-lane density readings from SQLite with filtering options.

    The density_readings table is written every simulation tick, so this
    endpoint gives a complete time-series of density per lane. Filter by
    lane_id, density level, or time window to narrow results.
    """
    if db_logger is not None:
        try:
            return await db_logger.get_density_history(
                lane_id=lane_id,
                start_time=start_time,
                end_time=end_time,
                level=level,
                limit=limit,
            )
        except Exception:
            pass  # Fall back to empty list if DB is unavailable

    # Fallback: DB logger unavailable — return empty list (no in-memory history for density)
    return []


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
