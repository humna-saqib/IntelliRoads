# System Architecture Diagram

> **Files read to produce this diagram:**
> - `backend/app/main.py` — lifespan setup, service wiring, simulation loop, WebSocket endpoint
> - `backend/app/services/traci_session.py` — TraCI / SUMO connection and mock-mode fallback
> - `backend/app/services/signal_controller.py` — rule-based timing (density→duration)
> - `backend/app/controllers/dqn_controller.py` — DQN / RULE_BASED mode switching, `ControllerMode` enum
> - `backend/app/controllers/fyp_dqn_controller.py` — final obs-v2 Double DQN model (loaded if available)
> - `backend/app/environment/signal_safety.py` — legal-action mask and safety constraints
> - `backend/app/services/priority_controller.py` — emergency vehicle override layer
> - `backend/app/core/database.py` — SQLite schema and `Database` class
> - `backend/app/websocket/manager.py` — `WebSocketManager.broadcast()`
> - `backend/app/api/routes/__init__.py` — all REST routers under `/api`
> - `backend/app/core/state_store.py` — `InMemoryStateStore`
> - `frontend/src/services/api.ts` — REST client (`BASE_URL = '/api'`)
> - `frontend/src/services/websocket.ts` — `TrafficWebSocket` with reconnect
> - `frontend/src/context/TrafficContext.tsx` — `TrafficProvider`, merges WS + REST data
> - `frontend/src/App.tsx` — routes and auth gate

```mermaid
flowchart TD
    subgraph SUMO["SUMO Traffic Simulator"]
        SIM["sumo / sumo-gui\n(intelliroads.sumocfg)"]
        TRACI_PORT["TraCI TCP :8813"]
    end

    subgraph BACKEND["FastAPI Backend  :8000"]
        direction TB

        TS["TraCISession\nservices/traci_session.py\n(LIVE or MOCK mode)"]

        subgraph SIMLOOP["Simulation Loop  main.py"]
            VDS["VehicleDataService\n collect_all()"]
            DC["DensityCalculator\n calculate_all_densities()"]
            CongD["CongestionDetector\n detect()"]
            OC["OccupancyCalculator\n calculate_all()"]

            subgraph CTRL["Signal Control Layer"]
                RB["SignalController (Rule-Based)\n LOW→20s MEDIUM→35s HIGH→55s"]
                SAFETY["SignalSafety\n legal_action_mask()"]
                DQN["DQNController\n RULE_BASED | DQN"]
                FYP["FYP obs-v2 Double DQN\n fyp_dqn_controller.py\n(loaded if model file present)"]
                RB --> SAFETY
                FYP --> SAFETY
                SAFETY --> DQN
            end

            EMERG["EmergencyVehicleDetector\n detect()"]
            PRIO["EmergencyPriorityController\n resolve_signals()"]
            KPI["KPIService\n compute_kpis()"]
            PERF["PerformanceMetricsService\n record_tick()"]
            RLENV["RLEnvironment\n step() — observational only"]
            STORE["InMemoryStateStore\n update_all() / get_full_snapshot()"]

            VDS --> DC --> CongD
            VDS --> OC
            VDS --> EMERG
            DC --> CTRL
            OC --> CTRL
            CTRL --> PRIO
            EMERG --> PRIO
            PRIO --> KPI
            PRIO --> PERF
            PRIO --> RLENV
            PRIO --> STORE
            KPI --> STORE
        end

        DBL["DBLogger\n services/db_logger.py"]
        DB[("SQLite\n intelliroads.db\n core/database.py")]
        WSM["WebSocketManager\n websocket/manager.py"]

        subgraph API["REST API  /api  (FastAPI routers)"]
            AUTH["/api/auth/login"]
            VAPI["/api/vehicles"]
            DAPI["/api/density"]
            CAPI["/api/congestion"]
            SAPI["/api/signals"]
            KAPI["/api/kpis"]
            IAPI["/api/intersections"]
            EAPI["/api/emergency"]
            PAPI["/api/performance"]
            RLAPI["/api/rl/mode  POST"]
            SETAPI["/api/settings"]
        end

        STORE --> DBL
        DBL --> DB
        STORE --> WSM
        STORE --> API
    end

    subgraph FRONTEND["React Dashboard  :5173 (Vite)"]
        direction TB
        WSCLIENT["TrafficWebSocket\n services/websocket.ts\n ws://…/ws/live?token=…"]
        RESTCLIENT["api.ts REST client\n BASE_URL='/api'\n Bearer token from localStorage"]
        CTX["TrafficContext / TrafficProvider\n context/TrafficContext.tsx\n merges WS snapshot + REST fallback"]
        PAGES["Pages\n / Home  /details Dashboard\n /map  /analytics  /alerts\n /reports  /settings  /login"]
        WIDGETS["Widgets\n JunctionCard  KPICards  SignalStatusGrid\n IntersectionMap  DensityChart\n CongestionAlerts  TimingModeSwitch …"]

        WSCLIENT --> CTX
        RESTCLIENT --> CTX
        CTX --> PAGES
        PAGES --> WIDGETS
    end

    SIM <-->|TraCI protocol| TRACI_PORT
    TRACI_PORT <-->|TraCISession| TS
    TS --> SIMLOOP
    WSM -->|JSON snapshot ~1 s| WSCLIENT
    FRONTEND -->|GET /api/…| API
    FRONTEND -->|POST /api/rl/mode| RLAPI
```

## Component Responsibilities

| Component | File(s) | Role |
|---|---|---|
| SUMO | `sumo/config/intelliroads.sumocfg` | Microscopic traffic simulation; 4-junction network |
| TraCISession | `services/traci_session.py` | Opens TraCI TCP connection; falls back to synthetic mock data if SUMO absent |
| Simulation loop | `main.py: simulate_loop()` | Orchestrates one tick per second; calls all services in order |
| SignalController | `services/signal_controller.py` | Rule-based timing: density level → green duration |
| SignalSafety | `environment/signal_safety.py` | Legal-action mask (min/max green, yellow never shortened) |
| DQNController | `controllers/dqn_controller.py` | Wraps rule-based and DQN; selectable via `POST /api/rl/mode` |
| FYP obs-v2 controller | `controllers/fyp_dqn_controller.py` | Final trained Double DQN with safety layer; loaded from `.pt` checkpoint |
| EmergencyPriorityController | `services/priority_controller.py` | Overrides signal to 90 s GREEN at any junction with an active emergency vehicle |
| InMemoryStateStore | `core/state_store.py` | Thread-safe in-memory cache; source of truth for REST and WS |
| DBLogger | `services/db_logger.py` | Persists telemetry to SQLite after every tick |
| SQLite | `core/database.py` | 14-table schema; WAL mode |
| WebSocketManager | `websocket/manager.py` | Broadcasts full snapshot JSON to all connected clients every ~1 s |
| TrafficContext | `frontend/src/context/TrafficContext.tsx` | Maintains WS connection; falls back to polling REST every 5 s when WS drops |
