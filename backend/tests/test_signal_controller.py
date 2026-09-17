import pytest
from typing import List
from app.models.density import DensityLevel, DensityResponse, LaneDensity
from app.models.signal import SignalPhaseType
from app.services.signal_controller import SignalController
from app.services.traci_session import TraCISession

def test_timing_rules(mock_session: TraCISession):
    controller = SignalController(session=mock_session)
    assert controller.TIMING_RULES[DensityLevel.LOW] == 20.0
    assert controller.TIMING_RULES[DensityLevel.MEDIUM] == 35.0
    assert controller.TIMING_RULES[DensityLevel.HIGH] == 55.0

def test_compute_timing(mock_session: TraCISession):
    controller = SignalController(session=mock_session)
    timing = controller.compute_timing("junctionA", DensityLevel.HIGH, SignalPhaseType.GREEN)
    
    assert timing.junction_id == "junctionA"
    assert timing.duration_seconds == 55.0
    assert timing.density_level == DensityLevel.HIGH
    assert timing.phase == SignalPhaseType.GREEN

def test_update_all_signals(mock_session: TraCISession):
    controller = SignalController(session=mock_session)
    
    density_response = DensityResponse(
        lanes=[
            LaneDensity(lane_id="lane_A_west_in", vehicle_count=15, lane_length_km=0.3, density=50.0, level=DensityLevel.HIGH, timestamp=1.0),
            LaneDensity(lane_id="lane_AB_west", vehicle_count=2, lane_length_km=0.4, density=5.0, level=DensityLevel.LOW, timestamp=1.0),
        ],
        average_density=27.5,
        timestamp=1.0,
    )

    controller.update_all_signals(density_response)
    signals = controller.get_current_signals()

    assert len(signals) == 4
    junction_ids = {s.junction_id for s in signals}
    assert junction_ids == {"junctionA", "junctionB", "junctionC", "junctionD"}