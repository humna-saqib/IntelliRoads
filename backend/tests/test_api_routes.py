import pytest
from httpx import AsyncClient
from app.models.density import DensityLevel, DensityResponse, LaneDensity
from app.models.occupancy import OccupancyResponse, LaneOccupancy
from app.models.signal import SignalResponse, SignalTiming, SignalPhaseType
from app.models.congestion import CongestionResponse

@pytest.mark.asyncio
async def test_get_density_endpoint(async_client: AsyncClient, state_store):
    density_data = DensityResponse(
        lanes=[LaneDensity(lane_id="lane_A_west_in", vehicle_count=5, lane_length_km=0.3, density=16.67, level=DensityLevel.LOW, timestamp=1.0)],
        average_density=16.67,
        timestamp=1.0,
    )
    state_store._density = density_data

    res = await async_client.get("/api/density")
    assert res.status_code == 200
    data = res.json()
    assert "lanes" in data
    assert len(data["lanes"]) == 1

@pytest.mark.asyncio
async def test_get_occupancy_endpoint(async_client: AsyncClient, state_store):
    occ_data = OccupancyResponse(
        lanes=[LaneOccupancy(lane_id="lane_A_west_in", occupancy_percent=12.5, occupancy_level=DensityLevel.LOW, timestamp=1.0)],
        average_occupancy=12.5,
        timestamp=1.0,
    )
    state_store._occupancy = occ_data

    res = await async_client.get("/api/occupancy")
    assert res.status_code == 200
    data = res.json()
    assert "lanes" in data
    assert data["average_occupancy"] == 12.5

@pytest.mark.asyncio
async def test_get_signals_endpoint(async_client: AsyncClient, state_store):
    sig_data = SignalResponse(
        signals=[SignalTiming(junction_id="junctionA", phase=SignalPhaseType.GREEN, duration_seconds=35.0, density_level=DensityLevel.MEDIUM, triggered_at=1.0, reason="test")],
        timestamp=1.0,
    )
    state_store._signals = sig_data

    res = await async_client.get("/api/signals")
    assert res.status_code == 200
    data = res.json()
    assert "signals" in data
    assert len(data["signals"]) == 1
    assert data["signals"][0]["junction_id"] == "junctionA"

@pytest.mark.asyncio
async def test_get_congestion_endpoint(async_client: AsyncClient, state_store):
    cg_data = CongestionResponse(events=[], total_congested=0, timestamp=1.0)
    state_store._congestion = cg_data

    res = await async_client.get("/api/congestion")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert data["total_congested"] == 0

@pytest.mark.asyncio
async def test_rl_mode_endpoints(async_client: AsyncClient, state_store):
    res1 = await async_client.get("/api/rl/mode")
    assert res1.status_code == 200
    assert "mode" in res1.json()

    res2 = await async_client.post("/api/rl/mode", json={"mode": "DQN"})
    assert res2.status_code == 200
    assert res2.json()["mode"] == "DQN"