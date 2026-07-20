"""
IntelliRoads – RL Environment Preparation Pydantic v2 models (Sprint 2).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field

# Order is authoritative for encoding/decoding state/next_state vectors.
STATE_FEATURE_NAMES: List[str] = [
    "density",
    "queue_length",
    "avg_waiting_time",
    "occupancy_percent",
    "current_signal_duration",
]


class RLAction(str, Enum):
    """Discrete signal-control action space."""

    DECREASE_GREEN = "DECREASE_GREEN"
    KEEP_SAME = "KEEP_SAME"
    INCREASE_GREEN = "INCREASE_GREEN"


class RLExperience(BaseModel):
    """One (state, action, reward, next_state) transition for a single junction."""

    sim_time: float = Field(..., description="Simulation time this transition was recorded")
    junction_id: str = Field(..., description="Junction this experience belongs to")
    state: List[float] = Field(..., description="Feature vector, see STATE_FEATURE_NAMES for order")
    action: RLAction = Field(..., description="Action taken by the rule-based controller this tick")
    reward: float = Field(..., description="Reward resulting from the action")
    next_state: List[float] = Field(..., description="Feature vector after the action, same order")
    done: bool = Field(
        default=False,
        description="Episode-termination flag; always False for now — episode boundaries aren't defined yet",
    )
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of this transition")

    model_config = {"use_enum_values": True}


class RLStats(BaseModel):
    """Evaluation utility output: inspect collected state vectors, rewards, and transition counts."""

    transition_count: int = Field(..., ge=0, description="Total experiences stored so far")
    reward_min: float = Field(..., description="Minimum reward observed")
    reward_max: float = Field(..., description="Maximum reward observed")
    reward_mean: float = Field(..., description="Mean reward observed")
    action_distribution: Dict[str, int] = Field(
        default_factory=dict, description="Count of each action taken across all experiences"
    )
    state_feature_stats: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Per-feature {min, max, mean} across all stored state vectors",
    )
