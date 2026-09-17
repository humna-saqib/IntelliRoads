"""
IntelliRoads - Per-intersection threshold configuration service.

Density and congestion thresholds were previously fixed class constants
(DensityCalculator.LOW_THRESHOLD/MEDIUM_THRESHOLD, CongestionDetector.
CONGESTION_THRESHOLD) shared by every intersection. This service lets an
operator configure different thresholds per junction via the Settings
page, persisted to a small JSON file so they survive a restart.

Falls back to the original global defaults for any junction that has no
explicit override, so existing behavior is unchanged until someone
actually configures something.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Same defaults as the original fixed constants in density_calculator.py
# and congestion_detector.py - unconfigured junctions behave exactly as
# they did before this feature existed.
DEFAULT_LOW_THRESHOLD: float = 20.0
DEFAULT_MEDIUM_THRESHOLD: float = 40.0
DEFAULT_CONGESTION_THRESHOLD: float = 40.0

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "threshold_config.json"

KNOWN_JUNCTIONS = ["junctionA", "junctionB", "junctionC", "junctionD"]

# lane_id -> junction_id, derived from the naming convention used throughout
# the codebase (lane_<JunctionLetter>_<direction>_in, e.g. lane_A_west_in).
# Inter-junction connector lanes (e.g. lane_AB_west) don't belong to a single
# junction and are intentionally left unmapped - they fall back to the
# global default threshold rather than guessing which junction owns them.
_LANE_JUNCTION_PATTERN = re.compile(r"^lane_([A-D])_")


def junction_for_lane(lane_id: str) -> Optional[str]:
    """Return the owning junction_id for a lane, or None if the lane isn't
    uniquely owned by a single junction (e.g. an inter-junction connector)."""
    match = _LANE_JUNCTION_PATTERN.match(lane_id)
    if match:
        return f"junction{match.group(1)}"
    return None


class JunctionThresholds(BaseModel):
    low_threshold: float = Field(default=DEFAULT_LOW_THRESHOLD, gt=0)
    medium_threshold: float = Field(default=DEFAULT_MEDIUM_THRESHOLD, gt=0)
    congestion_threshold: float = Field(default=DEFAULT_CONGESTION_THRESHOLD, gt=0)


class ThresholdConfigService:
    """In-memory threshold store, persisted to a JSON file on every write."""

    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        self._config_path = config_path
        self._lock = threading.Lock()
        self._overrides: Dict[str, JunctionThresholds] = {}
        self._load()

    def _load(self) -> None:
        if not self._config_path.exists():
            return
        try:
            raw = json.loads(self._config_path.read_text())
            for junction_id, values in raw.items():
                self._overrides[junction_id] = JunctionThresholds(**values)
            logger.info(
                f"Loaded threshold overrides for {len(self._overrides)} "
                f"junction(s) from {self._config_path}"
            )
        except Exception as exc:
            logger.warning(f"Failed to load threshold config, using defaults: {exc}")

    def _persist(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {jid: t.model_dump() for jid, t in self._overrides.items()}
        self._config_path.write_text(json.dumps(payload, indent=2))

    def get_all(self) -> Dict[str, JunctionThresholds]:
        """Returns configured thresholds for every known junction, filling
        in defaults for any junction without an explicit override."""
        with self._lock:
            return {
                jid: self._overrides.get(jid, JunctionThresholds())
                for jid in KNOWN_JUNCTIONS
            }

    def get(self, junction_id: str) -> JunctionThresholds:
        with self._lock:
            return self._overrides.get(junction_id, JunctionThresholds())

    def set(self, junction_id: str, thresholds: JunctionThresholds) -> JunctionThresholds:
        with self._lock:
            self._overrides[junction_id] = thresholds
            self._persist()
            logger.info(f"Updated thresholds for {junction_id}: {thresholds}")
            return thresholds

    def get_for_lane(self, lane_id: str) -> JunctionThresholds:
        """Convenience lookup used by DensityCalculator/CongestionDetector -
        resolves a lane_id to its junction, then returns that junction's
        thresholds (or defaults if unmapped/unconfigured)."""
        junction_id = junction_for_lane(lane_id)
        if junction_id is None:
            return JunctionThresholds()
        return self.get(junction_id)


# Module-level singleton, matching the pattern used by other stateful
# services in this codebase (e.g. InMemoryStateStore).
threshold_config_service = ThresholdConfigService()
