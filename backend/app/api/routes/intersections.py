"""
IntelliRoads – Intersections API endpoint.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, Request

from app.core.state_store import InMemoryStateStore

router = APIRouter(prefix="/intersections", tags=["intersections"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("")
async def get_intersections(store: InMemoryStateStore = Depends(get_store)) -> List[dict]:
    """
    Get aggregated status information for all monitored intersections.
    """
    snapshot = await store.get_full_snapshot()
    return snapshot.get("intersections", [])
