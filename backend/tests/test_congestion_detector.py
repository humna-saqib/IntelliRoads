import pytest
from app.models.density import DensityLevel, DensityResponse, LaneDensity
from app.models.congestion import CongestionStatus
from app.services.congestion_detector import CongestionDetector

def test_detect_congestion_event():
    detector = CongestionDetector()
    
    # 50 veh/km is > threshold (40.0) -> triggers CONGESTED
    density_response = DensityResponse(
        lanes=[
            LaneDensity(lane_id="lane_A_west_in", vehicle_count=15, lane_length_km=0.3, density=50.0, level=DensityLevel.HIGH, timestamp=1.0),
            LaneDensity(lane_id="lane_AB_west", vehicle_count=2, lane_length_km=0.4, density=5.0, level=DensityLevel.LOW, timestamp=1.0),
        ],
        average_density=27.5,
        timestamp=1.0,
    )

    res = detector.detect(density_response)
    assert res.total_congested == 1
    assert detector.is_congested("lane_A_west_in") is True
    assert detector.is_congested("lane_AB_west") is False

def test_resolve_congestion_event():
    detector = CongestionDetector()
    
    # Trigger event
    detector.detect_for_intersection("lane_A_west_in", 50.0)
    assert detector.is_congested("lane_A_west_in") is True

    # Manual resolve
    resolved = detector.resolve_event("lane_A_west_in")
    assert resolved is not None
    assert resolved.status == CongestionStatus.CLEAR
    assert detector.is_congested("lane_A_west_in") is False