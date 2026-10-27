"""SUMO integration test: the live FYP controller drives the real network safely with the final obs-v2 model."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

traci = pytest.importorskip("traci")
sumolib = pytest.importorskip("sumolib")

from app.controllers.dqn_controller import ControllerMode  # noqa: E402
from app.controllers.fyp_dqn_controller import DEFAULT_MODEL_PATH, FypDQNController, load_fyp_model  # noqa: E402
from app.environment.signal_safety import SignalSafetyConfig, validate_transition  # noqa: E402
from app.sumo_tools.route_generator import generate_routefile  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
JUNCTIONS = ("junctionA", "junctionB", "junctionC", "junctionD")

pytestmark = pytest.mark.skipif(not DEFAULT_MODEL_PATH.is_file(), reason="final obs-v2 model file not present")


class _Rule:
    def __init__(self): self.calls = 0
    def update_all_signals(self, density): self.calls += 1
    def get_current_signals(self): return []


def _start(seed: int, tmp: Path) -> None:
    generate_routefile(seed=seed, output_path=tmp / "r.rou.xml", duration=3600)
    traci.start([sumolib.checkBinary("sumo"), "-c", str(BACKEND / "sumo/config/intelliroads.sumocfg"), "--route-files", str(tmp / "r.rou.xml"),
                 "--step-length", "1.0", "--no-step-log", "true", "--no-warnings", "true", "--seed", str(seed)], label=f"live_{seed}")
    traci.switch(f"live_{seed}")


def test_live_controller_decides_every_5s_and_keeps_every_phase_change_safe():
    cfg = SignalSafetyConfig()
    with tempfile.TemporaryDirectory() as d:
        _start(777, Path(d))
        try:
            agent, info = load_fyp_model()
            ctl = FypDQNController(session=None, agent=agent, info=info, rule_based_controller=_Rule(), conn=traci)
            last, violations, changes = {}, [], 0
            for _ in range(600):
                traci.simulationStep()
                signals = ctl.control_step(density_response=None)
                assert {s.junction_id for s in signals} == set(JUNCTIONS)
                for j in JUNCTIONS:
                    tr, topo = ctl._trackers[j], ctl._topo[j]
                    if j not in last:
                        last[j] = (tr.phase, tr.start)
                    elif tr.phase != last[j][0]:
                        changes += 1
                        msg = validate_transition(cfg, topo.green_phases, topo.n_phases, last[j][0], tr.phase, tr.start - last[j][1])
                        if msg:
                            violations.append((traci.simulation.getTime(), j, msg))
                        last[j] = (tr.phase, tr.start)
            assert ctl.get_mode() == ControllerMode.DQN                      # no fallback happened
            assert ctl.stats["decisions"] == 4 * (600 // 5)                  # every junction every 5 s, t = 5 ... 600
            assert sum(ctl.stats["action_counts"].values()) == ctl.stats["decisions"]
            assert changes > 0 and violations == []
        finally:
            traci.close()


def test_rule_based_mode_pauses_dqn_decisions_and_dqn_mode_resumes():
    with tempfile.TemporaryDirectory() as d:
        _start(778, Path(d))
        try:
            agent, info = load_fyp_model()
            rule = _Rule()
            ctl = FypDQNController(session=None, agent=agent, info=info, rule_based_controller=rule, conn=traci)

            def run(n):
                for _ in range(n):
                    traci.simulationStep()
                    ctl.control_step(density_response=None)

            run(60)
            before = ctl.stats["decisions"]
            ctl.set_mode("RULE_BASED"); run(30)
            assert ctl.stats["decisions"] == before and rule.calls == 30
            ctl.set_mode("DQN"); run(30)
            assert ctl.stats["decisions"] > before
        finally:
            traci.close()
