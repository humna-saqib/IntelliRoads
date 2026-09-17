"""
IntelliRoads — API routes aggregator.
"""

from fastapi import APIRouter, Depends

from app.api.routes.auth import router as auth_router
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
from app.api.routes.settings import router as settings_router
from app.core.security import get_current_user

api_router = APIRouter(prefix="/api")

# Unprotected authentication router
api_router.include_router(auth_router)

# Protected dashboard endpoints
protected_deps = [Depends(get_current_user)]
api_router.include_router(vehicles_router, dependencies=protected_deps)
api_router.include_router(classification_router, dependencies=protected_deps)
api_router.include_router(density_router, dependencies=protected_deps)
api_router.include_router(congestion_router, dependencies=protected_deps)
api_router.include_router(signals_router, dependencies=protected_deps)
api_router.include_router(kpis_router, dependencies=protected_deps)
api_router.include_router(intersections_router, dependencies=protected_deps)
api_router.include_router(emergency_router, dependencies=protected_deps)
api_router.include_router(occupancy_router, dependencies=protected_deps)
api_router.include_router(performance_router, dependencies=protected_deps)

# Untouched per security constraints (Settings & RL/DQN)
api_router.include_router(rl_router)
api_router.include_router(settings_router)