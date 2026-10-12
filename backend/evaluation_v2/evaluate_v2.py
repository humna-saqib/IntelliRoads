"""
IntelliRoads - corrected controller evaluation (v2).

Purpose: establish the performance of the EXISTING checkpoint under a fair
evaluation. Does not modify the model, reward, training code or checkpoint.

What changed relative to backend/evaluate_controllers.py (which is untouched):
  * One shared episode runner and one shared measurement function for all
    controllers. Pipeline per simulation second:
        session.step() -> controller acts -> measure ALL four junctions.
  * The DQN/Always-Keep path no longer `break`s out of the junction loop when
    SUMOEnvironment.step() returns done=True. Root cause: the environment counts
    one step per junction call and flags done after 3,600 calls (= 900 s with 4
    junctions); the old loop then measured only junction A but still divided by 4.
    The environment's done flag does NOT close or reset SUMO, so evaluation-only
    `_max_steps` is raised above the horizon and we assert done never fires.
  * Per-controller measurement counts are recorded and asserted.
  * "Always-Keep" (action 0 at every decision) is evaluated through the exact
    same DQN code path with a stub agent.
  * Throughput is recorded two ways: departed (demand inserted) and arrived
    (vehicles that completed their trip). The legacy metric was departed.

Usage (from backend/):  SUMO_USE_GUI=false python evaluation_v2/evaluate_v2.py
"""
from __future__ import annotations

import collections
import csv
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("SUMO_USE_GUI", "false")
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

import traci  # noqa: E402

import evaluate_controllers as ev  # noqa: E402  (read-only reuse of helpers)
from app.agent.dqn_agent import DQNAgent  # noqa: E402
from app.environment.sumo_environment import SUMOEnvironment  # noqa: E402
from app.services.signal_controller import SignalController  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
N_EPISODES = int(os.environ.get("EVAL_V2_EPISODES", "30"))
N_STEPS = 1800
JUNCTIONS = ev.JUNCTION_IDS
CONTROLLERS = ["Fixed-Time", "Rule-Based", "Always-Keep", "Trained DQN"]


class KeepAgent:
    """Stub agent: action 0 (KEEP_CURRENT_PHASE) at every decision."""

    def select_action(self, state, epsilon=0.0):
        return 0


class Measurer:
    """Single measurement implementation used by every controller."""

    def __init__(self) -> None:
        self.waits: List[float] = []
        self.queues: List[float] = []
        self.occs: List[float] = []
        self.cong: List[float] = []
        self.n_junction_obs = 0
        self.departed = 0
        self.arrived = 0
        self.depart_times: Dict[str, float] = {}
        self.travel_times: List[float] = []

    def vehicle_events(self) -> None:
        now = traci.simulation.getTime()
        self.departed += int(traci.simulation.getDepartedNumber())
        for vid in traci.simulation.getDepartedIDList():
            self.depart_times[vid] = now
        arrived_ids = traci.simulation.getArrivedIDList()
        self.arrived += len(arrived_ids)
        for vid in arrived_ids:
            t0 = self.depart_times.pop(vid, None)
            if t0 is not None:
                self.travel_times.append(now - t0)

    def junctions(self) -> None:
        w = q = o = v = 0.0
        for jid in JUNCTIONS:  # ALWAYS all four junctions, no early exit
            m = ev._collect_junction_metrics(jid)
            w += m["avg_wait"]; q += m["queue_len"]; o += m["occupancy"]; v += m["veh_count"]
            self.n_junction_obs += 1
        n = len(JUNCTIONS)
        self.waits.append(w / n); self.queues.append(q / n); self.occs.append(o / n)
        self.cong.append(float((o / n > 70.0) or (v / n > 15.0)))

    def result(self, n_steps: int, extra: Dict[str, Any]) -> Dict[str, Any]:
        assert len(self.waits) == n_steps, (len(self.waits), n_steps)
        assert self.n_junction_obs == n_steps * len(JUNCTIONS), self.n_junction_obs
        return {
            "avg_waiting_time": statistics.mean(self.waits),
            "avg_travel_time": statistics.mean(self.travel_times) if self.travel_times else 0.0,
            "avg_queue_length": statistics.mean(self.queues),
            "avg_occupancy": statistics.mean(self.occs),
            "pct_congested": 100.0 * statistics.mean(self.cong),
            "throughput_arrived": self.arrived,
            "throughput_departed": self.departed,
            # measurement counts (verified below and saved)
            "n_steps_measured": len(self.waits),
            "n_junction_obs": self.n_junction_obs,
            "n_travel_time_obs": len(self.travel_times),
            **extra,
        }


