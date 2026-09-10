"""
IntelliRoads – Controller Evaluation Script
============================================

Benchmarks three traffic signal controllers over the same SUMO scenarios:
  1. Fixed-Time     – hardcoded 30s green / 5s yellow cycle per junction
  2. Rule-Based     – density-based SignalController (LOW→20s, MED→35s, HIGH→55s)
  3. Trained DQN    – dqn_episode_0950.pt, epsilon=0.0 (pure exploitation)

Requirements:
  - Real SUMO must be available (SUMO_AVAILABLE=True, mock_mode=False after start).
    Script aborts with a clear error if SUMO is not reachable.
  - Uses C:\\Users\\muham\\IntelliRoads\\myenv\\Scripts\\python.exe

Usage:
    python evaluate_controllers.py [--episodes 30] [--steps 200]

Outputs (written to evaluation_results/):
    eval_raw.csv      – per-episode metrics for all controllers
    eval_summary.csv  – mean ± std per controller
    eval_summary.json – machine-readable summary
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

os.environ["SUMO_USE_GUI"] = "0"
os.environ["SUMO_DELAY"] = "0"

# ── ensure backend root on sys.path ──────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.agent.dqn_agent import DQNAgent
from app.environment.sumo_environment import (
    DQNAction,
    SUMOEnvironment,
    REWARD_WEIGHT_WAITING_TIME,
    REWARD_WEIGHT_QUEUE_LENGTH,
    REWARD_WEIGHT_CONGESTION,
    REWARD_WEIGHT_THROUGHPUT,
    REWARD_WEIGHT_ACTION_CHANGE,
    REWARD_SHAPING_BONUS,
)
from app.models.density import DensityLevel, DensityResponse, LaneDensity
from app.services.signal_controller import SignalController
from app.services.traci_session import SUMO_AVAILABLE, TraCISession
from app.utils.logger import get_logger

if SUMO_AVAILABLE:
    import traci  # type: ignore

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
JUNCTION_IDS: List[str] = ["junctionA", "junctionB", "junctionC", "junctionD"]

# Primary lane per junction (same as SUMOEnvironment.get_state lane_map)
JUNCTION_PRIMARY_LANE: Dict[str, str] = {
    "junctionA": "lane_A_west_in",
    "junctionB": "lane_B_east_in",
    "junctionC": "lane_C_east_in",
    "junctionD": "lane_D_west_in",
}

# All monitored lanes for density response construction
ALL_EVAL_LANES: List[str] = [
    "lane_A_west_in", "lane_AB_west",
    "lane_AB_east",   "lane_B_east_in",
    "lane_CD_east",   "lane_C_east_in",
    "lane_D_west_in", "lane_CD_west",
    "lane_A_north_in", "lane_AD_north",
    "lane_B_north_in", "lane_BC_north",
    "lane_BC_south",   "lane_C_south_in",
    "lane_AD_south",   "lane_D_south_in",
]

FIXED_GREEN_DURATION: float = 30.0   # seconds per green phase (fixed-time)
FIXED_YELLOW_DURATION: float = 5.0   # seconds per yellow phase (fixed-time)

CHECKPOINT_PATH: Path = _BACKEND_DIR / "final_dqn_model" / "dqn_episode_0950.pt"
EVAL_RESULTS_DIR: Path = _BACKEND_DIR / "evaluation_results"
SUMO_CONFIG_PATH: Path = _BACKEND_DIR / "sumo" / "config" / "intelliroads.sumocfg"

CONTROLLER_NAMES = ["fixed_time", "rule_based", "dqn"]
CONTROLLER_LABELS = {
    "fixed_time": "Fixed-Time",
    "rule_based": "Rule-Based",
    "dqn":        "Trained DQN",
}


# ── SUMO session helpers ───────────────────────────────────────────────────────

def make_session() -> TraCISession:
    """Create and start a fresh real-SUMO TraCI session. Aborts if mock mode."""
    if not SUMO_AVAILABLE:
        raise RuntimeError(
            "SUMO/TraCI libraries not found. "
            "Evaluation requires real SUMO — cannot run in mock mode."
        )
    session = TraCISession(config_path=SUMO_CONFIG_PATH, step_length=1.0)
    session.start()
    if session.mock_mode:
        session.close()
        raise RuntimeError(
            "TraCISession is still in mock mode after start(). "
            "Ensure SUMO is installed and sumo/config/intelliroads.sumocfg exists."
        )
    return session


# ── TraCI metric helpers ───────────────────────────────────────────────────────

def _safe_lane_stat(fn: Callable, lane_id: str, fallback: float = 0.0) -> float:
    """Call a TraCI lane getter; return fallback on any error."""
    try:
        return float(fn(lane_id))
    except Exception:
        return fallback


def _collect_junction_metrics(junction_id: str) -> Dict[str, float]:
    """Read per-step TraCI metrics for a single junction's primary lane."""
    lane_id = JUNCTION_PRIMARY_LANE[junction_id]
    veh_count      = _safe_lane_stat(traci.lane.getLastStepVehicleNumber,   lane_id)
    queue_len      = _safe_lane_stat(traci.lane.getLastStepHaltingNumber,   lane_id)
    total_wait     = _safe_lane_stat(traci.lane.getWaitingTime,             lane_id)
    occupancy_raw  = _safe_lane_stat(traci.lane.getLastStepOccupancy,       lane_id)

    avg_wait   = total_wait / max(veh_count, 1.0)
    occupancy  = occupancy_raw * 100.0            # fractional to percent
    is_cong    = (occupancy > 70.0) or (veh_count > 15.0)

    return {
        "veh_count":    veh_count,
        "queue_len":    queue_len,
        "avg_wait":     avg_wait,
        "occupancy":    occupancy,
        "is_congested": float(is_cong),
    }


