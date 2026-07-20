"""
IntelliRoads – RL Environment evaluation API endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.models.rl import RLStats
from app.services.db_logger import DBLogger

router = APIRouter(prefix="/rl", tags=["rl"])


def get_db_logger(request: Request) -> DBLogger:
    return request.app.state.db_logger


@router.get("/stats", response_model=RLStats)
async def get_rl_stats(db_logger: DBLogger = Depends(get_db_logger)) -> RLStats:
    """
    Evaluation utility: inspect collected RL state vectors, rewards, and
    transition counts. Observational only — the rule-based controller
    stays fully in control; no DQN model exists yet.
    """
    return await db_logger.get_rl_stats()
