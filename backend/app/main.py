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
from app.core.state_store import InMemoryStateStore
from app.services.traci_session import TraCISession
from app.services.vehicle_data_service import VehicleDataService
from app.services.density_calculator import DensityCalculator
from app.services.congestion_detector import CongestionDetector
from app.services.signal_controller import SignalController
from app.services.kpi_service import KPIService
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

            # 3. Calculate density per lane
            density_response = density_calculator.calculate_all_densities(vehicles)

            # 4. Detect congestion events
            congestion_response = congestion_detector.detect(density_response)

            # 5. Adapt traffic signals using rule-based timing
            signal_controller.update_all_signals(density_response)
            current_signals = signal_controller.get_current_signals()
            signals_response = SignalResponse(
                signals=current_signals, timestamp=time.time()
            )

            # 6. Compute overall dashboard KPIs
            kpis = kpi_service.compute_kpis(
                vehicles, density_response, congestion_response, sim_time
            )

            # 7. Update central thread-safe state store
            await store.update_all(
                vehicles=vehicles,
                density=density_response,
                congestion=congestion_response,
                signals=signals_response,
                kpis=kpis,
                sim_time=sim_time,
            )

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

    logger.info(f"Using SUMO config path candidate: {config_path}")

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

    # Share state store and ws manager with FastAPI application state
    app.state.store = state_store
    app.state.ws_manager = ws_manager

    # Start simulation loop in the background
    sim_loop_task = asyncio.create_task(
        simulate_loop(
            session=session,
            data_service=data_service,
            density_calculator=density_calculator,
            congestion_detector=congestion_detector,
            signal_controller=signal_controller,
            kpi_service=kpi_service,
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
