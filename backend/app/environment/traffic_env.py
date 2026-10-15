"""
IntelliRoads FYP – corrected multi-junction SUMO environment (Stage 1 + Stage 2).

``TrafficSignalEnv`` is a new environment next to the legacy ``SUMOEnvironment``; the legacy
class (used by the live FastAPI controller and the existing checkpoint) is left untouched.

What this environment fixes compared with the legacy one
--------------------------------------------------------
* **Transition semantics.** ``step()`` applies the actions, then advances SUMO by
  ``decision_interval_s`` simulated seconds, and only then observes the next state and the
  reward.  The legacy ``step()`` read ``next_state`` in the same simulation instant as ``state``.
* **Episodes.** ``reset(seed)`` starts a fresh SUMO process with a fresh per-episode route file
  (written to a temporary directory – the tracked route file is never touched) and
  ``--seed``; episodes last ``horizon_s`` simulated seconds (default 1800 s, not 25 s).
* **Terminal vs truncation.** Reaching the time horizon is *truncation* (``truncated=True``,
  the learner must still bootstrap); *termination* means the simulation has nothing left to
  simulate.  ``replay_done_flag`` gives the flag to store in the replay buffer.
* **No silent fallbacks.** Any invalid TraCI response raises ``EnvError``.
* **Observation.** See ``app.environment.observation``.

Stage 2 – safe action handling
------------------------------
Actions keep their ids (0 KEEP, 1 SWITCH, 2 EXTEND, 3 REDUCE) but are executed by
``app.environment.signal_safety``: legality is computed from the junction's phase, the time
elapsed in it and the time *remaining* in it; EXTEND / REDUCE change the remaining time (the legacy
code changed the nominal duration, which allowed endless greens and lengthened yellows); yellow is
never touched; min / max green are enforced; SWITCH only enters the programme's own yellow.
``action_masks()`` returns the legal-action mask of every junction for the next decision.  An illegal
action raises ``EnvError`` (``on_illegal_action="raise"``, default) or is replaced by KEEP and
reported in ``info["coerced_actions"]`` (``"keep"``).  Every observed phase transition is audited
(``validate_transition``) and a violation raises ``EnvError`` when ``strict_safety`` is set.

The reward is still the legacy formula evaluated on the corrected, post-advance measurements; its
redesign is out of scope for these stages.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Tuple

import numpy as np

from app.environment.observation import (
    STATE_SIZE,
    EnvError,
    JunctionMeasurement,
    JunctionTopology,
    DEFAULT_DETECTOR_RANGE_M,
    OBS_V1,
    OBS_V2,
    check_detector_range,
    discover_topology,
    encode_state,
    encode_state_v2,
    read_measurement,
    read_presence,
    schema_feature_names,
    schema_state_size,
)
from app.environment.sumo_environment import (
    REWARD_SHAPING_BONUS,
    REWARD_WEIGHT_ACTION_CHANGE,
    REWARD_WEIGHT_CONGESTION,
    REWARD_WEIGHT_QUEUE_LENGTH,
    REWARD_WEIGHT_THROUGHPUT,
    REWARD_WEIGHT_WAITING_TIME,
    DQNAction,
)
from app.environment.signal_safety import (
    KEEP,
    IllegalActionError,
    PhaseView,
    SignalSafetyConfig,
    command_for,
    legal_action_mask,
    validate_transition,
)
from app.sumo_tools.route_generator import generate_routefile

try:  # pragma: no cover - import guard
    import sumolib
    import traci
    import traci.exceptions as _traci_exc

    SUMO_PYTHON_AVAILABLE = True
except Exception:  # pragma: no cover
    SUMO_PYTHON_AVAILABLE = False

_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SUMO_CONFIG = _BACKEND_DIR / "sumo" / "config" / "intelliroads.sumocfg"
DEFAULT_JUNCTIONS: Tuple[str, ...] = ("junctionA", "junctionB", "junctionC", "junctionD")

RouteFactory = Callable[[int, Path], Path]


def default_route_factory(seed: int, out_dir: Path, duration: int = 3600) -> Path:
    """Write the randomised demand of ``seed`` into ``out_dir`` (never into the tracked route file).

    ``duration`` is the time at which every flow stops inserting vehicles (default 3600 s as before).  The random
    draws do not depend on it, so a shorter ``duration`` gives exactly the first ``duration`` seconds of the same demand.
    """
    path = out_dir / f"episode_{seed}.rou.xml"
    generate_routefile(seed=seed, output_path=path, duration=duration)
    return path


@dataclass(frozen=True)
class EnvConfig:
    horizon_s: int = 1800                  # simulated seconds per episode
    decision_interval_s: int = 5           # simulated seconds between two decisions
    junction_ids: Tuple[str, ...] = DEFAULT_JUNCTIONS
    sumo_config: Path = DEFAULT_SUMO_CONFIG
    #: congestion rule of the legacy reward, applied to the junction-level measurement
    congestion_occupancy: float = 0.70
    congestion_count_per_lane: float = 15.0
    #: Stage 2 – signal safety rules and how to treat an illegal action
    safety: SignalSafetyConfig = SignalSafetyConfig()
    on_illegal_action: str = "raise"          # "raise" -> EnvError, "keep" -> coerce to KEEP and report
    strict_safety: bool = True                # raise EnvError if an unsafe phase transition is ever observed
    #: extra SUMO command-line options (Stage 4: e.g. ``--tripinfo-output`` to cross-check the evaluation metrics)
    extra_sumo_args: Tuple[str, ...] = ()
    #: Stage 4 – time (s) at which all flows stop inserting vehicles; ``None`` keeps the 3600 s of the route generator
    demand_end_s: Optional[int] = None
    #: Stage 5 – observation schema (``fyp-obs-v1`` default = the unchanged 11 features; ``fyp-obs-v2`` adds 4 presence features)
    obs_version: str = OBS_V1
    #: Stage 5 – detector range (m) of the v2 presence features; ignored by v1
    detector_range_m: float = DEFAULT_DETECTOR_RANGE_M

    def __post_init__(self) -> None:
        if self.on_illegal_action not in ("raise", "keep"):
            raise EnvError("on_illegal_action must be 'raise' or 'keep'")
        if self.horizon_s <= 0 or self.decision_interval_s <= 0:
            raise EnvError("horizon_s and decision_interval_s must be positive")
        if self.horizon_s % self.decision_interval_s != 0:
            raise EnvError("horizon_s must be a multiple of decision_interval_s")
        if not self.junction_ids:
            raise EnvError("at least one junction is required")
        if self.demand_end_s is not None and self.demand_end_s <= 0:
            raise EnvError("demand_end_s must be positive")
        schema_feature_names(self.obs_version)                 # raises EnvError for an unknown schema
        check_detector_range(self.detector_range_m)


class StepResult(NamedTuple):
    obs: Dict[str, np.ndarray]
    rewards: Dict[str, float]
    terminated: bool
    truncated: bool
    info: Dict[str, Any]


def replay_done_flag(terminated: bool, truncated: bool) -> bool:
    """Flag to store in replay: only a true terminal state cuts the bootstrap; a time-limit truncation does not."""
    return bool(terminated)


def legacy_reward(meas: JunctionMeasurement, n_lanes: int, action: int, departed_per_s: float,
                  congestion_occupancy: float, congestion_count_per_lane: float) -> float:
    """Legacy reward formula (weights imported from ``sumo_environment``) on corrected measurements."""
    congested = (meas.occupancy > congestion_occupancy) or (meas.count / n_lanes > congestion_count_per_lane)
    penalty = 0.0 if DQNAction(action) == DQNAction.KEEP_CURRENT_PHASE else 1.0
    reward = (
        - REWARD_WEIGHT_WAITING_TIME * meas.mean_wait_s
        - REWARD_WEIGHT_QUEUE_LENGTH * meas.halting
        - REWARD_WEIGHT_CONGESTION * (1.0 if congested else 0.0)
        + REWARD_WEIGHT_THROUGHPUT * departed_per_s
        - REWARD_WEIGHT_ACTION_CHANGE * penalty
    )
    if not congested:
        reward += REWARD_SHAPING_BONUS
    return round(reward, 4)


class TrafficSignalEnv:
    """Four-junction SUMO environment with a shared-policy interface (one observation per junction)."""

    state_size: int = STATE_SIZE
    action_size: int = len(DQNAction)

    def __init__(self, config: Optional[EnvConfig] = None, route_factory: Optional[RouteFactory] = None) -> None:
        if not SUMO_PYTHON_AVAILABLE:
            raise EnvError("traci/sumolib are not installed; TrafficSignalEnv needs a real SUMO (no mock mode)")
        self.cfg = config or EnvConfig()
        #: size / names of the observation this environment produces (v1 default: 11, unchanged)
        self.state_size: int = schema_state_size(self.cfg.obs_version)
        self.feature_names: Tuple[str, ...] = schema_feature_names(self.cfg.obs_version)
        if route_factory is not None:
            self._route_factory = route_factory
        elif self.cfg.demand_end_s is not None:
            end = int(self.cfg.demand_end_s)
            self._route_factory = lambda seed, out_dir: default_route_factory(seed, out_dir, duration=end)
        else:
            self._route_factory = default_route_factory
        self._label = f"fyp_env_{uuid.uuid4().hex[:8]}"
        self.conn: Any = None
        self._tmpdir: Optional[Path] = None
        self._topo: Dict[str, JunctionTopology] = {}
        self._phase: Dict[str, int] = {}
        self._phase_start: Dict[str, float] = {}
        self._next_switch: Dict[str, float] = {}      # scheduled end of the running phase, as of the last poll
        self._t: float = 0.0
        self._steps: int = 0
        self._done: bool = True
        self._teleports: int = 0
        self._violations: int = 0
        #: completed phases of the current episode: {junction, phase, start_s, duration_s}
        self.signal_log: List[Dict[str, Any]] = []
        #: callables ``hook(conn, sim_time)`` run after every simulated second (Stage 4 measurement); cleared by ``reset``
        self._second_hooks: List[Callable[[Any, float], None]] = []
        self.route_file: Optional[Path] = None
        self.seed: Optional[int] = None

    # ------------------------------------------------------------------ lifecycle
    def reset(self, seed: int) -> Dict[str, np.ndarray]:
        """Start a fresh episode with traffic demand and SUMO randomness fixed by ``seed``."""
        self.close()
        self._second_hooks = []
        self.seed = int(seed)
        self._tmpdir = Path(tempfile.mkdtemp(prefix="intelliroads_fyp_"))
        try:
            self.route_file = Path(self._route_factory(self.seed, self._tmpdir))
            if not self.route_file.resolve().is_relative_to(self._tmpdir.resolve()):
                raise EnvError(f"route files must be generated inside the episode's temporary directory, got {self.route_file} "
                               f"(tracked route files are never written)")
            cmd = [
                sumolib.checkBinary("sumo"), "-c", str(self.cfg.sumo_config),
                "--route-files", str(self.route_file),
                "--seed", str(self.seed),
                "--end", str(self.cfg.horizon_s + self.cfg.decision_interval_s + 10),
                "--no-step-log", "true", "--no-warnings", "true",
                *self.cfg.extra_sumo_args,
            ]
            traci.start(cmd, label=self._label)
            self.conn = traci.getConnection(self._label)
            self._topo = {j: discover_topology(self.conn, j) for j in self.cfg.junction_ids}
            self._t = float(self.conn.simulation.getTime())
            if self._t != 0.0:
                raise EnvError(f"expected simulation time 0 after reset, got {self._t}")
            for j in self.cfg.junction_ids:
                self._phase[j] = int(self.conn.trafficlight.getPhase(j))
                self._phase_start[j] = self._t
                self._next_switch[j] = float(self.conn.trafficlight.getNextSwitch(j))
        except EnvError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise EnvError(f"could not start SUMO episode (seed={seed}): {exc!r}") from exc
        self._steps = 0
        self._teleports = 0
        self._violations = 0
        self.signal_log = []
        self._done = False
        obs, _, _ = self._observe()
        return obs

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        if self._tmpdir is not None:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None
        self._done = True

    def __enter__(self) -> "TrafficSignalEnv":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def sim_time(self) -> float:
        return self._t

    @property
    def topology(self) -> Mapping[str, JunctionTopology]:
        return self._topo

    # ------------------------------------------------------------------ core API
    def step(self, actions: Mapping[str, int]) -> StepResult:
        """Apply one action per junction, advance SUMO one decision interval, observe, compute rewards."""
        if self.conn is None or self._done:
            raise EnvError("step() called on a finished or unstarted episode; call reset(seed) first")
        if set(actions) != set(self.cfg.junction_ids):
            raise EnvError(f"actions must be given for exactly {sorted(self.cfg.junction_ids)}, got {sorted(actions)}")
        requested = {j: self._parse_action(a) for j, a in actions.items()}

        parsed, coerced = self._resolve_actions(requested)          # validate ALL before applying ANY (nothing applied yet if this raises)
        try:
            for j, a in parsed.items():
                self._apply_action(j, a)
            self._track_phases(manual=True)          # a SWITCH takes effect at the action time, before the clock advances
            departed = 0
            for _ in range(self.cfg.decision_interval_s):
                self.conn.simulationStep()
                self._t = float(self.conn.simulation.getTime())
                departed += int(self.conn.simulation.getDepartedNumber())
                self._teleports += int(self.conn.simulation.getStartingTeleportNumber())
                self._track_phases(manual=False)
                for hook in self._second_hooks:
                    hook(self.conn, self._t)
            terminated = int(self.conn.simulation.getMinExpectedNumber()) == 0
        except EnvError:
            self._done = True                        # SUMO may already have advanced: the episode cannot continue, reset() is required
            raise
        except Exception as exc:
            self._done = True
            raise EnvError(f"TraCI failure while stepping at t={self._t}: {exc!r}") from exc

        self._steps += 1
        expected_t = float(self._steps * self.cfg.decision_interval_s)
        if abs(self._t - expected_t) > 1e-6:
            self._done = True
            raise EnvError(f"simulation clock out of sync: expected {expected_t}, got {self._t}")

        try:
            obs, metrics, clipped = self._observe()
        except BaseException:
            self._done = True
            raise
        departed_per_s = departed / self.cfg.decision_interval_s
        rewards = {
            j: legacy_reward(metrics[j], len(self._topo[j].lanes), parsed[j], departed_per_s,
                             self.cfg.congestion_occupancy, self.cfg.congestion_count_per_lane)
            for j in self.cfg.junction_ids
        }
        truncated = (not terminated) and self._t >= self.cfg.horizon_s
        self._done = terminated or truncated
        info = {
            "sim_time": self._t, "step": self._steps, "departed_in_interval": departed,
            "teleports_total": self._teleports, "metrics": metrics, "clipped_features": clipped,
            "elapsed_s": {j: self._t - self._phase_start[j] for j in self.cfg.junction_ids},
            "applied_actions": dict(parsed), "coerced_actions": coerced, "safety_violations": self._violations,
            # masks of the state reached by this step.  Provided even when the episode just ended: a time-limit
            # *truncation* must still bootstrap from that state, so the learner needs its legal actions.
            "action_masks": self.action_masks(),
        }
        return StepResult(obs, rewards, terminated, truncated, info)

    def add_second_hook(self, hook: Callable[[Any, float], None]) -> None:
        """Register ``hook(conn, sim_time)``, called after every simulated second of the *current* episode."""
        self._second_hooks.append(hook)

    def phase_view(self, junction_id: str) -> PhaseView:
        """Phase, elapsed and remaining time of a junction at the current decision time (read-only)."""
        if self.conn is None:
            raise EnvError("phase_view() needs a started episode; call reset(seed) first")
        return self._view(junction_id)

    def action_masks(self) -> Dict[str, np.ndarray]:
        """Legal-action mask (bool[4]: KEEP, SWITCH, EXTEND, REDUCE) of every junction for the next decision."""
        if self.conn is None:
            raise EnvError("action_masks() needs a started episode; call reset(seed) first")
        try:
            return {j: legal_action_mask(self._view(j), self.cfg.safety) for j in self.cfg.junction_ids}
        except EnvError:
            raise
        except Exception as exc:
            raise EnvError(f"TraCI failure while reading signal state at t={self._t}: {exc!r}") from exc

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _parse_action(a: Any) -> int:
        try:
            return int(DQNAction(int(a)))
        except (ValueError, TypeError) as exc:
            raise EnvError(f"invalid action {a!r}; expected one of {[int(x) for x in DQNAction]}") from exc

    def _view(self, junction_id: str) -> PhaseView:
        """Phase, elapsed and remaining time of a junction *now* (remaining = next switch - now)."""
        phase = self._phase[junction_id]
        remaining = self._next_switch[junction_id] - self._t
        if remaining < -1e-9:
            raise EnvError(f"{junction_id}: negative remaining phase time {remaining}")
        return PhaseView(phase, phase in self._topo[junction_id].green_phases,
                         self._t - self._phase_start[junction_id], remaining)

    def _track_phases(self, manual: bool) -> None:
        """Track phase changes and audit every transition against the safety rules.

        Timing uses SUMO's *schedule*: TraCI reports a naturally scheduled switch one second after
        the ``getNextSwitch`` time it was scheduled for (green due to end at 30 s is first seen as the
        next phase at the t = 31 poll).  A phase's start/end are therefore taken from the previous
        poll's ``getNextSwitch`` for natural switches and from the action time for our own SWITCH
        (``manual=True``), so that ``elapsed + remaining`` is the true scheduled phase length.
        """
        for j in self.cfg.junction_ids:
            p = int(self.conn.trafficlight.getPhase(j))
            if p != self._phase[j]:
                topo = self._topo[j]
                end = self._t if manual else self._next_switch[j]
                if not manual and not (-1e-6 <= self._t - end <= 1.0 + 1e-6):
                    raise EnvError(f"{j} at t={self._t:g}s: phase changed {self._phase[j]} -> {p} but it was scheduled for t={end:g}s")
                duration = end - self._phase_start[j]
                self.signal_log.append({"junction": j, "phase": self._phase[j], "start_s": self._phase_start[j], "duration_s": duration})
                problem = validate_transition(self.cfg.safety, topo.green_phases, topo.n_phases, self._phase[j], p, duration)
                if problem:
                    self._violations += 1
                    if self.cfg.strict_safety:
                        raise EnvError(f"{j} at t={self._t:g}s: unsafe signal transition – {problem}")
                self._phase[j] = p
                self._phase_start[j] = end
            self._next_switch[j] = float(self.conn.trafficlight.getNextSwitch(j))

    def _resolve_actions(self, requested: Mapping[str, int]) -> Tuple[Dict[str, int], Dict[str, Tuple[int, int]]]:
        """Check every requested action against the legal-action mask; raise or coerce to KEEP."""
        applied: Dict[str, int] = {}
        coerced: Dict[str, Tuple[int, int]] = {}
        for j, a in requested.items():
            mask = legal_action_mask(self._view(j), self.cfg.safety)
            if mask[a]:
                applied[j] = a
            elif self.cfg.on_illegal_action == "keep":
                applied[j], coerced[j] = KEEP, (a, KEEP)
            else:
                try:
                    command_for(self._view(j), a, self.cfg.safety, self._topo[j].n_phases)
                except IllegalActionError as exc:
                    raise IllegalActionError(f"{j} at t={self._t:g}s: {exc}") from exc
        return applied, coerced

    def _observe(self) -> Tuple[Dict[str, np.ndarray], Dict[str, JunctionMeasurement], int]:
        obs: Dict[str, np.ndarray] = {}
        metrics: Dict[str, JunctionMeasurement] = {}
        clipped = 0
        for j in self.cfg.junction_ids:
            m = read_measurement(self.conn, self._topo[j])          # also the reward's input: identical for v1 and v2
            if self.cfg.obs_version == OBS_V2:
                presence = read_presence(self.conn, self._topo[j], self._phase[j], self.cfg.detector_range_m)
                vec, n_clipped = encode_state_v2(self._topo[j], m, self._phase[j], self._t - self._phase_start[j], presence,
                                                 self.cfg.detector_range_m, elapsed_max_s=self.cfg.safety.max_green_s)
            else:
                vec, n_clipped = encode_state(self._topo[j], m, self._phase[j], self._t - self._phase_start[j],
                                              elapsed_max_s=self.cfg.safety.max_green_s)
            obs[j], metrics[j] = vec, m
            clipped += n_clipped
        return obs, metrics, clipped

    def _apply_action(self, junction_id: str, action: int) -> None:
        """Execute a (already validated) action with remaining-time arithmetic and verify TraCI applied it."""
        view = self._view(junction_id)
        cmd = command_for(view, action, self.cfg.safety, self._topo[junction_id].n_phases)
        if cmd is None:
            return
        tl = self.conn.trafficlight
        if cmd.kind == "set_phase":
            tl.setPhase(junction_id, int(cmd.value))
            got, want = int(tl.getPhase(junction_id)), int(cmd.value)
            remaining = float(tl.getNextSwitch(junction_id)) - self._t
            if got != want or abs(remaining - self.cfg.safety.yellow_s) > 1e-6:
                raise EnvError(f"{junction_id}: SWITCH did not enter a full yellow (phase {got}, remaining {remaining:g}s)")
        else:
            tl.setPhaseDuration(junction_id, cmd.value)
            remaining = float(tl.getNextSwitch(junction_id)) - self._t
            if abs(remaining - cmd.value) > 1e-6:
                raise EnvError(f"{junction_id}: expected {cmd.value:g}s of green left after the action, TraCI reports {remaining:g}s")
