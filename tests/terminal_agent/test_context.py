"""Tests for conversational session context and follow-up inheritance."""

import unittest
from src.terminal_agent.context import SessionContext
from src.terminal_agent.intent import IntentType


class TestSessionContext(unittest.TestCase):
    """Verify session state management across conversational turns."""

    def test_01_empty_initial_state(self):
        ctx = SessionContext()
        self.assertFalse(ctx.has_active_context())
        self.assertFalse(ctx.has_pending_clarification())
        self.assertIsNone(ctx.last_intent)
        self.assertIsNone(ctx.last_experiment_id)

    def test_02_radio_map_update_and_inheritance(self):
        ctx = SessionContext()
        base_config = {
            "scene_name": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, -10.0, 5.0],
            "cell_size": 5.0,
            "samples_per_tx": 10000,
        }
        mock_result = {
            "experiment_id": "experiment_20261101_100000_test1",
            "coverage_percentage": 95.5,
        }

        ctx.update_last_radio_map(base_config, mock_result)
        self.assertTrue(ctx.has_active_context())
        self.assertEqual(ctx.last_intent, IntentType.GENERATE_RADIO_MAP)
        self.assertEqual(ctx.last_experiment_id, "experiment_20261101_100000_test1")

        # User follow-up: 'Now generate the same map at 5 GHz'
        followup_params = {"frequency_hz": 5.0e9}
        merged = ctx.get_merged_radio_map_config(followup_params)

        self.assertAlmostEqual(merged["frequency_hz"], 5.0e9)
        self.assertEqual(merged["scene_name"], "simple_reflector")
        self.assertEqual(merged["tx_position"], [0.0, -10.0, 5.0])
        self.assertEqual(merged["cell_size"], 5.0)
        self.assertEqual(merged["samples_per_tx"], 10000)

    def test_03_pending_clarification_lifecycle(self):
        ctx = SessionContext()
        ctx.set_pending_clarification(
            intent=IntentType.GENERATE_RADIO_MAP,
            current_params={"frequency_hz": 3.5e9},
            param_name="scene_name",
            question="Which scene should I use?",
        )

        self.assertTrue(ctx.has_pending_clarification())
        self.assertEqual(ctx.pending_param_name, "scene_name")
        self.assertEqual(ctx.pending_intent, IntentType.GENERATE_RADIO_MAP)

        ctx.clear_pending()
        self.assertFalse(ctx.has_pending_clarification())

    def test_04_session_reset(self):
        ctx = SessionContext()
        ctx.update_last_radio_map({"scene_name": "simple_reflector"}, {"experiment_id": "exp_1"})
        ctx.set_pending_clarification(IntentType.RUN_SIMULATION, {}, "scene", "which scene?")

        ctx.reset()
        self.assertFalse(ctx.has_active_context())
        self.assertFalse(ctx.has_pending_clarification())
        self.assertIsNone(ctx.last_experiment_id)
        self.assertEqual(len(ctx.history), 0)


if __name__ == "__main__":
    unittest.main()

