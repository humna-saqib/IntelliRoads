import os
import pytest
from pathlib import Path

from app.services.traci_session import TraCISession
from app.services.vehicle_data_service import VehicleDataService
from app.services.density_calculator import DensityCalculator
from app.services.signal_controller import SignalController
from app.models.signal import SignalTiming

def test_sumo_e2e_short_smoke():
    os.environ["SUMO_USE_GUI"] = "false"
    
    # Locate SUMO config file
    cwd = Path.cwd()
    candidates = [
        cwd / "sumo" / "config" / "intelliroads.sumocfg",
        cwd / "backend" / "sumo" / "config" / "intelliroads.sumocfg",
        Path(__file__).parent.parent / "sumo" / "config" / "intelliroads.sumocfg",
    ]
    
    config_path = candidates[0]
    for c in candidates:
        if c.exists():
            config_path = c
            break

    assert config_path.exists(), f"SUMO config file not found at {config_path}"

    session = TraCISession(config_path=config_path, step_length=1.0)
    try:
        session.start()
    except Exception as exc:
        pytest.skip(f"SUMO connection could not be established: {exc}")

    try:
        data_service = VehicleDataService(session)
        density_calculator = DensityCalculator()
        signal_controller = SignalController(session)

        sim_time = 0.0
        # Run 5 simulation steps
        for _ in range(5):
            sim_time = session.step()
            vehicles = data_service.collect_all()
            density_response = density_calculator.calculate_all_densities(vehicles)
            signal_controller.update_all_signals(density_response)

        # Assertions
        assert sim_time >= 5.0, f"Expected simulation time >= 5.0, got {sim_time}"
        
        signals = signal_controller.get_current_signals()
        assert len(signals) == 4, f"Expected 4 junction signal decisions, got {len(signals)}"
        
        junction_ids = {s.junction_id for s in signals}
        assert junction_ids == {"junctionA", "junctionB", "junctionC", "junctionD"}
        
        for timing in signals:
            assert isinstance(timing, SignalTiming)
            assert timing.duration_seconds in (20.0, 35.0, 55.0)
            assert timing.junction_id in junction_ids
    finally:
        session.close()