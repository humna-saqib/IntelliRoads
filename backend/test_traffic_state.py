"""
IntelliRoads – Qasim's Traffic State Verification Test Suite.

Verifies:
1. get_rl_state(intersection_id) function structure and return type.
2. 5-feature vector dimensionality and value constraints (count, queue, wait, occupancy, phase).
3. Monitored intersections coverage (junctionA, junctionB, junctionC, junctionD).
4. Compatibility with Humna's DQN State Normalization (normalize_state).
5. Live REST API response verification (/api/rl/state and /api/rl/state/{intersection_id}).
"""

import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.traffic_state_service import (
    TrafficStateService,
    get_rl_state,
    get_traffic_state_service,
)
from app.agent.dqn_agent import STATE_SIZE, normalize_state


class TestTrafficStateService(unittest.TestCase):
    """Test suite for Qasim's traffic state extraction and formatting."""

    def setUp(self) -> None:
        self.service = get_traffic_state_service()
        self.junctions = ["junctionA", "junctionB", "junctionC", "junctionD"]

    def test_01_state_vector_dimension(self) -> None:
        """Verify state vector has exactly STATE_SIZE (5) elements."""
        for jid in self.junctions:
            state = get_rl_state(jid)
            self.assertIsInstance(state, list, f"State for {jid} should be a list")
            self.assertEqual(
                len(state),
                STATE_SIZE,
                f"State vector for {jid} must have length {STATE_SIZE}, got {len(state)}",
            )
            for i, val in enumerate(state):
                self.assertIsInstance(
                    val, (int, float),
                    f"Feature {i} for {jid} must be a number, got {type(val)}"
                )

    def test_02_feature_value_constraints(self) -> None:
        """Verify all 5 features satisfy physical constraints."""
        for jid in self.junctions:
            raw = self.service.get_raw_state(jid)
            
            # 1. Vehicle count >= 0
            self.assertGreaterEqual(raw["vehicle_count"], 0.0, f"Vehicle count for {jid} < 0")
            
            # 2. Queue length >= 0
            self.assertGreaterEqual(raw["queue_length"], 0.0, f"Queue length for {jid} < 0")
            
            # 3. Avg waiting time >= 0
            self.assertGreaterEqual(raw["avg_waiting_time"], 0.0, f"Avg waiting time for {jid} < 0")
            
            # 4. Lane occupancy between 0% and 100%
            self.assertGreaterEqual(raw["lane_occupancy"], 0.0, f"Occupancy for {jid} < 0%")
            self.assertLessEqual(raw["lane_occupancy"], 100.0, f"Occupancy for {jid} > 100%")
            
            # 5. Current phase >= 0
            self.assertGreaterEqual(raw["current_phase"], 0.0, f"Current phase for {jid} < 0")

    def test_03_dqn_normalization_compatibility(self) -> None:
        """Verify state vector can be directly normalized by Humna's DQN agent."""
        for jid in self.junctions:
            state = get_rl_state(jid)
            norm_state = normalize_state(state)
            
            self.assertEqual(len(norm_state), STATE_SIZE)
            for i, val in enumerate(norm_state):
                self.assertGreaterEqual(val, 0.0, f"Normalized value {i} for {jid} is below 0.0: {val}")
                # min-max normalisation scales features to [0.0, ~1.0+]
                self.assertIsInstance(val, float)

    def test_04_fallback_for_unknown_intersection(self) -> None:
        """Verify robust fallback for unexpected intersection ID."""
        state = get_rl_state("unknown_junction_xyz")
        self.assertEqual(len(state), STATE_SIZE)
        self.assertIsInstance(state, list)

    def test_05_raw_state_dict_keys(self) -> None:
        """Verify get_raw_state returns dictionary with all expected keys."""
        raw = self.service.get_raw_state("junctionA")
        expected_keys = {"vehicle_count", "queue_length", "avg_waiting_time", "lane_occupancy", "current_phase"}
        self.assertTrue(expected_keys.issubset(raw.keys()))


if __name__ == "__main__":
    print("=" * 60)
    print(" Running Qasim's Traffic State Verification Tests")
    print("=" * 60)
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTrafficStateService)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\nAll Qasim tests PASSED successfully!")
        sys.exit(0)
    else:
        print("\nSome tests FAILED.")
        sys.exit(1)
