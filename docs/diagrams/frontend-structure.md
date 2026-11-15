# Frontend Structure

> **Files read to produce this diagram:**
> - `frontend/src/App.tsx` — routes, auth gate, layout wrapper
> - `frontend/src/context/TrafficContext.tsx` — context fields, WebSocket + REST polling
> - `frontend/src/services/api.ts` — `BASE_URL`, `apiFetch`, `apiPost` helpers
> - `frontend/src/services/websocket.ts` — `TrafficWebSocket` class with exponential back-off
> - `frontend/src/pages/` — all page components (HomePage, DashboardPage, MapPage,
>   AnalyticsPage, AlertHistoryPage, ReportsPage, SettingsPage, LoginPage)
> - `frontend/src/components/` — all widget and UI-atom components

---

## Page and Component Map

```mermaid
flowchart TD
    subgraph Entry["App Entry (App.tsx)"]
        AUTH{Token in\nlocalStorage?}
    end

    AUTH -->|No| LOGIN["LoginPage\n/login"]
    AUTH -->|Yes| SHELL["App Shell\n(Header + Sidebar + Outlet)"]

    subgraph NAV["Sidebar Navigation"]
        R1["/  →  HomePage"]
        R2["/details  →  DashboardPage"]
        R3["/map  →  MapPage"]
        R4["/analytics  →  AnalyticsPage"]
        R5["/alerts  →  AlertHistoryPage"]
        R6["/reports  →  ReportsPage"]
        R7["/settings  →  SettingsPage"]
    end

    SHELL --> NAV

    subgraph CTX["TrafficContext (TrafficProvider)"]
        WS["websocket.ts\nTrafficWebSocket\n(exponential back-off)"]
        API["api.ts\napiFetch / apiPost\nBASE_URL = /api"]
        WS --> CTXDATA["Live state:\njunctions, kpis,\nalerts, mode,\nsimRunning, …"]
        API --> CTXDATA
    end

    NAV --> CTX

    subgraph HOME["HomePage (/)"]
        H1["KPICards"]
        H2["LiveStatusBadge"]
        H3["ControlModePanel"]
        H4["CongestionAlerts"]
        H5["JunctionCard × N"]
        H6["TimingModeSwitch"]
        H7["EmergencyPriorityBanner"]
        H8["FirstVisitTour"]
    end

    subgraph DASH["DashboardPage (/details)"]
        D1["SignalStatusGrid"]
        D2["DensityChart"]
        D3["OccupancyChart"]
        D4["VehicleTable"]
        D5["VehicleClassChart"]
        D6["SpeedDistribution"]
    end

    subgraph MAP["MapPage (/map)"]
        M1["IntersectionMap\n(Leaflet)"]
        M2["Junction list\nwith status badges"]
    end

    subgraph ANA["AnalyticsPage (/analytics)"]
        A1["DensityChart (historical)"]
        A2["OccupancyChart (historical)"]
        A3["VehicleClassChart"]
        A4["SpeedDistribution"]
        A5["KPICards (historical)"]
    end

    subgraph ALT["AlertHistoryPage (/alerts)"]
        AL1["CongestionAlerts list"]
        AL2["Date / severity filter"]
    end

    subgraph REP["ReportsPage (/reports)"]
        RP1["Report generation form"]
        RP2["Download (CSV / JSON)"]
    end

    subgraph SET["SettingsPage (/settings)"]
        S1["Threshold sliders"]
        S2["TimingModeSwitch"]
        S3["GlossaryModal trigger"]
        S4["ThemeToggle"]
        S5["VehicleInjectionPanel"]
    end

    CTXDATA --> HOME
    CTXDATA --> DASH
    CTXDATA --> MAP
    CTXDATA --> ANA
    CTXDATA --> ALT
    CTXDATA --> REP
    CTXDATA --> SET

    subgraph ATOMS["Shared UI Atoms"]
        UI1["Badge"]
        UI2["Card"]
        UI3["ChartTooltip"]
        UI4["EmptyState"]
        UI5["ErrorState"]
        UI6["GlossaryModal"]
        UI7["LiveStatusBadge"]
        UI8["LoadingSpinner"]
        UI9["Logo"]
        UI10["PageIntro"]
        UI11["Skeleton"]
        UI12["StatusIndicator"]
        UI13["ThemeToggle"]
    end

    HOME & DASH & MAP & ANA & ALT & REP & SET --> ATOMS
```

---

## Service Layer

| File | Role |
|---|---|
| `services/api.ts` | Thin fetch wrapper — `BASE_URL = '/api'`; `apiFetch(path)` for GET, `apiPost(path, body)` for POST. All REST calls go through here. |
| `services/websocket.ts` | `TrafficWebSocket` class — connects to `ws[s]://host/ws/live`, parses JSON frames, calls registered listeners, reconnects with exponential back-off on close/error. |
| `context/TrafficContext.tsx` | `TrafficProvider` owns the WebSocket instance and REST polling intervals; exposes a single React context used by every page and widget. |

## Auth Gate

`App.tsx` reads `localStorage.getItem('intelliroads_token')`. If absent the user is redirected to `LoginPage`. On successful login the token is stored and the user enters the main app shell.

## Routing

React Router v6 nested routes. The outer `<Route>` renders `Header` + `Sidebar` + `<Outlet>`; each page is a child route. The sidebar renders navigation links for all 7 pages. No lazy-loading of route chunks was observed in `App.tsx`.