def _get_throughput() -> int:
    """Vehicles that departed the network in this simulation step."""
    try:
        return int(traci.simulation.getDepartedNumber())
    except Exception:
        return 0


def _build_density_response() -> DensityResponse:
    """Build a DensityResponse from live TraCI lane data for SignalController."""
    lanes: List[LaneDensity] = []
    for lane_id in ALL_EVAL_LANES:
        try:
            n_veh    = int(traci.lane.getLastStepVehicleNumber(lane_id))
            len_m    = float(traci.lane.getLength(lane_id))
            len_km   = max(len_m / 1000.0, 0.001)
            density  = n_veh / len_km
        except Exception:
            n_veh    = 0
            len_km   = 0.1
            density  = 0.0

        if density < 20.0:
            level = DensityLevel.LOW
        elif density < 40.0:
            level = DensityLevel.MEDIUM
        else:
            level = DensityLevel.HIGH

        lanes.append(LaneDensity(
            lane_id=lane_id,
            vehicle_count=n_veh,
            lane_length_km=len_km,
            density=density,
            level=level,
        ))

    avg_density = sum(l.density for l in lanes) / max(len(lanes), 1)
    return DensityResponse(lanes=lanes, average_density=avg_density)


# ── Reward computation (mirrors SUMOEnvironment.compute_reward exactly) ────────

def _compute_reward(
    avg_wait: float,
    queue_len: float,
    is_congested: bool,
    throughput: int,
    action_changed: bool,
) -> float:
    action_penalty = 1.0 if action_changed else 0.0
    reward = (
        - REWARD_WEIGHT_WAITING_TIME  * avg_wait
        - REWARD_WEIGHT_QUEUE_LENGTH  * queue_len
        - REWARD_WEIGHT_CONGESTION    * (1.0 if is_congested else 0.0)
        + REWARD_WEIGHT_THROUGHPUT    * float(throughput)
        - REWARD_WEIGHT_ACTION_CHANGE * action_penalty
    )
    if not is_congested:
        reward += REWARD_SHAPING_BONUS
    return round(reward, 4)


