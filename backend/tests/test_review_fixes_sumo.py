"""Stage-9 review fix D5 on a real SUMO environment: an error part-way through ``step()`` ends the episode (``reset`` is
required), while an illegal action, refused before anything is applied, leaves the episode usable. Smoke seed 5,000,001 only."""

from __future__ import annotations

import pytest

pytest.importorskip("traci")
sumolib = pytest.importorskip("sumolib")

from app.environment.observation import EnvError
from app.environment.signal_safety import IllegalActionError
from app.environment.traffic_env import EnvConfig, TrafficSignalEnv

try:
    sumolib.checkBinary("sumo")
except Exception:  # pragma: no cover
    pytest.skip("SUMO binary not available", allow_module_level=True)

SEED = 5_000_001


@pytest.fixture
def env():
    e = TrafficSignalEnv(EnvConfig(horizon_s=60))
    yield e
    e.close()


def test_a_failure_while_stepping_ends_the_episode_until_reset(env, monkeypatch):
    env.reset(SEED)
    keep = {j: 0 for j in env.cfg.junction_ids}
    env.step(keep)

    def broken():
        raise RuntimeError("TraCI connection lost")

    monkeypatch.setattr(env.conn, "simulationStep", broken)
    with pytest.raises(EnvError, match="TraCI failure while stepping"):
        env.step(keep)
    monkeypatch.undo()
    with pytest.raises(EnvError, match="call reset"):                          # no confusing clock error, no silent continuation
        env.step(keep)
    env.reset(SEED)                                                             # a fresh episode works again
    assert env.step(keep).obs


def test_an_illegal_action_is_refused_without_ending_the_episode(env):
    env.reset(SEED)
    switch_now = {j: 1 for j in env.cfg.junction_ids}                          # SWITCH at t = 0 violates the minimum green
    with pytest.raises(IllegalActionError):
        env.step(switch_now)
    res = env.step({j: 0 for j in env.cfg.junction_ids})                       # nothing was applied: the episode continues
    assert res.obs and env.sim_time == 5.0
