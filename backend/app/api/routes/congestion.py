"""
IntelliRoads – Congestion API endpoint.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.state_store import InMemoryStateStore
from app.models.congestion import (
    CongestionEvent,
    CongestionResponse,
    CongestionStatus,
    ResolveEventRequest,
)

router = APIRouter(prefix="/congestion", tags=["congestion"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


def get_detector(request: Request):
    return getattr(request.app.state, "congestion_detector", None)


def get_db_logger(request: Request):
    return getattr(request.app.state, "db_logger", None)


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


@router.post("/resolve", response_model=CongestionEvent)
async def resolve_congestion(
    body: ResolveEventRequest,
    detector=Depends(get_detector),
    db_logger=Depends(get_db_logger),
    store: InMemoryStateStore = Depends(get_store),
) -> CongestionEvent:
    """
    Manually resolve an active congestion event.
    """
    if detector is None:
        raise HTTPException(status_code=500, detail="Congestion detector service unavailable.")

    resolved_event = detector.resolve_event(body.event_id)
    if resolved_event and db_logger is not None:
        try:
            await db_logger.mark_event_resolved(body.event_id)
        except Exception:
            pass

    if not resolved_event:
        # Check current store as backup
        congestion = await store.get_congestion()
        if congestion:
            for ev in congestion.events:
                if (ev.id == body.event_id or ev.intersection_id == body.event_id) and ev.status == CongestionStatus.CONGESTED:
                    ev.status = CongestionStatus.CLEAR
                    ev.resolved_at = ev.resolved_at or 0.0
                    if db_logger is not None:
                        try:
                            await db_logger.mark_event_resolved(body.event_id)
                        except Exception:
                            pass
                    return ev

        raise HTTPException(status_code=404, detail=f"Active congestion event '{body.event_id}' not found.")
    
    return resolved_event


@router.get("/history", response_model=List[CongestionEvent])
async def get_congestion_history(
    start_time: Optional[float] = Query(None, description="Start unix timestamp filter"),
    end_time: Optional[float] = Query(None, description="End unix timestamp filter"),
    status: Optional[str] = Query(None, description="Status filter (CONGESTED, CLEAR, ALL)"),
    intersection_id: Optional[str] = Query(None, description="Intersection or lane ID filter"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    db_logger=Depends(get_db_logger),
    store: InMemoryStateStore = Depends(get_store),
) -> List[CongestionEvent]:
    """
    Query historical congestion events from SQLite with filtering options.
    """
    if db_logger is not None:
        try:
            return await db_logger.get_congestion_history(
                start_time=start_time,
                end_time=end_time,
                status=status,
                intersection_id=intersection_id,
                limit=limit,
            )
        except Exception as exc:
            pass  # Fall back to in-memory store events

    # Fallback to current in-memory events if DB logger is unavailable
    congestion = await store.get_congestion()
    if not congestion:
        return []

    events = list(congestion.events)
    if status and status.upper() != "ALL":
        events = [e for e in events if e.status == status.upper()]
    if intersection_id and intersection_id.strip():
        target = intersection_id.strip().lower()
        events = [e for e in events if target in e.intersection_id.lower()]
    return events[:limit]

