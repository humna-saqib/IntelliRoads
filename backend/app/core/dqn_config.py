"""
IntelliRoads – DQN Hyperparameter Configuration.

Loads hyperparameter settings from central dqn_config.json with environment variable overrides.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env file if present
load_dotenv()

CONFIG_JSON_PATH = Path(__file__).resolve().parent / "dqn_config.json"


class DQNConfig(BaseModel):
    """Configuration model for all DQN agent and training hyperparameters."""
    hidden_size: int = 64
    gamma: float = 0.99
    learning_rate: float = 0.001
    memory_capacity: int = 10000
    batch_size_online: int = 32
    batch_size_offline: int = 64
    target_update_frequency_epochs: int = 10
    epsilon_online: float = 0.1
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay_epochs: int = 50
    offline_epochs: int = 50
    offline_steps_per_epoch: int = 20


def load_dqn_config() -> DQNConfig:
    """Loads parameters from dqn_config.json and overrides with environment variables starting with DQN_."""
    defaults = {}
    if CONFIG_JSON_PATH.exists():
        try:
            with open(CONFIG_JSON_PATH, "r") as f:
                defaults = json.load(f)
        except Exception:
            # Fallback to schema defaults if json is corrupt or unreadable
            pass

    config_dict = {}
    # Iterate over fields to apply default and environment variable checks
    for key, field_info in DQNConfig.model_fields.items():
        env_key = f"DQN_{key.upper()}"
        env_val = os.getenv(env_key)
        if env_val is not None:
            # Cast type based on schema definition
            expected_type = field_info.annotation
            try:
                if expected_type is int:
                    config_dict[key] = int(env_val)
                elif expected_type is float:
                    config_dict[key] = float(env_val)
                else:
                    config_dict[key] = env_val
            except ValueError:
                # Fallback to JSON default or Pydantic schema default
                config_dict[key] = defaults.get(key, field_info.default)
        else:
            config_dict[key] = defaults.get(key, field_info.default)

    return DQNConfig(**config_dict)
