# IntelliRoads

IntelliRoads is an AI-assisted traffic management system built on top of the SUMO simulator. It streams live vehicle telemetry into a FastAPI backend and a React dashboard so you can monitor traffic density, congestion, signal timing, and intersection status in real time.

## Overview

The project combines a Python backend with a Vite + React frontend. The backend collects traffic data from SUMO via TraCI, computes densities and KPIs, detects congestion, and broadcasts live snapshots over WebSocket. The frontend visualizes that data in a dashboard, an interactive map, and analytics views.

If SUMO cannot be started locally, the backend falls back to mock mode so the API can still boot for development.

## Features

- Real-time vehicle telemetry collection
- Vehicle classification by type
- Lane-level density calculation
- Congestion detection and event tracking
- Rule-based traffic signal timing
- KPI computation for the dashboard
- Live WebSocket updates for the UI
- Interactive map with live color-coded intersection status dots
- Analytics and dashboard views for traffic monitoring

## Tech Stack

- Backend: FastAPI, Uvicorn, TraCI, Pydantic, Loguru
- Frontend: React, TypeScript, Vite, Tailwind CSS, Recharts, React Router
- Simulation: SUMO

## Project Structure

```text
IntelliRoads/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── services/
│   │   ├── utils/
│   │   └── websocket/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── context/
│   │   ├── pages/
│   │   ├── services/
│   │   └── types/
│   └── package.json
└── sumo/
	├── config/
	├── network/
	└── routes/
```

## Prerequisites

- Python 3.9+
- Node.js 18+
- npm
- SUMO 1.13 or compatible

## Local Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd IntelliRoads
```

### 2. Install and run the backend

```bash
cd backend
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend URLs:

- API root: `http://localhost:8000/`
- OpenAPI docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`
- WebSocket stream: `ws://localhost:8000/ws/live`

### 3. Install and run the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

- Dashboard: `http://localhost:5173`

If you see `Permission denied` for `vite` or `tsc`, run:

```bash
chmod +x node_modules/.bin/*
```

## Available Pages

- `/` - Dashboard
- `/map` - Interactive traffic map
- `/analytics` - Traffic analytics view

## API Endpoints

All API routes are prefixed with `/api`.

- `GET /api/vehicles`
- `GET /api/vehicles/{vehicle_id}`
- `GET /api/vehicles/lane/{lane_id}`
- `GET /api/classification`
- `GET /api/density`
- `GET /api/density/{lane_id}`
- `GET /api/congestion`
- `GET /api/congestion/active`
- `GET /api/signals`
- `GET /api/signals/{junction_id}`
- `GET /api/kpis`
- `GET /api/intersections`

## How the Live Data Flow Works

1. SUMO advances the simulation.
2. The backend collects vehicle data through TraCI.
3. Density, congestion, signal timing, and KPI services process the data.
4. The current state is stored in memory and broadcast over WebSocket.
5. The React dashboard consumes the live snapshots and updates the UI.

## Troubleshooting

- If the backend cannot connect to SUMO, it will switch to mock mode.
- Make sure the SUMO config exists at `sumo/config/intelliroads.sumocfg`.
- If the frontend does not start, reinstall dependencies with `npm install`.
- If you need to check what changed, run `git status` and `git diff`.

## Development Notes

- The backend enables CORS for frontend communication.
- The WebSocket stream is push-based and sends the latest snapshot immediately on connection.
- The project is intended for local development and simulation-driven traffic analysis.

## License

See [LICENSE](LICENSE) for licensing details.
# intelliroads
