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

api_router = APIRouter(prefix="/api")

api_router.include_router(vehicles_router)
api_router.include_router(classification_router)
api_router.include_router(density_router)
api_router.include_router(congestion_router)
api_router.include_router(signals_router)
api_router.include_router(kpis_router)
api_router.include_router(intersections_router)
