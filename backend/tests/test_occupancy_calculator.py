import pytest
from unittest.mock import MagicMock, patch
from typing import List
from app.models.density import DensityLevel
from app.models.occupancy import OccupancyResponse
from app.models.vehicle import VehicleData
from app.services.occupancy_calculator import OccupancyCalculator, LOW_THRESHOLD, HIGH_THRESHOLD
from app.services.traci_session import TraCISession

def test_mock_occupancy_calculation(mock_session: TraCISession, mock_vehicles: List[VehicleData]):
    calc = OccupancyCalculator(session=mock_session)
    response = calc.calculate_all(mock_vehicles)

    assert isinstance(response, OccupancyResponse)
    assert len(response.lanes) > 0
    assert response.average_occupancy >= 0.0

    # lane_A_west_in has 2 cars (5.0m each = 10.0m occupied / 300m lane = 3.33%)
    west_in = next((l for l in response.lanes if l.lane_id == "lane_A_west_in"), None)
    assert west_in is not None
    assert west_in.occupancy_percent == 3.33
    assert west_in.occupancy_level == DensityLevel.LOW

def test_occupancy_level_thresholds(mock_session: TraCISession):
    calc = OccupancyCalculator(session=mock_session)
    
    assert calc.get_level(15.0) == DensityLevel.LOW
    assert calc.get_level(45.0) == DensityLevel.MEDIUM
    assert calc.get_level(75.0) == DensityLevel.HIGH

@patch("app.services.occupancy_calculator.traci")
def test_live_occupancy_calculation(mock_traci, mock_session: TraCISession):
    mock_session._mock_mode = False
    mock_traci.lane.getLastStepOccupancy.return_value = 0.45  # 45% occupancy
    
    calc = OccupancyCalculator(session=mock_session)
    response = calc.calculate_all([])
    
    assert isinstance(response, OccupancyResponse)
    assert len(response.lanes) > 0
    # Every lane should report 45.0%
    assert response.lanes[0].occupancy_percent == 45.0
    assert response.lanes[0].occupancy_level == DensityLevel.MEDIUM