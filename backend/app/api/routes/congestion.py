"""
IntelliRoads – Congestion API endpoint.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.state_store import InMemoryStateStore
from app.models.congestion import CongestionEvent, CongestionResponse, CongestionStatus

router = APIRouter(prefix="/congestion", tags=["congestion"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("", response_model=CongestionResponse)
async def get_congestion(store: InMemoryStateStore = Depends(get_store)) -> CongestionResponse:
    """
    Get current congestion status and events.
    """
    congestion = await store.get_congestion()
    if not congestion:
        raise HTTPException(status_code=503, detail="Congestion data not available yet.")
    return congestion


@router.get("/active", response_model=List[CongestionEvent])
async def get_active_congestion(
    store: InMemoryStateStore = Depends(get_store),
) -> List[CongestionEvent]:
    """
    Get only the currently active congestion events (unresolved).
    """
    congestion = await store.get_congestion()
    if not congestion:
        raise HTTPException(status_code=503, detail="Congestion data not available yet.")
    
    return [
        event
        for event in congestion.events
        if event.status == CongestionStatus.CONGESTED and event.resolved_at is None
    ]
