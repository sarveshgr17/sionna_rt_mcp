"""Tests for intent recognition across all seven MCP tools and CLI commands."""

import unittest
from src.terminal_agent.intent import IntentType, classify_intent


class TestIntentRecognition(unittest.TestCase):
    """Verify deterministic intent classification."""

    def test_01_check_environment_intents(self):
        queries = [
            "Check whether Sionna is working",
            "Is Sionna ready?",
            "check environment",
            "sionna status",
            "verify simulator",
            "backend status",
            "system health",
        ]
        for q in queries:
            self.assertEqual(classify_intent(q), IntentType.CHECK_ENVIRONMENT, f"Failed for: {q}")

    def test_02_list_scenes_intents(self):
        queries = [
            "Show available scenes",
            "List scenes",
            "Which scene is the default?",
            "what scenes are available?",
            "what 3d models can I simulate?",
        ]
        for q in queries:
            self.assertEqual(classify_intent(q), IntentType.LIST_SCENES, f"Failed for: {q}")

    def test_03_run_simulation_intents(self):
        queries = [
            "Run a point-to-point simulation",
            "Calculate received power between two transmitter and receiver positions",
            "Simulate a link at 3.5 GHz",
            "point to point simulation",
            "simulate between [0,-10,5] and [0,10,5]",
        ]
        for q in queries:
            self.assertEqual(classify_intent(q), IntentType.RUN_SIMULATION, f"Failed for: {q}")

    def test_04_generate_radio_map_intents(self):
        queries = [
            "Generate a radio map at 3.5 GHz",
            "Create a coverage map for simple_reflector",
            "Generate coverage using 10000 rays and 5m resolution",
            "Generate a radio map for 28 GHz",
            "Show heat map",
            "generate heatmap",
        ]
        for q in queries:
            self.assertEqual(classify_intent(q), IntentType.GENERATE_RADIO_MAP, f"Failed for: {q}")

    def test_05_list_experiments_intents(self):
        queries = [
            "Show my previous experiments",
            "List experiments",
            "past experiments",
            "saved experiments",
            "experiment history",
            "recent simulations",
        ]
        for q in queries:
            self.assertEqual(classify_intent(q), IntentType.LIST_EXPERIMENTS, f"Failed for: {q}")

    def test_06_get_experiment_details_intents(self):
        queries = [
            "Give me details of experiment ID experiment_20261101_120000_12345678",
            "view experiment id experiment_20261101_120000_12345678",
            "show experiment id",
            "experiment_20261101_120000_12345678",
        ]
        for q in queries:
            self.assertEqual(classify_intent(q), IntentType.GET_EXPERIMENT_DETAILS, f"Failed for: {q}")

    def test_07_compare_experiments_intents(self):
        queries = [
            "Compare experiment A with experiment B",
            "compare experiment_20261101_111 with experiment_20261101_222",
            "Generate difference heatmaps for these experiments",
            "diff between experiment_1 and experiment_2",
        ]
        for q in queries:
            self.assertEqual(classify_intent(q), IntentType.COMPARE_EXPERIMENTS, f"Failed for: {q}")

    def test_08_cli_commands(self):
        self.assertEqual(classify_intent("/help"), IntentType.HELP)
        self.assertEqual(classify_intent("help"), IntentType.HELP)
        self.assertEqual(classify_intent("/tools"), IntentType.TOOLS)
        self.assertEqual(classify_intent("tools"), IntentType.TOOLS)
        self.assertEqual(classify_intent("/context"), IntentType.CONTEXT)
        self.assertEqual(classify_intent("/reset"), IntentType.RESET)
        self.assertEqual(classify_intent("/exit"), IntentType.EXIT)
        self.assertEqual(classify_intent("exit"), IntentType.EXIT)
        self.assertEqual(classify_intent("quit"), IntentType.EXIT)

    def test_09_confirmations_and_rejections(self):
        self.assertEqual(classify_intent("yes", awaiting_confirmation=True), IntentType.CONFIRMATION)
        self.assertEqual(classify_intent("proceed", awaiting_confirmation=True), IntentType.CONFIRMATION)
        self.assertEqual(classify_intent("no", awaiting_confirmation=True), IntentType.REJECTION)
        self.assertEqual(classify_intent("cancel", awaiting_confirmation=True), IntentType.REJECTION)

    def test_10_follow_up_with_active_context(self):
        # With active radio map context, parameter updates route back to GENERATE_RADIO_MAP
        self.assertEqual(
            classify_intent("Now generate at 5 GHz", has_active_context=True),
            IntentType.GENERATE_RADIO_MAP,
        )
        self.assertEqual(
            classify_intent("Change cell size to 2m", has_active_context=True),
            IntentType.GENERATE_RADIO_MAP,
        )


if __name__ == "__main__":
    unittest.main()

