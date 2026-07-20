"""
IntelliRoads – Response Optimization Metrics API endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.core.state_store import InMemoryStateStore
from app.models.performance import PerformanceResponse
from app.services.db_logger import DBLogger

router = APIRouter(prefix="/performance", tags=["performance"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


def get_db_logger(request: Request) -> DBLogger:
    return request.app.state.db_logger


@router.get("", response_model=PerformanceResponse)
async def get_performance(
    minutes: int = Query(default=10, ge=1, le=120, description="How many recent per-minute buckets to include"),
    store: InMemoryStateStore = Depends(get_store),
    db_logger: DBLogger = Depends(get_db_logger),
) -> PerformanceResponse:
    """
    Get current controller/system performance metrics: the latest tick
    snapshot, recent per-minute (simulation-time) summaries, and a
    running whole-simulation summary. Purely observational — used to
    baseline the rule-based controller against the future DQN controller.
    """
    current = await store.get_performance()
    per_minute = await db_logger.get_minute_summary(limit=minutes)
    simulation_summary = await db_logger.get_simulation_summary()

    return PerformanceResponse(
        current=current,
        per_minute=per_minute,
        simulation_summary=simulation_summary,
    )