def run_episode(controller: str, agent: Any, seed: int) -> Dict[str, Any]:
    ev.generate_routefile(seed=seed, output_path=ev.ROUTE_FILE_PATH)
    session = ev.make_session()
    meas = Measurer()
    actions = collections.Counter()
    done_flags = 0
    try:
        sc = SignalController(session) if controller == "Rule-Based" else None
        env = None
        last_phase: Dict[str, int] = {}
        if controller in ("Always-Keep", "Trained DQN"):
            env = SUMOEnvironment(session=session)
            env._max_steps = 10 ** 9  # eval-only: env 'done' counts calls, not seconds
            env.reset()
        if controller == "Fixed-Time":
            for jid in JUNCTIONS:  # identical to legacy Fixed-Time setup
                try:
                    traci.trafficlight.setPhaseDuration(jid, ev.FIXED_GREEN_DURATION)
                except Exception:
                    pass

        for _ in range(N_STEPS):
            session.step()
            meas.vehicle_events()
            # ---- controller acts ----
            if controller == "Fixed-Time":
                for jid in JUNCTIONS:
                    try:
                        ph = traci.trafficlight.getPhase(jid)
                        if ph != last_phase.get(jid, -1):
                            last_phase[jid] = ph
                            traci.trafficlight.setPhaseDuration(
                                jid, ev.FIXED_GREEN_DURATION if ph % 2 == 0 else ev.FIXED_YELLOW_DURATION)
                    except Exception:
                        pass
            elif controller == "Rule-Based":
                sc.update_all_signals(ev._build_density_response())
            else:
                for jid in JUNCTIONS:
                    state = env.get_state(junction_id=jid)
                    a = agent.select_action(state, epsilon=0.0)
                    actions[a] += 1
                    _, _, done, _ = env.step(action=a, junction_id=jid, throughput=0)
                    done_flags += int(done)
            # ---- identical measurement for everyone ----
            meas.junctions()
        extra = {f"action_{i}": actions.get(i, 0) for i in range(4)}
        extra["done_flags"] = done_flags
        if controller in ("Always-Keep", "Trained DQN"):
            assert done_flags == 0, "environment signalled done inside the horizon"
            assert sum(actions.values()) == N_STEPS * len(JUNCTIONS)
        return meas.result(N_STEPS, extra)
    finally:
        session.close()


def main() -> None:
    ckpt = ev.CHECKPOINT_PATH
    sha = hashlib.sha256(ckpt.read_bytes()).hexdigest()
    agent = DQNAgent(state_size=5, action_size=4)
    agent.load(ckpt)
    agent.policy_net.eval()
    agents = {"Always-Keep": KeepAgent(), "Trained DQN": agent}
    config = {
        "n_episodes": N_EPISODES, "n_steps": N_STEPS, "junctions": JUNCTIONS,
        "seed_offset": ev.EVAL_SEED_OFFSET, "seeds": [ev.EVAL_SEED_OFFSET + i for i in range(1, N_EPISODES + 1)],
        "controllers": CONTROLLERS, "checkpoint": str(ckpt.relative_to(_BACKEND)),
        "checkpoint_sha256": sha, "epsilon": 0.0,
        "sumo_step_length": 1.0, "sumo_seed": "SUMO default (not set in sumocfg)",
        "env_max_steps_override": 10 ** 9,
        "metric_definitions": {
            "avg_waiting_time": "mean over steps of mean over 4 junctions of primary-lane getWaitingTime/max(vehicles,1)",
            "avg_queue_length": "mean over steps of mean over 4 junctions of primary-lane getLastStepHaltingNumber",
            "avg_occupancy": "mean over steps of mean over 4 junctions of primary-lane getLastStepOccupancy*100",
            "avg_travel_time": "mean (arrival - departure) over vehicles that ARRIVED within the horizon",
            "throughput_arrived": "vehicles arrived within horizon", "throughput_departed": "vehicles inserted within horizon",
        },
    }
    (OUT_DIR / "config_v2.json").write_text(json.dumps(config, indent=2))
    rows: List[Dict[str, Any]] = []
    t_all = time.time()
    for ep in range(1, N_EPISODES + 1):
        for c in CONTROLLERS:
            t0 = time.time()
            r = run_episode(c, agents.get(c), ev.EVAL_SEED_OFFSET + ep)
            rows.append({"controller": c, "episode": ep, "seed": ev.EVAL_SEED_OFFSET + ep, **r,
                         "wall_time_s": round(time.time() - t0, 2)})
            print(f"[{ep:2d}/{N_EPISODES}] {c:12s} wait={r['avg_waiting_time']:.3f} "
                  f"queue={r['avg_queue_length']:.3f} tt={r['avg_travel_time']:.2f} "
                  f"obs={r['n_junction_obs']}", flush=True)
        with open(OUT_DIR / "eval_raw_v2.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"done in {time.time()-t_all:.0f}s", flush=True)


if __name__ == "__main__":
    main()
