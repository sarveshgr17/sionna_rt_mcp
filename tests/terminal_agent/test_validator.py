"""Tests for tool argument validation and error rejection."""

import unittest
from src.terminal_agent.validator import (
    validate_compare_experiments_args,
    validate_coordinates,
    validate_get_experiment_args,
    validate_radio_map_args,
    validate_simulation_args,
)


class TestValidator(unittest.TestCase):
    """Verify tool parameter bounds, type checks, and error messaging."""

    def test_01_coordinate_validation(self):
        ok, err = validate_coordinates([0.0, -10.0, 5.0])
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Wrong length
        ok2, err2 = validate_coordinates([0.0, 5.0])
        self.assertFalse(ok2)
        self.assertIn("must contain exactly 3 coordinates", err2)

        # Non-numeric
        ok3, err3 = validate_coordinates(["a", "b", "c"])
        self.assertFalse(ok3)
        self.assertIn("numeric values", err3)

    def test_02_radio_map_valid_arguments(self):
        params = {
            "scene_name": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, -10.0, 5.0],
            "cell_size": 5.0,
            "samples_per_tx": 10000,
        }
        res = validate_radio_map_args(params)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.arguments["scene_name"], "simple_reflector")
        self.assertAlmostEqual(res.arguments["frequency_hz"], 3.5e9)
        self.assertEqual(res.arguments["cell_size"], 5.0)

    def test_03_radio_map_invalid_rejections(self):
        # Negative frequency
        res1 = validate_radio_map_args({"frequency_hz": -100})
        self.assertFalse(res1.is_valid)
        self.assertIn("Frequency must be strictly greater than 0", res1.error_message)

        # Invalid coordinates
        res2 = validate_radio_map_args({"tx_position": [1, 2]})
        self.assertFalse(res2.is_valid)
        self.assertIn("tx_position must contain exactly 3 coordinates", res2.error_message)

        # Invalid cell size
        res3 = validate_radio_map_args({"cell_size": -5.0})
        self.assertFalse(res3.is_valid)
        self.assertIn("Cell size must be greater than 0", res3.error_message)

        # Low ray budget (< 100)
        res4 = validate_radio_map_args({"samples_per_tx": 50})
        self.assertFalse(res4.is_valid)
        self.assertIn("at least 100 rays", res4.error_message)

    def test_04_simulation_validation(self):
        params = {
            "scene": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, -10.0, 5.0],
            "rx_position": [0.0, 10.0, 5.0],
        }
        res = validate_simulation_args(params)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.arguments["tx_power_dbm"], 30.0)  # Default injected

    def test_05_get_experiment_details_validation(self):
        # With explicit ID
        res = validate_get_experiment_args({"experiment_id": "exp_123"})
        self.assertTrue(res.is_valid)
        self.assertEqual(res.arguments["experiment_id"], "exp_123")

        # Missing ID with no context
        res2 = validate_get_experiment_args({})
        self.assertFalse(res2.is_valid)
        self.assertTrue(res2.needs_clarification)
        self.assertEqual(res2.missing_param, "experiment_id")

        # Missing ID with context fallback
        res3 = validate_get_experiment_args({}, last_exp_id="exp_context_1")
        self.assertTrue(res3.is_valid)
        self.assertEqual(res3.arguments["experiment_id"], "exp_context_1")

    def test_06_compare_experiments_validation(self):
        # Both IDs present
        res = validate_compare_experiments_args({"experiment_id_a": "exp_a", "experiment_id_b": "exp_b"})
        self.assertTrue(res.is_valid)

        # One ID missing
        res2 = validate_compare_experiments_args({"experiment_id_a": "exp_a"})
        self.assertFalse(res2.is_valid)
        self.assertTrue(res2.needs_clarification)
        self.assertEqual(res2.missing_param, "experiment_id_b")

        # Both IDs missing
        res3 = validate_compare_experiments_args({})
        self.assertFalse(res3.is_valid)
        self.assertTrue(res3.needs_clarification)
        self.assertEqual(res3.missing_param, "experiment_id_a")


if __name__ == "__main__":
    unittest.main()

