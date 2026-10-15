"""Stage-2 unit tests: legality, remaining-time arithmetic, boundaries and transition audit (no SUMO needed).

``FakeSignal`` models SUMO's observable phase timing as measured with TraCI probes: a phase
scheduled to end at ``next_switch`` is first *seen* as the next phase at the poll one second later,
``setPhase`` takes effect immediately with the phase's full programmed duration, and
``setPhaseDuration`` sets the remaining time.  The live-SUMO tests (test_signal_safety_sumo.py)
check the real thing.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from app.agent.dqn_agent import DQNAgent
from app.environment.observation import EnvError
from app.environment.signal_safety import (
    EXTEND,
    KEEP,
    REDUCE,
    SWITCH,
    IllegalActionError,
    PhaseView,
    SignalSafetyConfig,
    command_for,
    legal_action_mask,
    validate_transition,
)
from app.environment.sumo_environment import DQNAction
from app.environment.traffic_env import EnvConfig

CFG = SignalSafetyConfig()                       # min 10, max 60, step 5, yellow 5
GREENS = (0, 2)
PROGRAM = {0: 30.0, 1: 5.0, 2: 30.0, 3: 5.0}


def view(phase=0, elapsed=0.0, remaining=30.0):
    return PhaseView(phase, phase in GREENS, float(elapsed), float(remaining))


def mask(phase=0, elapsed=0.0, remaining=30.0):
    return [bool(x) for x in legal_action_mask(view(phase, elapsed, remaining), CFG)]


def test_action_ids_match_the_legacy_action_enum():
    assert (KEEP, SWITCH, EXTEND, REDUCE) == (DQNAction.KEEP_CURRENT_PHASE, DQNAction.SWITCH_TO_NEXT_PHASE,
                                              DQNAction.EXTEND_GREEN, DQNAction.REDUCE_GREEN)


# ------------------------------------------------------------------ legality: truth table and boundaries
@pytest.mark.parametrize("phase,elapsed,remaining,expected,why", [
    (0, 0, 30, [1, 0, 1, 1], "fresh green: min green not reached -> no SWITCH"),
    (0, 9, 21, [1, 0, 1, 1], "9 s < min_green 10 s -> no SWITCH"),
    (0, 10, 20, [1, 1, 1, 1], "exactly min_green -> SWITCH legal"),
    (2, 10, 20, [1, 1, 1, 1], "second green behaves like the first"),
    (0, 29, 1, [1, 1, 1, 0], "1 s left: REDUCE would leave < 1 s -> use SWITCH instead"),
    (0, 20, 6, [1, 1, 1, 1], "REDUCE leaves exactly 1 s -> legal (boundary)"),
    (0, 20, 5, [1, 1, 1, 0], "REDUCE would leave 0 s -> illegal (boundary)"),
    (0, 0, 15, [1, 0, 1, 1], "REDUCE keeps total green at exactly min_green 10 -> legal (boundary)"),
    (0, 0, 14, [1, 0, 1, 0], "REDUCE would push total green to 9 s < min_green -> illegal"),
    (0, 25, 30, [1, 1, 1, 1], "total 55 + 5 = 60 = max_green -> EXTEND legal (boundary)"),
    (0, 26, 30, [1, 1, 0, 1], "total 56 + 5 = 61 > max_green -> EXTEND illegal"),
    (0, 30, 30, [1, 1, 0, 1], "total already 60 -> EXTEND illegal"),
    (1, 0, 5, [1, 0, 0, 0], "yellow: only KEEP"),
    (1, 3, 2, [1, 0, 0, 0], "mid-yellow: only KEEP"),
    (3, 4, 1, [1, 0, 0, 0], "last second of the second yellow: only KEEP"),
])
def test_legal_action_mask_truth_table(phase, elapsed, remaining, expected, why):
    assert mask(phase, elapsed, remaining) == [bool(x) for x in expected], why


def test_keep_is_always_legal():
    for phase in range(4):
        for e in range(0, 91, 5):
            for r in range(0, 91, 5):
                assert mask(phase, e, r)[KEEP]


def test_yellow_is_untouchable_for_every_elapsed_and_remaining_time():
    for phase in (1, 3):
        for e in range(0, 8):
            for r in range(0, 8):
                assert mask(phase, e, r) == [True, False, False, False]


# ------------------------------------------------------------------ remaining-time arithmetic
def test_extend_and_reduce_change_the_remaining_time_not_the_nominal_duration():
    # legacy code set the remaining time to nominal(30) +/- 5 regardless of how long the green had run
    assert command_for(view(0, 10, 20), EXTEND, CFG, 4).value == 25.0
    assert command_for(view(0, 10, 20), REDUCE, CFG, 4).value == 15.0
    assert command_for(view(0, 25, 5), EXTEND, CFG, 4).value == 10.0
    assert command_for(view(0, 10, 20), EXTEND, CFG, 4).kind == "set_remaining"


def test_switch_always_enters_the_programmes_own_yellow():
    assert (command_for(view(0, 12, 18), SWITCH, CFG, 4).kind, command_for(view(0, 12, 18), SWITCH, CFG, 4).value) == ("set_phase", 1.0)
    assert command_for(view(2, 12, 18), SWITCH, CFG, 4).value == 3.0


def test_keep_needs_no_command():
    assert command_for(view(), KEEP, CFG, 4) is None


@pytest.mark.parametrize("v,action", [
    (view(0, 5, 25), SWITCH), (view(1, 1, 4), SWITCH), (view(1, 1, 4), EXTEND), (view(3, 1, 4), REDUCE),
    (view(0, 30, 30), EXTEND), (view(0, 20, 5), REDUCE),
])
def test_illegal_actions_raise_with_a_helpful_message(v, action):
    with pytest.raises(IllegalActionError, match="illegal") as e:
        command_for(v, action, CFG, 4)
    assert "legal=" in str(e.value)


@pytest.mark.parametrize("bad", [-1, 4, 9])
def test_unknown_action_ids_are_rejected(bad):
    with pytest.raises(IllegalActionError, match="unknown"):
        command_for(view(), bad, CFG, 4)


# ------------------------------------------------------------------ transition audit
@pytest.mark.parametrize("old,new,dur,ok", [
    (0, 1, 30, True), (0, 1, 10, True), (0, 1, 60, True), (2, 3, 25, True),
    (1, 2, 5, True), (3, 0, 5, True),
    (0, 1, 9, False), (0, 1, 61, False),                      # green outside [10, 60]
    (1, 2, 4, False), (1, 2, 6, False), (3, 0, 0, False),      # yellow shortened / lengthened / skipped
    (0, 2, 30, False), (1, 0, 5, False), (2, 0, 30, False),    # not the next phase in the cycle
])
def test_validate_transition(old, new, dur, ok):
    msg = validate_transition(CFG, GREENS, 4, old, new, dur)
    assert (msg is None) == ok, msg


def test_config_validation():
    for kwargs in (dict(min_green_s=0), dict(min_green_s=20, max_green_s=10), dict(step_s=0), dict(yellow_s=0)):
        with pytest.raises(EnvError):
            SignalSafetyConfig(**kwargs)
    with pytest.raises(EnvError):
        EnvConfig(on_illegal_action="ignore")
    assert EnvConfig().on_illegal_action == "raise" and EnvConfig().strict_safety is True


# ------------------------------------------------------------------ simulated signal: repeated actions and a property test
class FakeSignal:
    """Observable SUMO phase timing (see module docstring)."""

    def __init__(self, program=PROGRAM):
        self.program, self.t, self.phase, self.start, self.next_switch = program, 0, 0, 0, program[0]
        self.log = []                                    # (phase, duration) of every completed phase

    def view(self):
        return view(self.phase, self.t - self.start, self.next_switch - self.t)

    def tick(self):
        self.t += 1
        if self.t == self.next_switch + 1:               # a scheduled switch is seen one poll late
            self._advance(self.next_switch)

    def _advance(self, end):
        self.log.append((self.phase, end - self.start))
        self.phase, self.start = (self.phase + 1) % 4, end
        self.next_switch = end + self.program[self.phase]

    def apply(self, action):
        cmd = command_for(self.view(), action, CFG, 4)
        if cmd is None:
            return
        if cmd.kind == "set_phase":
            self.log.append((self.phase, self.t - self.start))
            self.phase, self.start = int(cmd.value), self.t
            self.next_switch = self.t + self.program[self.phase]
        else:
            self.next_switch = self.t + cmd.value


def run_policy(sig, policy, decisions, interval=5):
    for _ in range(decisions):
        sig.apply(policy(sig))
        for _ in range(interval):
            sig.tick()


@pytest.mark.parametrize("interval", [1, 5])
def test_repeated_extension_stops_exactly_at_max_green_and_yellow_is_untouched(interval):
    sig = FakeSignal()
    def policy(s):
        m = legal_action_mask(s.view(), CFG)
        return EXTEND if m[EXTEND] else KEEP
    run_policy(sig, policy, 80 // interval, interval)
    assert sig.log[0] == (0, 60.0), "legacy code could extend forever; now the first green ends at exactly max_green"
    assert sig.log[1] == (1, 5.0)
    assert all(d <= CFG.max_green_s for p, d in sig.log if p in GREENS)


@pytest.mark.parametrize("interval,expected_green", [(1, 10.0), (5, 15.0)])
def test_repeated_reduction_is_bounded_by_min_green_and_by_the_one_second_floor(interval, expected_green):
    """Decided every second the min-green rule binds (green ends at exactly 10 s); decided every 5 s the
    rule 'REDUCE must leave >= 1 s of green' binds first (15 s).  Either way green never drops below 10 s
    and the yellow that follows is a full 5 s."""
    sig = FakeSignal()
    def policy(s):
        m = legal_action_mask(s.view(), CFG)
        return REDUCE if m[REDUCE] else KEEP
    run_policy(sig, policy, 40 // interval, interval)
    assert sig.log[0] == (0, expected_green) and sig.log[1] == (1, 5.0)
    assert sig.log[0][1] >= CFG.min_green_s


def test_extend_then_reduce_returns_to_the_original_length():
    sig = FakeSignal()
    seq = iter([KEEP, KEEP, EXTEND, REDUCE])               # decisions at t = 0, 5, 10, 15
    run_policy(sig, lambda s: next(seq, KEEP), 8)
    assert sig.log[0] == (0, 30.0)


def test_switch_before_min_green_is_rejected_and_at_min_green_gives_a_full_yellow():
    sig = FakeSignal()
    run_policy(sig, lambda s: KEEP, 1)                      # t = 5
    with pytest.raises(IllegalActionError):
        sig.apply(SWITCH)
    run_policy(sig, lambda s: KEEP, 1)                      # t = 10 -> exactly min_green
    sig.apply(SWITCH)
    for _ in range(12):
        sig.tick()
    assert sig.log[0] == (0, 10.0) and sig.log[1] == (1, 5.0)


@pytest.mark.parametrize("seed", range(5))
def test_random_legal_actions_never_violate_the_safety_rules(seed):
    rng = np.random.default_rng(seed)
    sig = FakeSignal()
    for _ in range(4000):                                    # 20,000 simulated seconds
        legal = np.flatnonzero(legal_action_mask(sig.view(), CFG))
        sig.apply(int(rng.choice(legal)))
        for _ in range(int(rng.choice([1, 2, 5]))):          # decision intervals of 1, 2 or 5 s
            sig.tick()
    assert len(sig.log) > 200
    prev_phase = None
    for phase, duration in sig.log:
        if prev_phase is not None:
            assert phase == (prev_phase + 1) % 4
        prev_phase = phase
        if phase in GREENS:
            assert CFG.min_green_s <= duration <= CFG.max_green_s
        else:
            assert duration == CFG.yellow_s
    for (p0, d0), (p1, _) in zip(sig.log, sig.log[1:]):
        assert validate_transition(CFG, GREENS, 4, p0, p1, d0) is None


def test_every_action_on_every_reachable_state_is_either_rejected_or_safe():
    """Exhaustive check on the model: from any (phase, elapsed, remaining) any *legal* action keeps the phase valid."""
    for phase in range(4):
        for e in range(0, 61):
            for r in range(0, 61):
                v = view(phase, e, r)
                if v.is_green and not (CFG.min_green_s <= e + r <= CFG.max_green_s):
                    continue                                   # unreachable: a green's total length is always within bounds
                for a in np.flatnonzero(legal_action_mask(v, CFG)):
                    cmd = command_for(v, int(a), CFG, 4)
                    if cmd is None:
                        continue
                    if cmd.kind == "set_remaining":
                        total = e + cmd.value
                        assert v.is_green and CFG.min_green_s <= total <= CFG.max_green_s and cmd.value >= 1
                    else:
                        assert v.is_green and e >= CFG.min_green_s and int(cmd.value) == (phase + 1) % 4


# ------------------------------------------------------------------ agent integration (masking)
class _FixedQ(torch.nn.Module):
    def __init__(self, q):
        super().__init__()
        self.q = torch.tensor([q], dtype=torch.float32)

    def forward(self, x):
        return self.q.expand(x.shape[0], -1)


def _agent(q):
    agent = DQNAgent(state_size=11, action_size=4, device="cpu", normalize_inputs=False)
    agent.policy_net = _FixedQ(q)
    return agent


S = [0.0] * 11


def test_greedy_action_respects_the_mask():
    agent = _agent([0.1, 9.0, 0.2, 0.3])
    assert agent.select_action(S, epsilon=0.0) == 1                                # unmasked: the illegal SWITCH
    assert agent.select_action(S, epsilon=0.0, legal_mask=[True, False, True, True]) == 3
    assert agent.select_action(S, epsilon=0.0, legal_mask=[True, False, False, False]) == 0


def test_exploration_only_samples_legal_actions():
    agent = _agent([0.0] * 4)
    draws = {agent.select_action(S, epsilon=1.0, legal_mask=[True, False, True, False]) for _ in range(300)}
    assert draws == {0, 2}


def test_invalid_masks_are_rejected_and_unmasked_behaviour_is_unchanged():
    agent = _agent([0.1, 9.0, 0.2, 0.3])
    with pytest.raises(ValueError, match="no legal action"):
        agent.select_action(S, epsilon=0.0, legal_mask=[False] * 4)
    with pytest.raises(ValueError, match="entries"):
        agent.select_action(S, epsilon=0.0, legal_mask=[True, True])
    assert 0 <= agent.select_action(S, epsilon=1.0) < 4