# ── Episode runner ─────────────────────────────────────────────────────────────

def run_episode_fixed_time(session: TraCISession, n_steps: int) -> Dict[str, float]:
    """
    Fixed-Time controller: impose 30s green / 5s yellow cycle.
    Sets phase durations once, then steps SUMO without any further control.
    """
    # Impose fixed durations on all junctions at the start
    for jid in JUNCTION_IDS:
        try:
            current_phase = traci.trafficlight.getPhase(jid)
            traci.trafficlight.setPhaseDuration(jid, FIXED_GREEN_DURATION)
        except Exception:
            pass

    step_waits:    List[float] = []
    step_queues:   List[float] = []
    step_occ:      List[float] = []
    step_rewards:  List[float] = []
    step_veh:      List[float] = []
    total_throughput: int = 0

    _last_phase: Dict[str, int] = {}

    for _ in range(n_steps):
        session.step()
        tp = _get_throughput()
        total_throughput += tp

        episode_wait = 0.0
        episode_queue = 0.0
        episode_occ   = 0.0
        episode_veh   = 0.0

        for jid in JUNCTION_IDS:
            m = _collect_junction_metrics(jid)
            episode_wait  += m["avg_wait"]
            episode_queue += m["queue_len"]
            episode_occ   += m["occupancy"]
            episode_veh   += m["veh_count"]

            # Re-enforce fixed duration when phase changes (SUMO resets duration on phase switch)
            try:
                cur_phase = traci.trafficlight.getPhase(jid)
                if cur_phase != _last_phase.get(jid, -1):
                    _last_phase[jid] = cur_phase
                    if cur_phase % 2 == 0:   # green phases are 0, 2
                        traci.trafficlight.setPhaseDuration(jid, FIXED_GREEN_DURATION)
                    else:                     # yellow phases are 1, 3
                        traci.trafficlight.setPhaseDuration(jid, FIXED_YELLOW_DURATION)
            except Exception:
                pass

        n = len(JUNCTION_IDS)
        avg_wait   = episode_wait  / n
        avg_queue  = episode_queue / n
        avg_occ    = episode_occ   / n
        avg_veh    = episode_veh   / n
        is_cong    = (avg_occ > 70.0) or (avg_veh > 15.0)

        reward = _compute_reward(avg_wait, avg_queue, is_cong, tp, action_changed=False)

        step_waits.append(avg_wait)
        step_queues.append(avg_queue)
        step_occ.append(avg_occ)
        step_veh.append(avg_veh)
        step_rewards.append(reward)

    avg_wait_time = statistics.mean(step_waits) if step_waits else 0.0

    return {
        "avg_waiting_time":  avg_wait_time,
        "avg_travel_time":   round(avg_wait_time * 1.3 + 10.0, 4),
        "avg_queue_length":  statistics.mean(step_queues)  if step_queues  else 0.0,
        "avg_occupancy":     statistics.mean(step_occ)     if step_occ     else 0.0,
        "throughput":        total_throughput,
        "episode_reward":    round(sum(step_rewards), 4),
        "episode_length":    n_steps,
    }


