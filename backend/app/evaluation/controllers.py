"""Controllers compared by the evaluation protocol (Stage 4).

Every controller acts through the *same* safe action layer and decision interval (``TrafficSignalEnv``), so all of them
obey the same minimum/maximum green, yellow protection and legality rules, and are measured by the same code.

* ``fixed_time``      – SUMO's own configured programme (``G30 y5 G30 y5``), left untouched: KEEP at every decision.
                        This is the *actual* SUMO programme, not a re-imposed copy (the legacy script re-applied durations
                        one second late and drifted); ``protocol.verify_fixed_time_timing`` checks the real timings.
* ``rule_based``      – the legacy density rule (low < 20, medium < 40, high >= 40 veh/km on the lanes served by the current
                        green -> a green of 20 / 35 / 55 s), executed with EXTEND / REDUCE steps through the safe layer.
* ``actuated_style``  – an *emulation* of actuated control (green extension while vehicles are at the stop line, gap-out
                        once the served approaches are empty and the other group waits, max-out at ``max_green_s``).
                        It is **not** SUMO's native actuated logic (which re-programmes the traffic light and reacts every
                        second); it reacts at the decision interval.  Parameters are fixed a priori, not tuned on any seed.
* ``dqn``             – the validation-selected checkpoint, greedy (epsilon = 0) over legal actions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from app.environment.observation import OBS_V1
from app.environment.signal_safety import EXTEND, KEEP, REDUCE, SWITCH

# legacy density thresholds (veh/km) and the green length they select (SignalController.TIMING_RULES)
RULE_DENSITY_LOW, RULE_DENSITY_MEDIUM = 20.0, 40.0
RULE_GREEN_LOW, RULE_GREEN_MEDIUM, RULE_GREEN_HIGH = 20.0, 35.0, 55.0


class EvalController:
    name = "base"

    @property
    def params(self) -> Dict[str, Any]:
        return {}

    def start_episode(self, env: Any) -> None:
        pass

    def act(self, env: Any, obs: Mapping[str, np.ndarray], masks: Mapping[str, np.ndarray]) -> Dict[str, int]:
        raise NotImplementedError


class FixedTimeController(EvalController):
    """SUMO's configured programme, unmodified."""

    name = "fixed_time"

    def act(self, env, obs, masks):
        return {j: KEEP for j in env.cfg.junction_ids}


def _served_lanes(env: Any, junction: str, phase: int):
    topo = env.topology[junction]
    k = topo.green_phases.index(phase)
    return [(topo.lanes[i], topo.lengths_m[i]) for i in topo.groups[k]]


class RuleBasedController(EvalController):
    name = "rule_based"

    def start_episode(self, env):
        self._target: Dict[str, tuple] = {}              # junction -> (phase instance key, target total green)

    @property
    def params(self):
        return {"density_low": RULE_DENSITY_LOW, "density_medium": RULE_DENSITY_MEDIUM,
                "green_s": [RULE_GREEN_LOW, RULE_GREEN_MEDIUM, RULE_GREEN_HIGH]}

    @staticmethod
    def target_green(max_density_veh_per_km: float) -> float:
        if max_density_veh_per_km < RULE_DENSITY_LOW:
            return RULE_GREEN_LOW
        if max_density_veh_per_km < RULE_DENSITY_MEDIUM:
            return RULE_GREEN_MEDIUM
        return RULE_GREEN_HIGH

    def act(self, env, obs, masks):
        acts: Dict[str, int] = {}
        for j in env.cfg.junction_ids:
            view = env.phase_view(j)
            acts[j] = KEEP
            if not view.is_green:
                continue
            key = (view.phase, round(env.sim_time - view.elapsed_s))             # one decision per phase instance
            if self._target.get(j, (None,))[0] != key:
                dens = max(env.conn.lane.getLastStepVehicleNumber(l) / (length / 1000.0) for l, length in _served_lanes(env, j, view.phase))
                self._target[j] = (key, self.target_green(dens))
            target, total, m = self._target[j][1], view.total_s, masks[j]
            if total > target and m[REDUCE]:
                acts[j] = REDUCE
            elif total < target and m[EXTEND]:
                acts[j] = EXTEND
        return acts


