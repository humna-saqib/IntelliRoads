"""
IntelliRoads – FastAPI main application entry point.

Initialises services, starts the background simulation loop, and exposes
the REST and WebSocket APIs.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import time
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, Depends, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.database import Database
from app.core.state_store import InMemoryStateStore
from app.services.traci_session import TraCISession
from app.services.vehicle_data_service import VehicleDataService
from app.services.density_calculator import DensityCalculator
from app.services.congestion_detector import CongestionDetector
from app.services.signal_controller import SignalController
from app.services.kpi_service import KPIService
from app.services.db_logger import DBLogger
from app.services.emergency_detector import EmergencyVehicleDetector
from app.services.priority_controller import EmergencyPriorityController
from app.services.occupancy_calculator import OccupancyCalculator
from app.services.performance_metrics_service import PerformanceMetricsService
from app.services.rl_environment import RLEnvironment
from app.models.emergency import EmergencyResponse
from app.models.signal import SignalResponse
from app.websocket.manager import WebSocketManager, websocket_endpoint
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Setup state store, WebSocket manager, and simulation loop task
# ---------------------------------------------------------------------------
state_store = InMemoryStateStore()
ws_manager = WebSocketManager()
sim_loop_task: asyncio.Task | None = None


async def simulate_loop(
    session: TraCISession,
    data_service: VehicleDataService,
    density_calculator: DensityCalculator,
    congestion_detector: CongestionDetector,
    signal_controller: SignalController,
    kpi_service: KPIService,
    db_logger: DBLogger,
    emergency_detector: EmergencyVehicleDetector,
    priority_controller: EmergencyPriorityController,
    occupancy_calculator: OccupancyCalculator,
    performance_metrics_service: PerformanceMetricsService,
    rl_environment: RLEnvironment,
    store: InMemoryStateStore,
    manager: WebSocketManager,
) -> None:
    """
    Background loop that advances the simulation, processes telemetry,
    updates the state store, and broadcasts to WebSocket clients.
    """
    logger.info("Simulation background loop started.")
    try:
        while True:
            start_time = time.time()

            # 1. Step simulation
            sim_time = session.step()

            # 2. Collect raw vehicle telemetry
            vehicles = data_service.collect_all()

            # 2.5. Detect active emergency vehicles (ambulance/police/firetruck)
            active_emergency, emergency_events = emergency_detector.detect(vehicles, sim_time)
            emergency_response = EmergencyResponse(
                active_vehicles=active_emergency,
                recent_events=emergency_events,
                timestamp=time.time(),
            )

            # 3. Calculate density per lane
            density_response = density_calculator.calculate_all_densities(vehicles)

            # 4. Detect congestion events
            congestion_response = congestion_detector.detect(density_response)

            # 4.5. Compute lane occupancy (independent of signal control –
            #      purely observational for analytics/future RL state)
            occupancy_response = occupancy_calculator.calculate_all(vehicles)

            # 5. Adapt traffic signals using rule-based timing – unchanged,
            #    always pure density-based, never touched by priority control.
            #    Timed for Response Optimization Metrics (controller_response_time).
            controller_timer_start = time.perf_counter()
            signal_controller.update_all_signals(density_response)
            normal_signals = signal_controller.get_current_signals()
            normal_signals_response = SignalResponse(
                signals=normal_signals, timestamp=time.time()
            )

            # 5.5. Resolve final signals: substitute priority GREEN for any
            #      junction with an active emergency vehicle, otherwise pass
            #      the normal decision through untouched. Separate layer —
            #      SignalController's own state is never mutated.
            final_signals, priority_events = priority_controller.resolve_signals(
                normal_signals=normal_signals,
                active_emergency_vehicles=active_emergency,
                density_response=density_response,
                sim_time=sim_time,
            )
            controller_response_time_ms = (time.perf_counter() - controller_timer_start) * 1000.0
            signals_response = SignalResponse(signals=final_signals, timestamp=time.time())

            # 6. Compute overall dashboard KPIs
            kpis = kpi_service.compute_kpis(
                vehicles,
                density_response,
                congestion_response,
                sim_time,
                mock_mode=session.mock_mode,
                fetch_latency_ms=data_service.last_fetch_latency_ms,
            )

            # 6.5. Response Optimization Metrics – purely observational, reads
            #      the same tick's data but never influences signal control.
            tick_processing_time_ms = (time.time() - start_time) * 1000.0
            performance_snapshot = performance_metrics_service.record_tick(
                sim_time=sim_time,
                vehicles=vehicles,
                density_response=density_response,
                occupancy_response=occupancy_response,
                congestion_response=congestion_response,
                normal_signals=normal_signals,
                priority_events=priority_events,
                controller_response_time_ms=controller_response_time_ms,
                tick_processing_time_ms=tick_processing_time_ms,
            )

            # 6.6. RL Environment Preparation – observes the rule-based
            #      controller's behaviour and produces training-data
            #      transitions only. Does not control signals.
            rl_experiences = rl_environment.step(
                sim_time=sim_time,
                vehicles=vehicles,
                density_response=density_response,
                occupancy_response=occupancy_response,
                congestion_response=congestion_response,
                normal_signals=normal_signals,
                throughput_tick=performance_snapshot.throughput_tick,
            )

            # 7. Update central thread-safe state store (final/merged signals –
            #    what the API and dashboard actually see)
            await store.update_all(
                vehicles=vehicles,
                density=density_response,
                congestion=congestion_response,
                signals=signals_response,
                kpis=kpis,
                sim_time=sim_time,
                emergency=emergency_response,
                occupancy=occupancy_response,
                performance=performance_snapshot,
            )

            # 7.5. Persist telemetry to SQLite for historical/RL data collection.
            #      signal_decisions logs the pure normal decision, so normal
            #      vs. emergency-override history stays distinguishable.
            try:
                await db_logger.log_tick(
                    sim_time=sim_time,
                    vehicles=vehicles,
                    density_response=density_response,
                    congestion_response=congestion_response,
                    signals_response=normal_signals_response,
                    occupancy_response=occupancy_response,
                )
                await db_logger.log_emergency_events(emergency_events)
                await db_logger.log_priority_events(priority_events)
                await db_logger.log_performance_metrics(performance_snapshot)
                await db_logger.log_rl_experiences(rl_experiences)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"DB logging failed for this tick: {exc}")

            # 8. Broadcast state snapshot to all connected WebSocket clients
            snapshot = await store.get_full_snapshot()
            await manager.broadcast(snapshot)

            # Control tick frequency (~1.0 second step length)
            elapsed = time.time() - start_time
            sleep_time = max(1.0 - elapsed, 0.05)
            await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info("Simulation loop task was cancelled.")
    except Exception as exc:
        logger.exception(f"Fatal error in simulation loop: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan events: handles SUMO startup, background task, and graceful shutdown.
    """
    global sim_loop_task

    # Set up paths for SUMO configuration
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

    # Force SUMO to use GUI (sumo-gui) as requested
    os.environ["SUMO_USE_GUI"] = "true"

    # Initialise TraCI session and dependencies
    session = TraCISession(config_path=config_path, step_length=1.0)
    
    try:
        session.start()
    except Exception as exc:
        logger.warning(
            f"Failed to start SUMO session: {exc}. "
            f"Will fallback completely to MOCK data."
        )
        # Force mock mode on connection error
        session._mock_mode = True
        session._connected = True

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

    # Connect the SQLite telemetry database (Sprint 2 logging layer)
    database = Database()
    await database.connect()
    db_logger = DBLogger(database)

    # Share state store, ws manager, and db logger with FastAPI application state
    app.state.store = state_store
    app.state.ws_manager = ws_manager
    app.state.db_logger = db_logger

    # Start simulation loop in the background
    sim_loop_task = asyncio.create_task(
        simulate_loop(
            session=session,
            data_service=data_service,
            density_calculator=density_calculator,
            congestion_detector=congestion_detector,
            signal_controller=signal_controller,
            kpi_service=kpi_service,
            db_logger=db_logger,
            emergency_detector=emergency_detector,
            priority_controller=priority_controller,
            occupancy_calculator=occupancy_calculator,
            performance_metrics_service=performance_metrics_service,
            rl_environment=rl_environment,
            store=state_store,
            manager=ws_manager,
        )
    )

    yield

    # Clean up on shutdown
    logger.info("Shutting down application...")
    if sim_loop_task:
        sim_loop_task.cancel()
        try:
            await sim_loop_task
        except asyncio.CancelledError:
            pass

    session.close()
    await database.close()
    logger.info("Application teardown complete.")


# Create FastAPI application instance
app = FastAPI(
    title="IntelliRoads Adaptive Traffic Control System",
    description="Sprint 1 - Core Traffic Optimization Pipeline API",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend dashboard communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(api_router)


# Expose root endpoint
@app.get("/")
def read_root():
    return {
        "message": "IntelliRoads Adaptive Traffic Control System API is running.",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# Health check endpoint
@app.get("/health")
def read_health():
    return {"status": "ok", "timestamp": time.time()}


# WebSocket live update stream endpoint
@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket_endpoint(websocket, ws_manager, state_store)


if __name__ == "__main__":
    import uvicorn
    # Make sure logs directory exists
    os.makedirs("logs", exist_ok=True)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
