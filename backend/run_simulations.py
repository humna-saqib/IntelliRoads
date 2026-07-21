"""
IntelliRoads – Multiple Simulation Runs Orchestrator (Sprint 2 - Feature 4).

Executes multiple SUMO simulation runs automatically, collects metrics, and saves results
to SQLite database and JSON summary files.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# Add backend directory to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.agent.dqn_agent import DQNAgent
from app.controllers.dqn_controller import DQNController, ControllerMode
from app.core.database import DB_PATH
from app.environment.sumo_environment import SUMOEnvironment
from app.models.emergency import EmergencyResponse
from app.models.signal import SignalResponse
from app.services.congestion_detector import CongestionDetector
from app.services.density_calculator import DensityCalculator
from app.services.emergency_detector import EmergencyVehicleDetector
from app.services.kpi_service import KPIService
from app.services.occupancy_calculator import OccupancyCalculator
from app.services.performance_metrics_service import PerformanceMetricsService
from app.services.priority_controller import EmergencyPriorityController
from app.services.rl_environment import RLEnvironment
from app.services.signal_controller import SignalController
from app.services.traci_session import TraCISession
from app.services.vehicle_data_service import VehicleDataService

SIMULATIONS_DIR = Path(__file__).resolve().parent / "data" / "simulations"


def _ensure_simulation_runs_table(db_path: Path) -> None:
    """Ensure database table exists for simulation run history."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sumo_simulation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                duration REAL NOT NULL,
                avg_waiting_time REAL NOT NULL,
                avg_queue_length REAL NOT NULL,
                throughput INTEGER NOT NULL,
                avg_reward REAL NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sumo_simulation_runs_run_id ON sumo_simulation_runs(run_id)"
        )
        conn.commit()
    finally:
        conn.close()


