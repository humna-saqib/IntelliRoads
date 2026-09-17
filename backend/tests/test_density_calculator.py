import pytest
from typing import List
from app.models.density import DensityLevel, DensityResponse, LaneDensity
from app.models.vehicle import VehicleData
from app.services.density_calculator import DensityCalculator

def test_calculate_lane_density_levels():
    calc = DensityCalculator()
    
    # LOW level (< 20 veh/km) -> 3 vehicles on 0.3km = 10.0 veh/km
    low_res = calc.calculate_lane_density("lane_A_west_in", 3)
    assert low_res.density == 10.0
    assert low_res.level == DensityLevel.LOW

    # MEDIUM level (20 <= density < 40 veh/km) -> 9 vehicles on 0.3km = 30.0 veh/km
    med_res = calc.calculate_lane_density("lane_A_west_in", 9)
    assert med_res.density == 30.0
    assert med_res.level == DensityLevel.MEDIUM

    # HIGH level (>= 40 veh/km) -> 15 vehicles on 0.3km = 50.0 veh/km
    high_res = calc.calculate_lane_density("lane_A_west_in", 15)
    assert high_res.density == 50.0
    assert high_res.level == DensityLevel.HIGH

def test_calculate_all_densities(mock_vehicles: List[VehicleData]):
    calc = DensityCalculator()
    response: DensityResponse = calc.calculate_all_densities(mock_vehicles)
    
    assert isinstance(response, DensityResponse)
    assert len(response.lanes) > 0
    assert response.average_density >= 0.0

    # Verify lane_A_west_in has count = 2 from mock_vehicles
    west_in = next((l for l in response.lanes if l.lane_id == "lane_A_west_in"), None)
    assert west_in is not None
    assert west_in.vehicle_count == 2
    assert west_in.density == round(2 / 0.3, 3)

def test_custom_lane_lengths():
    custom_lengths = {"custom_lane_1": 1.0}
    calc = DensityCalculator(lane_lengths=custom_lengths)
    res = calc.calculate_lane_density("custom_lane_1", 15)
    assert res.lane_length_km == 1.0
    assert res.density == 15.0

def test_get_average_density():
    calc = DensityCalculator()
    assert calc.get_average_density([]) == 0.0

    lanes = [
        LaneDensity(lane_id="l1", vehicle_count=10, lane_length_km=0.5, density=20.0, level=DensityLevel.LOW, timestamp=1.0),
        LaneDensity(lane_id="l2", vehicle_count=20, lane_length_km=0.5, density=40.0, level=DensityLevel.HIGH, timestamp=1.0),
    ]
    assert calc.get_average_density(lanes) == 30.0