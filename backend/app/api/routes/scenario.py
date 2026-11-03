"""
IntelliRoads – manual traffic injection endpoint.

Lets an operator add a chosen number of vehicles to the running SUMO
simulation from the portal, to observe how the active signal controller
(rule-based or DQN) responds to the extra load.
"""

from __future__ import annotations

import itertools
from typing import Literal

import traci
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.traci_session import TraCISession

router = APIRouter(prefix="/scenario", tags=["scenario"])

MAX_VEHICLES = 300

ROUTES = [
    "route_top_east", "route_top_west",
    "route_bottom_east", "route_bottom_west",
    "route_left_south", "route_left_north",
    "route_right_south", "route_right_north",
]

_counter = itertools.count(1)


class InjectRequest(BaseModel):
    count: int = Field(..., ge=1, le=MAX_VEHICLES, description="Number of vehicles to add")
    vehicle_type: Literal["passenger", "motorcycle", "bus"] = "passenger"
    route: str = Field("all", description="A route id from /scenario/routes, or 'all' to spread evenly")
    spacing: float = Field(1.0, ge=0.5, le=10.0, description="Seconds between departures on the same route")


@router.get("/routes")
async def list_routes() -> dict:
    return {"routes": ROUTES, "max_vehicles": MAX_VEHICLES}


@router.post("/inject")
async def inject_vehicles(body: InjectRequest, request: Request) -> dict:
    session: TraCISession = request.app.state.session
    if session.mock_mode:
        raise HTTPException(status_code=409, detail="SUMO is not connected (mock mode); cannot inject vehicles.")
    if body.route != "all" and body.route not in ROUTES:
        raise HTTPException(status_code=422, detail=f"Unknown route '{body.route}'.")

    targets = ROUTES if body.route == "all" else [body.route]
    now = session.get_simulation_time()
    added = 0
    per_route: dict[str, int] = {}
    for i in range(body.count):
        route = targets[i % len(targets)]
        slot = per_route.get(route, 0)
        per_route[route] = slot + 1
        veh_id = f"manual_{next(_counter)}"
        try:
            traci.vehicle.add(
                veh_id, route, typeID=body.vehicle_type,
                depart=str(now + 1.0 + slot * body.spacing),
                departLane="best", departSpeed="max",
            )
            added += 1
        except traci.TraCIException as exc:
            raise HTTPException(status_code=500, detail=f"SUMO rejected vehicle {veh_id}: {exc}") from exc

    return {"status": "ok", "added": added, "vehicle_type": body.vehicle_type, "per_route": per_route}
