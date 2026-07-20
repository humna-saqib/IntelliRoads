"""
IntelliRoads – API routes aggregator.
"""

from fastapi import APIRouter

from app.api.routes.vehicles import router as vehicles_router
from app.api.routes.classification import router as classification_router
from app.api.routes.density import router as density_router
from app.api.routes.congestion import router as congestion_router
from app.api.routes.signals import router as signals_router
from app.api.routes.kpis import router as kpis_router
from app.api.routes.intersections import router as intersections_router
from app.api.routes.emergency import router as emergency_router
from app.api.routes.occupancy import router as occupancy_router
from app.api.routes.performance import router as performance_router
from app.api.routes.rl import router as rl_router

api_router = APIRouter(prefix="/api")

api_router.include_router(vehicles_router)
api_router.include_router(classification_router)
api_router.include_router(density_router)
api_router.include_router(congestion_router)
api_router.include_router(signals_router)
api_router.include_router(kpis_router)
api_router.include_router(intersections_router)
api_router.include_router(emergency_router)
api_router.include_router(occupancy_router)
api_router.include_router(performance_router)
api_router.include_router(rl_router)
