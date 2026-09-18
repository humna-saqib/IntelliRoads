import os
import sys
import time
import pytest
from typing import List
from unittest.mock import MagicMock

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath("backend"))

from app.models.vehicle import VehicleData, VehicleType
from app.services.traci_session import TraCISession
from app.core.state_store import InMemoryStateStore
from app.core.security import create_access_token
from app.main import app
from httpx import AsyncClient, ASGITransport

@pytest.fixture
def auth_token() -> str:
    return create_access_token("admin")

@pytest.fixture
def mock_session() -> TraCISession:
    session = TraCISession(config_path="dummy.sumocfg", step_length=1.0)
    session._mock_mode = True
    session._connected = True
    return session

@pytest.fixture
def mock_vehicles() -> List[VehicleData]:
    now = time.time()
    return [
        VehicleData(
            vehicle_id="v_car_1",
            speed=12.5,
            position_x=10.0,
            position_y=20.0,
            road_id="road_A",
            lane_id="lane_A_west_in",
            vehicle_type=VehicleType.CAR,
            waiting_time=2.0,
            timestamp=now,
        ),
        VehicleData(
            vehicle_id="v_car_2",
            speed=8.0,
            position_x=15.0,
            position_y=20.0,
            road_id="road_A",
            lane_id="lane_A_west_in",
            vehicle_type=VehicleType.CAR,
            waiting_time=5.0,
            timestamp=now,
        ),
        VehicleData(
            vehicle_id="v_bus_1",
            speed=5.0,
            position_x=5.0,
            position_y=25.0,
            road_id="road_A",
            lane_id="lane_A_north_in",
            vehicle_type=VehicleType.BUS,
            waiting_time=12.0,
            timestamp=now,
        ),
        VehicleData(
            vehicle_id="v_moto_1",
            speed=15.0,
            position_x=50.0,
            position_y=20.0,
            road_id="road_AB",
            lane_id="lane_AB_west",
            vehicle_type=VehicleType.MOTORCYCLE,
            waiting_time=0.0,
            timestamp=now,
        ),
        VehicleData(
            vehicle_id="v_em_1",
            speed=20.0,
            position_x=100.0,
            position_y=20.0,
            road_id="road_CD",
            lane_id="lane_CD_east",
            vehicle_type=VehicleType.EMERGENCY,
            waiting_time=1.0,
            timestamp=now,
        ),
    ]

@pytest.fixture
def state_store() -> InMemoryStateStore:
    store = InMemoryStateStore()
    app.state.store = store
    
    mock_dqn_ctrl = MagicMock()
    mock_dqn_ctrl.get_mode.return_value = MagicMock(value="RULE_BASED")
    mock_dqn_ctrl.set_mode.side_effect = lambda m: setattr(mock_dqn_ctrl.get_mode.return_value, 'value', str(m))
    app.state.dqn_controller = mock_dqn_ctrl
    
    return store

@pytest.fixture
async def async_client(state_store, auth_token) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {auth_token}"},
    ) as client:
        yield client

