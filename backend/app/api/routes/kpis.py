"""
IntelliRoads – KPI API endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.state_store import InMemoryStateStore
from app.models.kpi import KPIData

router = APIRouter(prefix="/kpis", tags=["kpis"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("", response_model=KPIData)
async def get_kpis(store: InMemoryStateStore = Depends(get_store)) -> KPIData:
    """
    Get current simulation performance KPIs.
    """
    kpis = await store.get_kpis()
    if not kpis:
        raise HTTPException(status_code=503, detail="KPI calculations not available yet.")
    return kpis
