"""
IntelliRoads – Signal timing API endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.state_store import InMemoryStateStore
from app.models.signal import SignalResponse, SignalTiming

router = APIRouter(prefix="/signals", tags=["signals"])


def get_store(request: Request) -> InMemoryStateStore:
    return request.app.state.store


@router.get("", response_model=SignalResponse)
async def get_signals(store: InMemoryStateStore = Depends(get_store)) -> SignalResponse:
    """
    Get current signal timings for all monitored junctions.
    """
    signals = await store.get_signals()
    if not signals:
        raise HTTPException(status_code=503, detail="Signal timing data not available yet.")
    return signals


@router.get("/{junction_id}", response_model=SignalTiming)
async def get_signal_by_junction(
    junction_id: str,
    store: InMemoryStateStore = Depends(get_store),
) -> SignalTiming:
    """
    Get current signal timing for a specific junction.
    """
    signals = await store.get_signals()
    if not signals:
        raise HTTPException(status_code=503, detail="Signal timing data not available yet.")
    
    for sig in signals.signals:
        if sig.junction_id == junction_id:
            return sig
            
    raise HTTPException(status_code=404, detail=f"Junction '{junction_id}' not found.")