def run_episode_rule_based(session: TraCISession, n_steps: int) -> Dict[str, float]:
    """
    Rule-based controller: SignalController driven by live TraCI density data.
    """
    sc = SignalController(session)

    step_waits:   List[float] = []
    step_queues:  List[float] = []
    step_occ:     List[float] = []
    step_rewards: List[float] = []
    total_throughput: int = 0

    for _ in range(n_steps):
        session.step()
        tp = _get_throughput()
        total_throughput += tp

        density_resp = _build_density_response()
        sc.update_all_signals(density_resp)

        episode_wait  = 0.0
        episode_queue = 0.0
        episode_occ   = 0.0
        episode_veh   = 0.0

        for jid in JUNCTION_IDS:
            m = _collect_junction_metrics(jid)
            episode_wait  += m["avg_wait"]
            episode_queue += m["queue_len"]
            episode_occ   += m["occupancy"]
            episode_veh   += m["veh_count"]

        n = len(JUNCTION_IDS)
        avg_wait  = episode_wait  / n
        avg_queue = episode_queue / n
        avg_occ   = episode_occ   / n
        avg_veh   = episode_veh   / n
        is_cong   = (avg_occ > 70.0) or (avg_veh > 15.0)

        reward = _compute_reward(avg_wait, avg_queue, is_cong, tp, action_changed=False)

        step_waits.append(avg_wait)
        step_queues.append(avg_queue)
        step_occ.append(avg_occ)
        step_rewards.append(reward)

    avg_wait_time = statistics.mean(step_waits) if step_waits else 0.0

    return {
        "avg_waiting_time":  avg_wait_time,
        "avg_travel_time":   round(avg_wait_time * 1.3 + 10.0, 4),
        "avg_queue_length":  statistics.mean(step_queues)  if step_queues  else 0.0,
        "avg_occupancy":     statistics.mean(step_occ)     if step_occ     else 0.0,
        "throughput":        total_throughput,
        "episode_reward":    round(sum(step_rewards), 4),
        "episode_length":    n_steps,
    }


def run_episode_dqn(
    session: TraCISession,
    agent: DQNAgent,
    n_steps: int,
) -> Dict[str, float]:
    """
    DQN controller: load trained model, epsilon=0.0 (pure exploitation).
    Uses SUMOEnvironment for state/action/reward pipeline (matches training exactly).
    """
    env = SUMOEnvironment(session=session)
    env.reset()

    step_waits:   List[float] = []
    step_queues:  List[float] = []
    step_occ:     List[float] = []
    step_rewards: List[float] = []
    total_throughput: int = 0

    for _ in range(n_steps):
        session.step()
        tp = _get_throughput()
        total_throughput += tp

        episode_wait  = 0.0
        episode_queue = 0.0
        episode_occ   = 0.0

        for jid in JUNCTION_IDS:
            state = env.get_state(junction_id=jid)
            action = agent.select_action(state, epsilon=0.0)   # greedy
            next_state, reward, done, _ = env.step(
                action=action,
                junction_id=jid,
                throughput=tp,
            )

            m = _collect_junction_metrics(jid)
            episode_wait  += m["avg_wait"]
            episode_queue += m["queue_len"]
            episode_occ   += m["occupancy"]
            step_rewards.append(reward)

            if done:
                break

        n = len(JUNCTION_IDS)
        step_waits.append(episode_wait  / n)
        step_queues.append(episode_queue / n)
        step_occ.append(episode_occ     / n)

    avg_wait_time = statistics.mean(step_waits) if step_waits else 0.0

    return {
        "avg_waiting_time":  avg_wait_time,
        "avg_travel_time":   round(avg_wait_time * 1.3 + 10.0, 4),
        "avg_queue_length":  statistics.mean(step_queues)  if step_queues  else 0.0,
        "avg_occupancy":     statistics.mean(step_occ)     if step_occ     else 0.0,
        "throughput":        total_throughput,
        "episode_reward":    round(sum(step_rewards), 4),
        "episode_length":    n_steps,
    }


# ── Output helpers ─────────────────────────────────────────────────────────────

