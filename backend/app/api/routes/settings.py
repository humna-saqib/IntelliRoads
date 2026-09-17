"""
IntelliRoads - Settings API: per-intersection threshold configuration.
"""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException

from app.core.threshold_config import (
    KNOWN_JUNCTIONS,
    JunctionThresholds,
    threshold_config_service,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/thresholds", response_model=Dict[str, JunctionThresholds])
def get_all_thresholds() -> Dict[str, JunctionThresholds]:
    """Returns configured (or default) thresholds for every known junction."""
    return threshold_config_service.get_all()


@router.get("/thresholds/{junction_id}", response_model=JunctionThresholds)
def get_junction_thresholds(junction_id: str) -> JunctionThresholds:
    if junction_id not in KNOWN_JUNCTIONS:
        raise HTTPException(status_code=404, detail=f"Unknown junction: {junction_id}")
    return threshold_config_service.get(junction_id)


@router.put("/thresholds/{junction_id}", response_model=JunctionThresholds)
def update_junction_thresholds(
    junction_id: str, thresholds: JunctionThresholds
) -> JunctionThresholds:
    if junction_id not in KNOWN_JUNCTIONS:
        raise HTTPException(status_code=404, detail=f"Unknown junction: {junction_id}")
    if thresholds.low_threshold >= thresholds.medium_threshold:
        raise HTTPException(
            status_code=400,
            detail="low_threshold must be less than medium_threshold",
        )
    return threshold_config_service.set(junction_id, thresholds)
