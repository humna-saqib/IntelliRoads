"""
IntelliRoads FYP – live-application controller for the final obs-v2 Double DQN.

Drives the real signals of the running dashboard backend with the *same* model, observation encoding and safe action layer that
the final evaluation used (``app.environment.observation``, ``app.environment.signal_safety``, ``app.training.double_dqn``).
Nothing of the evaluated logic is re-implemented here except the live phase bookkeeping, because the evaluation environment owns
its own SUMO process while the live application shares one TraCI connection with other services.

Behaviour
---------
* One decision per junction every ``DECISION_INTERVAL_S`` simulated seconds (the evaluation's decision interval).
* The observation is built from the live TraCI connection; the action is the **greedy masked argmax**
  (``MaskedDoubleDQN.greedy``): an illegal action is never chosen, and ``command_for`` re-checks legality before anything is sent.
* The legacy interface is kept (``set_mode`` / ``get_mode`` / ``control_step`` / ``get_current_signals``) so ``main.py``, the mode
  endpoints and the emergency-priority layer work unchanged.  ``RULE_BASED`` mode delegates to the existing rule-based controller;
  any failure in DQN mode drops back to rule-based control, exactly like the legacy controller.
* The checkpoint is pinned by SHA-256 and strictly schema-checked; a mismatching or legacy 5-feature file is refused, never reshaped.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np
import torch

from app.controllers.dqn_controller import ControllerMode
from app.environment.observation import (
    DEFAULT_DETECTOR_RANGE_M,
    OBS_V1,
    OBS_V2,
    JunctionMeasurement,
    JunctionTopology,
    discover_topology,
    encode_state,
    encode_state_v2,
    read_measurement,
    read_presence,
)
from app.environment.signal_safety import (
    ACTION_NAMES,
    KEEP,
    PhaseView,
    SignalSafetyConfig,
    command_for,
    legal_action_mask,
)
from app.evaluation.protocol import policy_weights_sha256, sha256_file
from app.models.density import DensityLevel
from app.models.signal import SignalPhaseType, SignalTiming
from app.training.double_dqn import MaskedDoubleDQN
from app.training.runs import checkpoint_schema
from app.utils.logger import get_logger

logger = get_logger(__name__)

DECISION_INTERVAL_S = 5

#: The model evaluated in the final evaluation (training run ``fyp_s0_obs_v2``, validation-selected episode 240, ``best.pt``).
DEFAULT_MODEL_PATH: Path = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "fyp_obs_v2_ep240.pt"
DEFAULT_MODEL_SHA256 = "e7bc8722fe62b1cec0b9d4cf06038347050092c8a6ed6193f398f41683a97055"

#: ``INTELLIROADS_DQN_MODEL=legacy`` keeps the original 5-feature demo model.
MODEL_SELECTOR_ENV = "INTELLIROADS_DQN_MODEL"


class FypModelError(RuntimeError):
    """The checkpoint is missing, altered or not a usable FYP model."""


def load_fyp_model(path: Path = DEFAULT_MODEL_PATH, expected_sha256: Optional[str] = DEFAULT_MODEL_SHA256) -> Tuple[MaskedDoubleDQN, Dict[str, Any]]:
    """Load a FYP checkpoint for inference only (strict: pinned hash, validated schema, no reshaping)."""
    path = Path(path)
    if not path.is_file():
        raise FypModelError(f"model file not found: {path}")
    digest = sha256_file(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise FypModelError(f"{path.name}: SHA-256 {digest[:12]}... does not match the evaluated model {expected_sha256[:12]}...")
    ck = torch.load(str(path), map_location="cpu", weights_only=False)
    try:
        schema = checkpoint_schema(ck)
    except Exception as exc:
        raise FypModelError(f"{path.name} is not a usable FYP checkpoint: {exc}") from exc
    agent = MaskedDoubleDQN(int(ck["state_size"]), int(ck["n_actions"]), hidden=int(ck["train_config"]["hidden"]))
    agent.policy_net.load_state_dict(ck["policy_net"])
    agent.policy_net.eval()
    info = {
        "file": path.name, "sha256": digest, "policy_sha256": policy_weights_sha256(agent),
        "obs_version": schema["obs_version"], "detector_range_m": schema["detector_range_m"],
        "state_size": agent.state_size, "n_actions": agent.n_actions, "hidden": int(ck["train_config"]["hidden"]),
        "selected_episode": int(ck["episode"]), "val_metric": ck.get("val_metric"), "val_score": ck.get("val_score"),
    }
    return agent, info


class PhaseTracker:
    """Phase, start and scheduled end of one junction's current phase, polled every simulated second.

    Same timing convention as the evaluation environment: TraCI reports a naturally scheduled switch one second after the
    ``getNextSwitch`` time it was scheduled for, so a phase's start is the *previous* poll's ``getNextSwitch`` for natural switches
    and the action time for our own SWITCH or for any change made by another service (e.g. the emergency-priority layer).
    """

    def __init__(self, conn: Any, junction_id: str, now: float) -> None:
        self.junction_id = junction_id
        tl = conn.trafficlight
        self.phase = int(tl.getPhase(junction_id))
        self.next_switch = float(tl.getNextSwitch(junction_id))
        # TraCI 1.18 has no getSpentDuration: elapsed = scheduled phase length - time left (the controller is created at simulation
        # start, so this is normally 0 s elapsed in phase 0).
        scheduled = float(tl.getPhaseDuration(junction_id))
        self.start = min(max(self.next_switch - scheduled, 0.0), now)

    def update(self, conn: Any, now: float, manual: bool = False) -> None:
        tl = conn.trafficlight
        phase = int(tl.getPhase(self.junction_id))
        if phase != self.phase:
            natural = -1e-6 <= now - self.next_switch <= 1.0 + 1e-6
            self.start = self.next_switch if (natural and not manual) else now
            self.phase = phase
        self.next_switch = float(tl.getNextSwitch(self.junction_id))

    def view(self, now: float, green_phases: Tuple[int, ...]) -> PhaseView:
        return PhaseView(self.phase, self.phase in green_phases, max(now - self.start, 0.0), max(self.next_switch - now, 0.0))


@dataclass
class _Decision:
    action: int
    q: Tuple[float, ...]
    meas: JunctionMeasurement
    time: float


class FypDQNController:
    """Live controller running the final obs-v2 model through the safe action layer."""

    def __init__(
        self,
        session: Any,
        agent: MaskedDoubleDQN,
        info: Mapping[str, Any],
        rule_based_controller: Optional[Any] = None,
        mode: ControllerMode = ControllerMode.DQN,
        conn: Any = None,
        safety: Optional[SignalSafetyConfig] = None,
        junction_ids: Optional[Tuple[str, ...]] = None,
        decision_interval_s: int = DECISION_INTERVAL_S,
    ) -> None:
        self.session = session
        self.agent = agent
        self.model_info: Dict[str, Any] = dict(info)
        self.rule_based_controller = rule_based_controller
        self.mode = mode
        self.safety = safety or SignalSafetyConfig()
        self.decision_interval_s = int(decision_interval_s)
        self.obs_version: str = self.model_info["obs_version"]
        self.detector_range_m: float = float(self.model_info.get("detector_range_m") or DEFAULT_DETECTOR_RANGE_M)
        self._conn = conn
        self._junction_ids = junction_ids
        self._topo: Dict[str, JunctionTopology] = {}
        self._trackers: Dict[str, PhaseTracker] = {}
        self._last: Dict[str, _Decision] = {}
        self._signals: Dict[str, SignalTiming] = {}
        self.stats: Dict[str, Any] = {"decisions": 0, "action_counts": {n: 0 for n in ACTION_NAMES}, "clipped_features": 0,
                                      "last_decision_sim_time": None}
        logger.info(f"FypDQNController ready: model {self.model_info['file']} (episode {self.model_info['selected_episode']}, "
                    f"{self.obs_version}, {self.model_info['state_size']} features), mode={self.mode.value}")

    # ------------------------------------------------------------------ mode management (legacy interface)
    def set_mode(self, mode: ControllerMode | str) -> None:
        if isinstance(mode, str):
            mode = ControllerMode(mode.upper())
        self.mode = mode

    def get_mode(self) -> ControllerMode:
        return self.mode

    def get_current_signals(self) -> List[SignalTiming]:
        if self.mode == ControllerMode.RULE_BASED and self.rule_based_controller is not None:
            return self.rule_based_controller.get_current_signals()
        return list(self._signals.values())

    def describe(self) -> Dict[str, Any]:
        """Model and usage information for the dashboard / API."""
        return {"model": "fyp-obs-v2 Double DQN", **self.model_info, "mode": self.mode.value,
                "decision_interval_s": self.decision_interval_s, "safety": {
                    "min_green_s": self.safety.min_green_s, "max_green_s": self.safety.max_green_s,
                    "step_s": self.safety.step_s, "yellow_s": self.safety.yellow_s},
                "stats": {**self.stats, "action_counts": dict(self.stats["action_counts"])}}

    # ------------------------------------------------------------------ control step
    def control_step(self, density_response: Any, vehicles: Optional[List[Any]] = None, occupancy_response: Optional[Any] = None,
                     throughput: int = 1, epsilon: float = 0.0) -> List[SignalTiming]:
        """One call per simulated second.  ``epsilon`` is accepted for interface compatibility and ignored (greedy policy)."""
        conn, now, ready = None, 0.0, False
        try:                                                       # nothing below may crash the live simulation loop
            conn = self._connection()
            now = float(conn.simulation.getTime())
            self._ensure_initialised(conn, now)
            for j in self._trackers:                               # polled every second in both modes
                self._trackers[j].update(conn, now)
            ready = True
        except Exception as exc:
            self._fall_back(exc)

        if self.mode == ControllerMode.RULE_BASED and self.rule_based_controller is not None:
            self.rule_based_controller.update_all_signals(density_response)
            return self.rule_based_controller.get_current_signals()
        if ready:
            try:
                self._dqn_step(conn, now)
            except Exception as exc:
                self._fall_back(exc)
                if self.rule_based_controller is not None:
                    self.rule_based_controller.update_all_signals(density_response)
                    return self.rule_based_controller.get_current_signals()
        elif self.rule_based_controller is not None:               # not ready and no rule-based mode set: use it for this tick
            self.rule_based_controller.update_all_signals(density_response)
            return self.rule_based_controller.get_current_signals()
        return list(self._signals.values())

    def _fall_back(self, exc: Exception) -> None:
        if self.mode != ControllerMode.RULE_BASED:
            logger.error(f"FYP DQN control step failed ({exc!r}); falling back to RULE_BASED mode until switched back manually.")
            self.mode = ControllerMode.RULE_BASED
        else:
            logger.warning(f"FYP controller bookkeeping failed while in RULE_BASED mode ({exc!r}).")

    # ------------------------------------------------------------------ internals
    def _connection(self) -> Any:
        if self._conn is None:
            import traci  # type: ignore
            self._conn = traci
        return self._conn

    def _ensure_initialised(self, conn: Any, now: float) -> None:
        if self._trackers:
            return
        ids = self._junction_ids or tuple(sorted(j for j in conn.trafficlight.getIDList() if j.startswith("junction")))
        if not ids:
            raise RuntimeError("no signalised junctions found in the running simulation")
        for j in ids:
            self._topo[j] = discover_topology(conn, j)
            self._trackers[j] = PhaseTracker(conn, j, now)

    def _due(self, now: float) -> bool:
        t = int(round(now))
        return abs(now - t) < 1e-6 and t > 0 and t % self.decision_interval_s == 0

    def _observe(self, conn: Any, j: str, now: float, view: PhaseView) -> Tuple[np.ndarray, JunctionMeasurement]:
        topo, tr = self._topo[j], self._trackers[j]
        meas = read_measurement(conn, topo)
        if self.obs_version == OBS_V2:
            presence = read_presence(conn, topo, tr.phase, self.detector_range_m)
            vec, clipped = encode_state_v2(topo, meas, tr.phase, view.elapsed_s, presence, self.detector_range_m,
                                           elapsed_max_s=self.safety.max_green_s)
        elif self.obs_version == OBS_V1:
            vec, clipped = encode_state(topo, meas, tr.phase, view.elapsed_s, elapsed_max_s=self.safety.max_green_s)
        else:
            raise FypModelError(f"unsupported observation schema {self.obs_version!r}")
        self.stats["clipped_features"] += int(clipped)
        return vec, meas

    def _q_values(self, vec: np.ndarray) -> Tuple[float, ...]:
        with torch.no_grad():
            q = self.agent.policy_net(torch.as_tensor(np.asarray(vec, np.float32)).unsqueeze(0))[0]
        return tuple(float(x) for x in q.tolist())

    def _dqn_step(self, conn: Any, now: float) -> None:
        if self._due(now):
            for j, tr in self._trackers.items():
                topo = self._topo[j]
                view = tr.view(now, topo.green_phases)
                vec, meas = self._observe(conn, j, now, view)
                mask = legal_action_mask(view, self.safety)
                action = self.agent.greedy(vec, mask)
                cmd = command_for(view, action, self.safety, topo.n_phases)      # raises if the action were illegal
                if cmd is not None:
                    if cmd.kind == "set_phase":
                        conn.trafficlight.setPhase(j, int(cmd.value))
                    else:
                        conn.trafficlight.setPhaseDuration(j, float(cmd.value))
                    tr.update(conn, now, manual=True)
                self._last[j] = _Decision(action, self._q_values(vec), meas, now)
                self.stats["decisions"] += 1
                self.stats["action_counts"][ACTION_NAMES[action]] += 1
                self.stats["last_decision_sim_time"] = now
        for j, tr in self._trackers.items():
            self._signals[j] = self._timing(j, tr, now)

    def _timing(self, j: str, tr: PhaseTracker, now: float) -> SignalTiming:
        topo = self._topo[j]
        view = tr.view(now, topo.green_phases)
        d = self._last.get(j)
        count = d.meas.count if d is not None else 0.0
        level = DensityLevel.LOW if count < 10.0 else (DensityLevel.MEDIUM if count <= 25.0 else DensityLevel.HIGH)
        if d is None:
            reason = "obs-v2 DQN: waiting for the first decision"
        else:
            q = ", ".join(f"{n} {v:+.2f}" for n, v in zip(ACTION_NAMES, d.q))
            reason = f"obs-v2 DQN action: {ACTION_NAMES[d.action]} at t={d.time:.0f}s (Q: {q})"
        return SignalTiming(
            junction_id=j,
            phase=SignalPhaseType.GREEN if view.is_green else SignalPhaseType.YELLOW,
            duration_seconds=max(view.total_s, 1.0),
            density_level=level,
            triggered_at=time.time(),
            reason=reason,
        )


def try_build_fyp_controller(session: Any, rule_based_controller: Any, mode: ControllerMode = ControllerMode.DQN) -> Optional[FypDQNController]:
    """Build the live FYP controller, or return ``None`` (with the reason logged) so the caller keeps the legacy controller."""
    if os.environ.get(MODEL_SELECTOR_ENV, "fyp").strip().lower() == "legacy":
        logger.info(f"{MODEL_SELECTOR_ENV}=legacy: using the original 5-feature demo model.")
        return None
    if getattr(session, "mock_mode", True):
        logger.warning("SUMO is not running (mock mode): the FYP model needs live TraCI data; using the legacy controller.")
        return None
    try:
        agent, info = load_fyp_model()
    except FypModelError as exc:
        logger.warning(f"FYP obs-v2 model not loaded ({exc}); using the legacy controller.")
        return None
    return FypDQNController(session=session, agent=agent, info=info, rule_based_controller=rule_based_controller, mode=mode)
