"""
IntelliRoads – Response Optimization Metrics API endpoint.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request

from app.core.state_store import InMemoryStateStore
from app.models.performance import PerformanceResponse, PerformanceSnapshot
from app.services.db_logger import DBLogger

router = APIRouter(prefix="/performance", tags=["performance"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


def get_db_logger(request: Request) -> DBLogger:
    return request.app.state.db_logger


def get_db_logger_optional(request: Request):
    return getattr(request.app.state, "db_logger", None)


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


@router.get("/history", response_model=List[PerformanceSnapshot])
async def get_performance_history(
    start_time: Optional[float] = Query(None, description="Start unix timestamp filter"),
    end_time: Optional[float] = Query(None, description="End unix timestamp filter"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    db_logger=Depends(get_db_logger_optional),
) -> List[PerformanceSnapshot]:
    """
    Query raw per-tick performance metric snapshots from SQLite with filtering.

    The performance_metrics table is written every simulation tick, so this
    endpoint gives a complete time-series of raw system performance data.
    The existing GET /performance endpoint returns aggregated per-minute
    summaries; this endpoint returns the underlying individual tick snapshots.
    Filter by time window to narrow results.
    """
    if db_logger is not None:
        try:
            return await db_logger.get_performance_history(
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
        except Exception:
            pass  # Fall back to empty list if DB is unavailable

    # Fallback: DB logger unavailable — return empty list
    return []