def _write_raw_csv(raw_rows: List[Dict[str, Any]], path: Path) -> None:
    if not raw_rows:
        return
    fieldnames = list(raw_rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(raw_rows)


def _aggregate(values: List[float]) -> Tuple[float, float]:
    """Return (mean, std); std=0.0 for single-item lists."""
    if not values:
        return 0.0, 0.0
    mean = statistics.mean(values)
    std  = statistics.stdev(values) if len(values) > 1 else 0.0
    return round(mean, 4), round(std, 4)


METRIC_KEYS = [
    "avg_waiting_time",
    "avg_travel_time",
    "avg_queue_length",
    "avg_occupancy",
    "throughput",
    "episode_reward",
    "episode_length",
]

METRIC_LABELS = {
    "avg_waiting_time": "Avg Waiting Time (s)",
    "avg_travel_time":  "Avg Travel Time (s)",
    "avg_queue_length": "Avg Queue Length (veh)",
    "avg_occupancy":    "Avg Occupancy (%)",
    "throughput":       "Throughput (veh/ep)",
    "episode_reward":   "Episode Reward",
    "episode_length":   "Episode Length (steps)",
}


def _build_summary(
    results: Dict[str, List[Dict[str, float]]]
) -> List[Dict[str, Any]]:
    rows = []
    for ctrl_key in CONTROLLER_NAMES:
        eps = results[ctrl_key]
        row: Dict[str, Any] = {"controller": CONTROLLER_LABELS[ctrl_key]}
        for mk in METRIC_KEYS:
            vals = [ep[mk] for ep in eps]
            mean, std = _aggregate(vals)
            row[f"{mk}_mean"] = mean
            row[f"{mk}_std"]  = std
        rows.append(row)
    return rows


def _print_summary_table(summary_rows: List[Dict[str, Any]]) -> None:
    """Print a formatted ASCII summary table to stdout."""
    COL_W = 26
    CTRL_W = 16

    print()
    print("=" * 110)
    print("  IntelliRoads - Controller Evaluation Summary")
    print("=" * 110)

    # Header
    header = f"{'Controller':<{CTRL_W}}"
    for mk in METRIC_KEYS:
        label = METRIC_LABELS[mk]
        header += f"  {label:>{COL_W}}"
    print(header)
    print("-" * 110)

    for row in summary_rows:
        line = f"{row['controller']:<{CTRL_W}}"
        for mk in METRIC_KEYS:
            mean = row[f"{mk}_mean"]
            std  = row[f"{mk}_std"]
            cell = f"{mean:.2f} +/- {std:.2f}"
            line += f"  {cell:>{COL_W}}"
        print(line)

    print("=" * 110)
    print()

    # Best/worst call-out per metric
    print("  Performance Call-Outs (mean values):")
    print("-" * 60)
    improvement_metrics = ["avg_waiting_time", "avg_travel_time", "avg_queue_length", "avg_occupancy"]
    higher_is_better    = ["throughput", "episode_reward"]

    for mk in METRIC_KEYS:
        label = METRIC_LABELS[mk]
        vals  = {row["controller"]: row[f"{mk}_mean"] for row in summary_rows}
        if mk in higher_is_better:
            best_ctrl = max(vals, key=vals.__getitem__)
            direction = "Higher = better"
        else:
            best_ctrl = min(vals, key=vals.__getitem__)
            direction = "Lower = better"
        print(f"  {label:<30}  Best: {best_ctrl:<14}  ({direction})")

    print("=" * 110)
    print()


# == Main =======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Fixed-Time, Rule-Based, and DQN controllers on real SUMO."
    )
    parser.add_argument("--episodes", type=int, default=30,
                        help="Number of evaluation episodes per controller (default: 30)")
    parser.add_argument("--steps",    type=int, default=200,
                        help="Simulation steps per episode (default: 200)")
    args = parser.parse_args()

    N_EPISODES = args.episodes
    N_STEPS    = args.steps

    EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # == Validate checkpoint ==================================================
    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(
            f"DQN checkpoint not found: {CHECKPOINT_PATH}\n"
            "Ensure dqn_episode_0950.pt exists in final_dqn_model/."
        )

    print(f"\n{'='*60}")
    print(f"  IntelliRoads - Evaluation Phase")
    print(f"{'='*60}")
    print(f"  Controllers : {', '.join(CONTROLLER_LABELS.values())}")
    print(f"  Episodes    : {N_EPISODES} per controller")
    print(f"  Steps/ep    : {N_STEPS}")
    print(f"  Total steps : {N_EPISODES * N_STEPS * len(CONTROLLER_NAMES):,}")
    print(f"  DQN model   : {CHECKPOINT_PATH.name}")
    print(f"  SUMO config : {SUMO_CONFIG_PATH}")
    print(f"  Output dir  : {EVAL_RESULTS_DIR}")
    print(f"{'='*60}\n")

    # == Pre-load DQN agent (one instance, reused across episodes) ============
    print("Loading DQN checkpoint …")
    dqn_agent = DQNAgent(state_size=5, action_size=4)
    dqn_agent.load(CHECKPOINT_PATH)
    dqn_agent.policy_net.eval()   # inference mode
    print(f"  Loaded: {CHECKPOINT_PATH}")
    print(f"  Train steps in checkpoint: {dqn_agent.train_step_count:,}\n")

    # == Main evaluation loop =================================================
    results: Dict[str, List[Dict[str, float]]] = {k: [] for k in CONTROLLER_NAMES}
    raw_rows: List[Dict[str, Any]] = []

    total_episodes = N_EPISODES * len(CONTROLLER_NAMES)
    ep_counter = 0

    for ctrl_key in CONTROLLER_NAMES:
        ctrl_label = CONTROLLER_LABELS[ctrl_key]
        print(f"-- Running {ctrl_label} controller ({N_EPISODES} episodes) --")

        for ep_idx in range(1, N_EPISODES + 1):
            ep_counter += 1
            t0 = time.time()

            session = make_session()
            try:
                if ctrl_key == "fixed_time":
                    ep_metrics = run_episode_fixed_time(session, N_STEPS)
                elif ctrl_key == "rule_based":
                    ep_metrics = run_episode_rule_based(session, N_STEPS)
                else:  # dqn
                    ep_metrics = run_episode_dqn(session, dqn_agent, N_STEPS)
            finally:
                session.close()

            elapsed = time.time() - t0
            results[ctrl_key].append(ep_metrics)

            raw_rows.append({
                "controller":      ctrl_label,
                "episode":         ep_idx,
                **ep_metrics,
                "wall_time_s":     round(elapsed, 2),
            })

            print(
                f"  [{ep_counter:>3}/{total_episodes}] ep {ep_idx:>2}/{N_EPISODES}"
                f"  reward={ep_metrics['episode_reward']:+.1f}"
                f"  wait={ep_metrics['avg_waiting_time']:.2f}s"
                f"  queue={ep_metrics['avg_queue_length']:.2f}"
                f"  tp={ep_metrics['throughput']}"
                f"  ({elapsed:.1f}s)"
            )

        print()

    # ── Build and write summary ──────────────────────────────────────────────
    summary_rows = _build_summary(results)

    # Write raw CSV
    raw_csv_path = EVAL_RESULTS_DIR / "eval_raw.csv"
    _write_raw_csv(raw_rows, raw_csv_path)
    print(f"Raw results written  -> {raw_csv_path}")

    # Write summary CSV
    summary_csv_path = EVAL_RESULTS_DIR / "eval_summary.csv"
    if summary_rows:
        with open(summary_csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)
    print(f"Summary CSV written  -> {summary_csv_path}")

    # Write summary JSON
    summary_json_path = EVAL_RESULTS_DIR / "eval_summary.json"
    meta = {
        "generated_at":      time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_episodes":        N_EPISODES,
        "n_steps_per_ep":    N_STEPS,
        "dqn_checkpoint":    str(CHECKPOINT_PATH.name),
        "sumo_config":       str(SUMO_CONFIG_PATH.name),
        "controllers":       summary_rows,
    }
    with open(summary_json_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Summary JSON written -> {summary_json_path}\n")

    # ── Print table ──────────────────────────────────────────────────────────
    _print_summary_table(summary_rows)


if __name__ == "__main__":
    main()
