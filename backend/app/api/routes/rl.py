"""
IntelliRoads – RL Environment evaluation and Controller mode management API endpoints.
"""

from __future__ import annotations

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Body

from app.models.rl import RLStats
from app.services.db_logger import DBLogger
from app.core.state_store import InMemoryStateStore
from app.controllers.dqn_controller import DQNController, ControllerMode

router = APIRouter(prefix="/rl", tags=["rl"])


def get_db_logger(request: Request) -> DBLogger:
    return request.app.state.db_logger


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


def get_dqn_controller(request: Request) -> DQNController:
    return request.app.state.dqn_controller


@router.get("/stats", response_model=RLStats)
async def get_rl_stats(db_logger: DBLogger = Depends(get_db_logger)) -> RLStats:
    """
    Evaluation utility: inspect collected RL state vectors, rewards, and
    transition counts.
    """
    return await db_logger.get_rl_stats()


@router.get("/mode")
async def get_controller_mode(store: InMemoryStateStore = Depends(get_store)) -> Dict[str, str]:
    """
    Get current signal controller operating mode (RULE_BASED or DQN).
    """
    mode = await store.get_controller_mode()
    return {"mode": mode}


@router.post("/mode")
async def set_controller_mode(
    payload: Dict[str, str] = Body(..., example={"mode": "DQN"}),
    store: InMemoryStateStore = Depends(get_store),
    dqn_controller: DQNController = Depends(get_dqn_controller),
) -> Dict[str, str]:
    """
    Select active signal controller operating mode (RULE_BASED or DQN).
    Allows switching to DQN controller while maintaining old rule-based controller for comparison.
    """
    requested_mode = payload.get("mode", "").upper()
    if requested_mode not in ("RULE_BASED", "DQN"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid controller mode '{requested_mode}'. Supported modes: 'RULE_BASED', 'DQN'."
        )

    mode_enum = ControllerMode(requested_mode)
    dqn_controller.set_mode(mode_enum)
    await store.set_controller_mode(requested_mode)
    return {"status": "success", "mode": requested_mode}
