import pytest
from unittest.mock import MagicMock
from app.controllers.dqn_controller import DQNController, ControllerMode
from app.models.density import DensityLevel, DensityResponse
from app.services.traci_session import TraCISession

def test_dqn_controller_mode_switching(mock_session: TraCISession):
    rule_controller = MagicMock()
    rule_controller.get_current_signals.return_value = []
    rule_controller.update_all_signals.return_value = None

    env = MagicMock()
    agent = MagicMock()

    controller = DQNController(
        session=mock_session,
        environment=env,
        agent=agent,
        rule_based_controller=rule_controller,
        mode=ControllerMode.RULE_BASED,
    )

    assert controller.get_mode() == ControllerMode.RULE_BASED

    # Switch to DQN
    controller.set_mode("DQN")
    assert controller.get_mode() == ControllerMode.DQN

    # Switch back to RULE_BASED
    controller.set_mode(ControllerMode.RULE_BASED)
    assert controller.get_mode() == ControllerMode.RULE_BASED

def test_dqn_controller_fallback(mock_session: TraCISession):
    rule_controller = MagicMock()
    rule_controller.get_current_signals.return_value = []
    
    env = MagicMock()
    env.junction_ids = ["junctionA"]
    env.get_state.side_effect = RuntimeError("DQN evaluation failed")

    agent = MagicMock()

    controller = DQNController(
        session=mock_session,
        environment=env,
        agent=agent,
        rule_based_controller=rule_controller,
        mode=ControllerMode.DQN,
    )

    density_response = DensityResponse(lanes=[], average_density=0.0, timestamp=1.0)
    signals = controller.control_step(density_response=density_response, vehicles=[], occupancy_response=None)

    # Controller should fall back to RULE_BASED mode upon exception
    assert controller.get_mode() == ControllerMode.RULE_BASED