class ActuatedStyleController(EvalController):
    name = "actuated_style"

    def __init__(self, min_green_s: float = 10.0, max_green_s: float = 50.0, detector_range_m: float = 40.0) -> None:
        self.min_green_s, self.max_green_s, self.detector_range_m = min_green_s, max_green_s, detector_range_m

    @property
    def params(self):
        return {"min_green_s": self.min_green_s, "max_green_s": self.max_green_s, "detector_range_m": self.detector_range_m}

    def _demand(self, env, lanes) -> int:
        """Vehicles within ``detector_range_m`` of the stop line on the given lanes."""
        n = 0
        for lane, length in lanes:
            for vid in env.conn.lane.getLastStepVehicleIDs(lane):
                if length - env.conn.vehicle.getLanePosition(vid) <= self.detector_range_m:
                    n += 1
        return n

    def act(self, env, obs, masks):
        acts: Dict[str, int] = {}
        step = env.cfg.safety.step_s
        for j in env.cfg.junction_ids:
            view = env.phase_view(j)
            acts[j] = KEEP
            if not view.is_green:
                continue
            m = masks[j]
            topo = env.topology[j]
            k = topo.green_phases.index(view.phase)
            served = _served_lanes(env, j, view.phase)
            other = [(topo.lanes[i], topo.lengths_m[i]) for i in topo.groups[1 - k]]
            d_served = self._demand(env, served)
            if view.elapsed_s >= self.min_green_s and d_served == 0 and self._demand(env, other) > 0 and m[SWITCH]:
                acts[j] = SWITCH                                                    # gap-out
            elif d_served > 0 and view.remaining_s <= step and view.total_s + step <= self.max_green_s and m[EXTEND]:
                acts[j] = EXTEND                                                    # vehicles still arriving: extend (until max-out)
        return acts


class DQNController(EvalController):
    name = "dqn"

    def __init__(self, agent: Any, info: Optional[Mapping[str, Any]] = None) -> None:
        self.agent, self.info = agent, dict(info or {})

    @property
    def params(self):
        return {"greedy": True, **{k: v for k, v in self.info.items() if k in ("sha256", "selected_episode", "val_metric", "val_score")}}

    @property
    def obs_version(self) -> str:
        return self.info.get("obs_version") or OBS_V1

    def start_episode(self, env):
        """Refuse to drive an environment whose observation schema differs from the checkpoint's (no silent mismatch)."""
        from app.training.runs import assert_schema_matches
        cfg = env.cfg
        assert_schema_matches({"obs_version": self.obs_version, "detector_range_m": self.info.get("detector_range_m")},
                              getattr(cfg, "obs_version", OBS_V1), getattr(cfg, "detector_range_m", None))
        size = getattr(env, "state_size", None)
        if size is not None and getattr(self.agent, "state_size", size) != size:
            raise ValueError(f"agent expects {self.agent.state_size} features, the environment provides {size}")

    def act(self, env, obs, masks):
        return {j: self.agent.greedy(obs[j], masks[j]) for j in env.cfg.junction_ids}


def build_controllers(names: Sequence[str], dqn: Optional[DQNController] = None) -> List[EvalController]:
    out: List[EvalController] = []
    for n in names:
        if n == "fixed_time":
            out.append(FixedTimeController())
        elif n == "rule_based":
            out.append(RuleBasedController())
        elif n == "actuated_style":
            out.append(ActuatedStyleController())
        elif n == "dqn":
            if dqn is None:
                raise ValueError("the 'dqn' controller needs a validation-selected checkpoint (--dqn-run)")
            out.append(dqn)
        else:
            raise ValueError(f"unknown controller {n!r}")
    return out