def _persist_run_to_db(db_path: Path, run_info: Dict[str, Any]) -> None:
    """Save simulation run summary metadata to SQLite."""
    _ensure_simulation_runs_table(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        # Delete if duplicated ID
        conn.execute("DELETE FROM sumo_simulation_runs WHERE run_id = ?", (run_info["run_id"],))
        
        conn.execute(
            """
            INSERT INTO sumo_simulation_runs 
            (run_id, start_time, end_time, duration, avg_waiting_time, avg_queue_length, throughput, avg_reward, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_info["run_id"],
                run_info["start_time"],
                run_info["end_time"],
                run_info["duration"],
                run_info["avg_waiting_time"],
                run_info["avg_queue_length"],
                run_info["throughput"],
                run_info["avg_reward"],
                run_info["timestamp"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _update_master_summary(summary_file: Path, new_runs: List[Dict[str, Any]]) -> None:
    """Read existing summary JSON, merge simulation runs, and write back."""
    existing_runs: List[Dict[str, Any]] = []
    if summary_file.exists():
        try:
            with open(summary_file, "r") as f:
                existing_runs = json.load(f)
        except Exception:
            pass

    run_map = {run["run_id"]: run for run in existing_runs}
    for run in new_runs:
        run_map[run["run_id"]] = run

    with open(summary_file, "w") as f:
        json.dump(list(run_map.values()), f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="SUMO Automated Multiple Simulation Runner.")
    parser.add_argument("--runs", type=int, default=3, help="Number of simulation runs to execute")
    parser.add_argument("--steps", type=int, default=500, help="Simulation duration (steps/ticks) per run")
    parser.add_argument(
        "--mode",
        type=str,
        default="RULE_BASED",
        choices=["RULE_BASED", "DQN"],
        help="Controller mode to evaluate (RULE_BASED or DQN)",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default="data/models/dqn_agent.pt",
        help="DQN agent checkpoint path to load (for DQN mode evaluation)",
    )
    args = parser.parse_args()

    SIMULATIONS_DIR.mkdir(parents=True, exist_ok=True)
    summary_json_path = SIMULATIONS_DIR / "summary.json"

    # Find SUMO configuration file
    cwd = Path.cwd()
    config_candidates = [
        cwd / "sumo" / "config" / "intelliroads.sumocfg",
        cwd / "backend" / "sumo" / "config" / "intelliroads.sumocfg",
        Path(__file__).parent.parent / "sumo" / "config" / "intelliroads.sumocfg",
    ]
    config_path = config_candidates[0]
    for candidate in config_candidates:
        if candidate.exists():
            config_path = candidate
            break

    logger.info(f"Using SUMO Configuration: {config_path}")
    logger.info(f"Executing {args.runs} runs | steps={args.steps} | mode={args.mode}")
    print("=" * 80)

    completed_runs: List[Dict[str, Any]] = []

    for run_idx in range(1, args.runs + 1):
        run_id = f"sim_run_{run_idx}_{uuid.uuid4().hex[:6]}"
        run_dir = SIMULATIONS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        log_file = run_dir / "simulation.log"

        # Capture logs for this simulation run to its own log file
        handler_id = logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO",
            encoding="utf-8",
        )

        logger.info(f"[{run_idx}/{args.runs}] STARTING SIMULATION RUN: {run_id}")
        
        start_wall_time = time.time()
        
        # 1. Initialize TraCI/SUMO session
        session = TraCISession(config_path=config_path, step_length=1.0)
        try:
            session.start()
        except Exception as exc:
            logger.warning(f"Failed to launch live SUMO session: {exc}. Falling back to MOCK mode.")
            session._mock_mode = True
            session._connected = True

        # 2. Build Pipeline instances
        data_service = VehicleDataService(session)
        density_calculator = DensityCalculator()
        congestion_detector = CongestionDetector()
        signal_controller = SignalController(session)
        kpi_service = KPIService()
        emergency_detector = EmergencyVehicleDetector()
        priority_controller = EmergencyPriorityController()
        occupancy_calculator = OccupancyCalculator(session)
        performance_metrics_service = PerformanceMetricsService(session)
        rl_environment = RLEnvironment()

        # 3. DQN Setup
        sumo_env = SUMOEnvironment(session)
        dqn_agent = DQNAgent()
        if args.mode == "DQN":
            model_file = Path(args.model_path)
            if model_file.exists():
                try:
                    dqn_agent.load(model_file)
                    logger.info(f"Loaded trained DQN checkpoint weights from {model_file}")
                except Exception as exc:
                    logger.error(f"Failed to load checkpoint weights: {exc}. Starting with raw DQN agent.")
            else:
                logger.warning(f"Model checkpoint not found at {model_file}. Starting with raw DQN agent.")

        dqn_controller = DQNController(
            session=session,
            environment=sumo_env,
            agent=dqn_agent,
            rule_based_controller=signal_controller,
            mode=ControllerMode(args.mode),
        )

        step_records: List[Dict[str, Any]] = []
        
        # Performance aggregate buffers
        waiting_times: List[float] = []
        queue_lengths: List[float] = []
        rewards: List[float] = []
        
        logger.info("Starting simulation ticks loop.")
        
        # 4. Simulation ticks loop
        for step in range(1, args.steps + 1):
            if not session.is_connected():
                logger.warning("TraCI session disconnected prematurely.")
                break
                
            tick_start = time.perf_counter()
            
            # Step SUMO
            sim_time = session.step()
            
            # Collect Telemetry
            vehicles = data_service.collect_all()
            
            # Calculate Densities
            density_response = density_calculator.calculate_all_densities(vehicles)
            
            # Detect Congestion
            congestion_response = congestion_detector.detect(density_response)
            
            # Compute Occupancy
            occupancy_response = occupancy_calculator.calculate_all(vehicles)
            
            # Detect Emergencies
            active_emergency, emergency_events = emergency_detector.detect(vehicles, sim_time)
            
            # DQN / Rule-based Control Step
            ctrl_start = time.perf_counter()
            normal_signals = dqn_controller.control_step(
                density_response=density_response,
                vehicles=vehicles,
                occupancy_response=occupancy_response,
                throughput=1,
            )
            ctrl_time_ms = (time.perf_counter() - ctrl_start) * 1000.0
            
            # Priority override resolver
            final_signals, priority_events = priority_controller.resolve_signals(
                normal_signals=normal_signals,
                active_emergency_vehicles=active_emergency,
                density_response=density_response,
                sim_time=sim_time,
            )
            
            tick_time_ms = (time.perf_counter() - tick_start) * 1000.0
            
            # Record Performance Snapshots
            perf_snapshot = performance_metrics_service.record_tick(
                sim_time=sim_time,
                vehicles=vehicles,
                density_response=density_response,
                occupancy_response=occupancy_response,
                congestion_response=congestion_response,
                normal_signals=normal_signals,
                priority_events=priority_events,
                controller_response_time_ms=ctrl_time_ms,
                tick_processing_time_ms=tick_time_ms,
            )
            
            # Produce RL experiences
            experiences = rl_environment.step(
                sim_time=sim_time,
                vehicles=vehicles,
                density_response=density_response,
                occupancy_response=occupancy_response,
                congestion_response=congestion_response,
                normal_signals=normal_signals,
                throughput_tick=perf_snapshot.throughput_tick,
            )
            
            step_reward = sum(e.reward for e in experiences) if experiences else 0.0
            
            # Store values in aggregates
            waiting_times.append(perf_snapshot.avg_waiting_time)
            queue_lengths.append(perf_snapshot.avg_queue_length)
            rewards.append(step_reward)
            
            step_records.append({
                "step": step,
                "sim_time": sim_time,
                "avg_waiting_time": perf_snapshot.avg_waiting_time,
                "avg_queue_length": perf_snapshot.avg_queue_length,
                "throughput_tick": perf_snapshot.throughput_tick,
                "throughput_total": perf_snapshot.throughput_total,
                "reward": step_reward,
            })

        # Tear down session
        session.close()
        end_wall_time = time.time()
        
        # Calculate final aggregated run metrics
        avg_wait = sum(waiting_times) / len(waiting_times) if waiting_times else 0.0
        avg_queue = sum(queue_lengths) / len(queue_lengths) if queue_lengths else 0.0
        avg_rew = sum(rewards) / len(rewards) if rewards else 0.0
        throughput = step_records[-1]["throughput_total"] if step_records else 0
        duration = step_records[-1]["sim_time"] - step_records[0]["sim_time"] if len(step_records) > 1 else 0.0

        run_result = {
            "run_id": run_id,
            "start_time": start_wall_time,
            "end_time": end_wall_time,
            "duration": round(duration, 2),
            "avg_waiting_time": round(avg_wait, 4),
            "avg_queue_length": round(avg_queue, 4),
            "throughput": throughput,
            "avg_reward": round(avg_rew, 4),
            "timestamp": start_wall_time,
        }

        # 5. Persist summaries
        _persist_run_to_db(DB_PATH, run_result)
        completed_runs.append(run_result)

        # Write detailed step stats to JSON
        stats_json_path = run_dir / "stats.json"
        with open(stats_json_path, "w") as f:
            json.dump(step_records, f, indent=2)

        logger.info(f"Finished Run: {run_id} in {end_wall_time - start_wall_time:.2f}s")
        logger.info(f"Metrics: Avg Wait={avg_wait:.2f}s | Avg Queue={avg_queue:.2f} | Throughput={throughput} | Avg Reward={avg_rew:.4f}")
        
        # Clean up logger file handler
        logger.remove(handler_id)

    # Save to master summary json file
    if completed_runs:
        _update_master_summary(summary_json_path, completed_runs)

        # Display report comparison
        print("\n" + "=" * 95)
        print("SIMULATION RUNS SUMMARY COMPARISON")
        print("=" * 95)
        print(f"{'Run ID':<22} | {'Duration (s)':<12} | {'Avg Wait (s)':<12} | {'Avg Queue':<10} | {'Throughput':<10} | {'Avg Reward':<10}")
        print("-" * 95)
        for r in completed_runs:
            print(
                f"{r['run_id']:<22} | {r['duration']:<12.1f} | {r['avg_waiting_time']:<12.2f} | "
                f"{r['avg_queue_length']:<10.2f} | {r['throughput']:<10} | {r['avg_reward']:<10.4f}"
            )
        print("=" * 95)
        logger.info(f"Master summary file saved at: {summary_json_path}")
    else:
        logger.warning("No simulation runs were completed successfully.")


if __name__ == "__main__":
    main()
