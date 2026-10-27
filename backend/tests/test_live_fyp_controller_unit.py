"""Unit tests (no SUMO) for the live FYP controller: strict model loading, phase bookkeeping, model selection and fallback."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.controllers.dqn_controller import ControllerMode
from app.controllers import fyp_dqn_controller as live
from app.controllers.fyp_dqn_controller import (
    DEFAULT_MODEL_PATH,
    DEFAULT_MODEL_SHA256,
    FypDQNController,
    FypModelError,
    PhaseTracker,
    load_fyp_model,
    try_build_fyp_controller,
)

LEGACY_MODEL = Path(__file__).resolve().parent.parent / "data" / "models" / "dqn_agent.pt"
needs_model = pytest.mark.skipif(not DEFAULT_MODEL_PATH.is_file(), reason="final obs-v2 model file not present")


class _FakeTL:
    def __init__(self, phase: int, next_switch: float, duration: float) -> None:
        self.phase, self.next_switch, self.duration = phase, next_switch, duration

    def getPhase(self, j): return self.phase
    def getNextSwitch(self, j): return self.next_switch
    def getPhaseDuration(self, j): return self.duration


def _conn(phase=0, next_switch=30.0, duration=30.0):
    return SimpleNamespace(trafficlight=_FakeTL(phase, next_switch, duration))


# ------------------------------------------------------------------ model loading
@needs_model
def test_final_model_loads_with_pinned_hash_and_schema():
    agent, info = load_fyp_model()
    assert info["sha256"] == DEFAULT_MODEL_SHA256
    assert (info["obs_version"], info["state_size"], info["n_actions"], info["hidden"], info["selected_episode"]) == ("fyp-obs-v2", 15, 4, 64, 240)
    assert agent.policy_net.training is False


@needs_model
def test_altered_hash_is_refused():
    with pytest.raises(FypModelError, match="does not match"):
        load_fyp_model(DEFAULT_MODEL_PATH, expected_sha256="0" * 64)


def test_missing_file_is_refused(tmp_path):
    with pytest.raises(FypModelError, match="not found"):
        load_fyp_model(tmp_path / "nope.pt")


@pytest.mark.skipif(not LEGACY_MODEL.is_file(), reason="legacy model not present")
def test_legacy_five_feature_model_is_refused_not_reshaped():
    with pytest.raises(FypModelError, match="not a usable FYP checkpoint"):
        load_fyp_model(LEGACY_MODEL, expected_sha256=None)


# ------------------------------------------------------------------ phase bookkeeping
def test_tracker_initial_elapsed_from_schedule():
    tr = PhaseTracker(_conn(phase=0, next_switch=30.0, duration=30.0), "junctionA", now=0.0)
    assert (tr.phase, tr.start, tr.next_switch) == (0, 0.0, 30.0)


def test_tracker_natural_switch_starts_at_scheduled_end():
    conn = _conn()
    tr = PhaseTracker(conn, "junctionA", 0.0)
    conn.trafficlight.phase, conn.trafficlight.next_switch = 1, 35.0
    tr.update(conn, now=31.0)                       # TraCI reports the switch one second after its scheduled time
    assert (tr.phase, tr.start, tr.next_switch) == (1, 30.0, 35.0)


def test_tracker_manual_or_external_change_starts_now():
    conn = _conn()
    tr = PhaseTracker(conn, "junctionA", 0.0)
    conn.trafficlight.phase, conn.trafficlight.next_switch = 1, 20.0
    tr.update(conn, now=15.0, manual=True)          # our own SWITCH
    assert tr.start == 15.0
    conn.trafficlight.phase, conn.trafficlight.next_switch = 2, 90.0
    tr.update(conn, now=18.0)                       # another service (e.g. emergency priority) changed the phase early
    assert (tr.phase, tr.start) == (2, 18.0)


def test_tracker_view_never_negative():
    conn = _conn()
    tr = PhaseTracker(conn, "junctionA", 0.0)
    v = tr.view(now=31.0, green_phases=(0, 2))
    assert v.remaining_s == 0.0 and v.elapsed_s == 31.0 and v.is_green


# ------------------------------------------------------------------ model selection and fallback
def test_legacy_selector_keeps_legacy_controller(monkeypatch):
    monkeypatch.setenv(live.MODEL_SELECTOR_ENV, "legacy")
    assert try_build_fyp_controller(SimpleNamespace(mock_mode=False), None) is None


def test_mock_mode_keeps_legacy_controller(monkeypatch):
    monkeypatch.delenv(live.MODEL_SELECTOR_ENV, raising=False)
    assert try_build_fyp_controller(SimpleNamespace(mock_mode=True), None) is None


def test_missing_model_keeps_legacy_controller(monkeypatch, tmp_path):
    monkeypatch.delenv(live.MODEL_SELECTOR_ENV, raising=False)
    monkeypatch.setattr(live, "DEFAULT_MODEL_PATH", tmp_path / "missing.pt")
    monkeypatch.setattr(live, "load_fyp_model", lambda: (_ for _ in ()).throw(FypModelError("missing")))
    assert try_build_fyp_controller(SimpleNamespace(mock_mode=False), None) is None


class _Rule:
    def __init__(self): self.calls = 0
    def update_all_signals(self, density): self.calls += 1
    def get_current_signals(self): return ["rule-signal"]


@needs_model
def test_failure_in_dqn_mode_falls_back_to_rule_based():
    agent, info = load_fyp_model()
    rule = _Rule()
    conn = SimpleNamespace(simulation=SimpleNamespace(getTime=lambda: 5.0),
                           trafficlight=SimpleNamespace(getIDList=lambda: ()))          # no junctions -> initialisation fails
    ctl = FypDQNController(session=None, agent=agent, info=info, rule_based_controller=rule, conn=conn)
    out = ctl.control_step(density_response=None)
    assert out == ["rule-signal"] and ctl.get_mode() == ControllerMode.RULE_BASED and rule.calls == 1


@needs_model
def test_mode_strings_and_describe():
    agent, info = load_fyp_model()
    ctl = FypDQNController(session=None, agent=agent, info=info, conn=SimpleNamespace())
    ctl.set_mode("rule_based")
    assert ctl.get_mode() == ControllerMode.RULE_BASED
    ctl.set_mode("DQN")
    d = ctl.describe()
    assert d["mode"] == "DQN" and d["sha256"] == DEFAULT_MODEL_SHA256 and d["safety"]["max_green_s"] == 60.0
    assert d["stats"]["decisions"] == 0


# ------------------------------------------------------------------ Windows compatibility
def test_live_controller_imports_without_fcntl():
    """The live backend must start on Windows: the controller may not import any module that needs ``fcntl`` (Linux only)."""
    import subprocess
    import sys
    code = ("import sys; sys.modules['fcntl'] = None\n"      # makes 'import fcntl' raise ImportError, as on Windows
            "import app.main; import app.controllers.fyp_dqn_controller as c; print('ok', c.DEFAULT_MODEL_SHA256[:8])")
    out = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "ok e7bc8722" in out.stdout, out.stderr[-800:]


@needs_model
def test_policy_hash_matches_the_evaluation_definition():
    from app.evaluation.protocol import policy_weights_sha256 as eval_hash
    agent, info = load_fyp_model()
    assert info["policy_sha256"] == eval_hash(agent)
