"""
IntelliRoads – Vehicle classification API endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.state_store import InMemoryStateStore

router = APIRouter(prefix="/classification", tags=["classification"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("")
async def get_classification(store: InMemoryStateStore = Depends(get_store)) -> dict:
    """
    Get current classification counts, percentages and statistics.
    """
    snapshot = await store.get_full_snapshot()
    return snapshot.get("classification", {
        "car": 0,
        "motorcycle": 0,
        "bus": 0,
        "emergency": 0,
        "unknown": 0,
        "percentages": {},
        "most_common_type": "unknown"
    })
