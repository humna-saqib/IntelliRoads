"""
IntelliRoads FYP – safe signal-action handling and action masking (Stage 2).

Pure logic, no SUMO import: everything here takes the *current phase view* of one junction
(phase index, seconds elapsed in the phase, seconds remaining) and decides

* which of the four actions are **legal** right now (``legal_action_mask``),
* which TraCI command a legal action turns into, using correct *remaining-time* arithmetic
  (``command_for``),
* whether an observed phase transition respected the safety rules (``validate_transition``).

Signal programs of this network: ``G(30) y(5) G(30) y(5)`` – two green phases, each followed by
its own 5 s yellow, and **no all-red phase**.  The rules enforced are therefore:

* a yellow phase is never shortened, lengthened or skipped – while a junction is in yellow the
  only legal action is KEEP, so yellow always runs its full programmed duration;
* a green phase lasts between ``min_green_s`` and ``max_green_s`` seconds in total;
* SWITCH is legal only after the minimum green has elapsed, and it always enters the *programme's
  own* yellow (phase + 1), never jumps to another green;
* EXTEND / REDUCE change the **remaining** time of the running green by ``step_s`` (not the
  nominal duration, which the legacy code used), and only if the resulting total green stays
  inside the bounds;
* phases only ever advance ``p -> (p + 1) % n_phases``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from app.environment.observation import EnvError

# Action ids – identical to ``DQNAction`` in the legacy environment (checked by the unit tests).
KEEP, SWITCH, EXTEND, REDUCE = 0, 1, 2, 3
N_ACTIONS = 4
ACTION_NAMES = ("KEEP", "SWITCH", "EXTEND", "REDUCE")

_EPS = 1e-9


class IllegalActionError(EnvError):
    """An action was requested that is not legal in the current signal state."""


@dataclass(frozen=True)
class SignalSafetyConfig:
    min_green_s: float = 10.0               # a green may not be ended / reduced below this total length
    max_green_s: float = 60.0               # a green may not be extended beyond this total length
    step_s: float = 5.0                     # change of the remaining green per EXTEND / REDUCE
    yellow_s: float = 5.0                   # programmed yellow duration (never altered)
    min_remaining_after_reduce_s: float = 1.0   # REDUCE must leave at least this much green; SWITCH is the way to end it

    def __post_init__(self) -> None:
        if not (0 < self.min_green_s <= self.max_green_s):
            raise EnvError("need 0 < min_green_s <= max_green_s")
        if self.step_s <= 0 or self.yellow_s <= 0 or self.min_remaining_after_reduce_s < 0:
            raise EnvError("step_s and yellow_s must be positive")


@dataclass(frozen=True)
class PhaseView:
    """Snapshot of one junction's signal at a decision time."""

    phase: int
    is_green: bool
    elapsed_s: float
    remaining_s: float

    @property
    def total_s(self) -> float:
        return self.elapsed_s + self.remaining_s


@dataclass(frozen=True)
class SignalCommand:
    """``set_phase`` -> TraCI ``setPhase(value)``; ``set_remaining`` -> TraCI ``setPhaseDuration(value)``."""

    kind: str
    value: float


def legal_action_mask(view: PhaseView, cfg: SignalSafetyConfig) -> np.ndarray:
    """Boolean mask over (KEEP, SWITCH, EXTEND, REDUCE) of the actions that are legal in ``view``."""
    mask = np.zeros(N_ACTIONS, dtype=bool)
    mask[KEEP] = True                                       # waiting is always safe
    if not view.is_green:                                   # yellow: must run to completion untouched
        return mask
    mask[SWITCH] = view.elapsed_s >= cfg.min_green_s - _EPS
    mask[EXTEND] = view.total_s + cfg.step_s <= cfg.max_green_s + _EPS
    new_remaining = view.remaining_s - cfg.step_s
    mask[REDUCE] = (new_remaining >= cfg.min_remaining_after_reduce_s - _EPS
                    and view.elapsed_s + new_remaining >= cfg.min_green_s - _EPS)
    return mask


def command_for(view: PhaseView, action: int, cfg: SignalSafetyConfig, n_phases: int) -> Optional[SignalCommand]:
    """TraCI command that executes ``action`` (``None`` for KEEP). Raises ``IllegalActionError`` if not legal."""
    if action not in (KEEP, SWITCH, EXTEND, REDUCE):
        raise IllegalActionError(f"unknown action {action!r}")
    mask = legal_action_mask(view, cfg)
    if not mask[action]:
        raise IllegalActionError(
            f"{ACTION_NAMES[action]} is illegal in phase {view.phase} (green={view.is_green}, "
            f"elapsed={view.elapsed_s:g}s, remaining={view.remaining_s:g}s); legal={[ACTION_NAMES[i] for i in np.flatnonzero(mask)]}"
        )
    if action == KEEP:
        return None
    if action == SWITCH:
        return SignalCommand("set_phase", float((view.phase + 1) % n_phases))      # the programme's own yellow
    if action == EXTEND:
        return SignalCommand("set_remaining", view.remaining_s + cfg.step_s)
    return SignalCommand("set_remaining", view.remaining_s - cfg.step_s)


def validate_transition(cfg: SignalSafetyConfig, green_phases: Sequence[int], n_phases: int,
                        old_phase: int, new_phase: int, old_duration_s: float) -> Optional[str]:
    """Return an error message if the phase change ``old -> new`` (after ``old_duration_s``) is unsafe, else ``None``."""
    if new_phase != (old_phase + 1) % n_phases:
        return f"invalid phase transition {old_phase} -> {new_phase} (only {old_phase} -> {(old_phase + 1) % n_phases} is allowed)"
    if old_phase in green_phases:
        if old_duration_s < cfg.min_green_s - _EPS:
            return f"green phase {old_phase} ended after {old_duration_s:g}s < min_green {cfg.min_green_s:g}s"
        if old_duration_s > cfg.max_green_s + _EPS:
            return f"green phase {old_phase} lasted {old_duration_s:g}s > max_green {cfg.max_green_s:g}s"
    elif abs(old_duration_s - cfg.yellow_s) > _EPS:
        return f"yellow phase {old_phase} lasted {old_duration_s:g}s instead of {cfg.yellow_s:g}s"
    return None
