"""Tests for AgentExecutor conversation loop and multi-turn state handling."""

import unittest
from unittest.mock import AsyncMock
from src.terminal_agent.context import SessionContext
from src.terminal_agent.executor import AgentExecutor
from src.terminal_agent.mcp_client import MCPDirectClient


class TestAgentExecutor(unittest.IsolatedAsyncioTestCase):
    """Verify executor multi-turn conversation and tool invocation flow."""

    async def asyncSetUp(self):
        self.mock_client = AsyncMock(spec=MCPDirectClient)
        self.mock_client.discovered_tools = {
            "check_environment": AsyncMock(description="Check environment"),
            "list_scenes": AsyncMock(description="List scenes"),
            "run_simulation": AsyncMock(description="Run simulation"),
            "generate_radio_map": AsyncMock(description="Generate radio map"),
            "list_experiments": AsyncMock(description="List experiments"),
            "get_experiment_details": AsyncMock(description="Get experiment details"),
            "compare_experiments": AsyncMock(description="Compare experiments"),
        }
        self.context = SessionContext()
        self.executor = AgentExecutor(mcp_client=self.mock_client, context=self.context)

    async def test_01_cli_controls(self):
        res_help = await self.executor.execute_instruction("/help")
        self.assertIn("SIONNA RT RADIO PLANNER", res_help.output)

        res_tools = await self.executor.execute_instruction("/tools")
        self.assertIn("Registered MCP Tools", res_tools.output)
        self.assertIn("generate_radio_map", res_tools.output)

        res_reset = await self.executor.execute_instruction("/reset")
        self.assertIn("reset", res_reset.output)

        res_exit = await self.executor.execute_instruction("/exit")
        self.assertTrue(res_exit.is_exit)

    async def test_02_check_environment(self):
        self.mock_client.call_tool.return_value = {
            "is_usable": True,
            "backend": "llvm_ad_mono_polarized",
            "python_version": "3.10.10",
            "sionna_version": "2.2.0",
            "mitsuba_version": "3.9.1",
        }
        res = await self.executor.execute_instruction("Check whether Sionna is working")
        self.mock_client.call_tool.assert_called_with("check_environment", {})
        self.assertIn("READY (Usable)", res.output)
        self.assertIn("llvm_ad_mono_polarized", res.output)

    async def test_03_list_scenes(self):
        self.mock_client.call_tool.return_value = {
            "scenes": [
                {"name": "simple_reflector", "description": "Two-path scene", "is_default": True}
            ],
            "default_scene": "simple_reflector",
            "count": 1,
        }
        res = await self.executor.execute_instruction("Show available scenes")
        self.mock_client.call_tool.assert_called_with("list_scenes", {})
        self.assertIn("simple_reflector", res.output)

    async def test_04_radio_map_single_shot(self):
        self.mock_client.call_tool.return_value = {
            "status": "success",
            "experiment_id": "experiment_20261101_150000_abc123",
            "scene_name": "simple_reflector",
            "coverage_percentage": 97.5,
            "mean_rss_dbm": -62.3,
            "min_rss_dbm": -101.4,
            "max_rss_dbm": -35.2,
            "grid_dimensions": [50, 50],
            "total_cells": 2500,
            "artifact_paths": {
                "rss_heatmap": "C:/fake/rss_heatmap.png",
                "path_gain_heatmap": "C:/fake/path_gain_heatmap.png",
            },
        }

        prompt = (
            "Generate a radio map for simple_reflector at 3.5 GHz. "
            "Place transmitter at [0,-10,5]. Use 5 metre cell size and 10000 rays."
        )
        res = await self.executor.execute_instruction(prompt)

        # Verify tool was called with parsed parameters
        self.mock_client.call_tool.assert_called_once()
        tool_name, args = self.mock_client.call_tool.call_args[0]
        self.assertEqual(tool_name, "generate_radio_map")
        self.assertEqual(args["scene_name"], "simple_reflector")
        self.assertAlmostEqual(args["frequency_hz"], 3.5e9)
        self.assertEqual(args["tx_position"], [0.0, -10.0, 5.0])
        self.assertEqual(args["cell_size"], 5.0)
        self.assertEqual(args["samples_per_tx"], 10000)

        # Output assertions
        self.assertIn("Assistant: I understood your request.", res.output)
        self.assertIn("Experiment ID:       experiment_20261101_150000_abc123", res.output)
        self.assertIn("Coverage:            97.50%", res.output)
        self.assertIn("Mean RSS:            -62.30 dBm", res.output)
        self.assertIn("RSS Heatmap:       C:/fake/rss_heatmap.png", res.output)

    async def test_05_multi_turn_clarification(self):
        self.mock_client.call_tool.return_value = {
            "status": "success",
            "experiment_id": "experiment_20261101_999",
            "scene_name": "simple_reflector",
            "coverage_percentage": 90.0,
            "artifact_paths": {"rss_heatmap": "C:/fake/rss.png"},
        }

        # Turn 1: User gives partial command
        res1 = await self.executor.execute_instruction("Generate a radio map at 3.5 GHz")
        self.assertIn("Which scene should I use?", res1.output)

        # Turn 2: User provides scene
        res2 = await self.executor.execute_instruction("simple_reflector")
        self.assertIn("What cell size should I use?", res2.output)

        # Turn 3: User provides cell size
        res3 = await self.executor.execute_instruction("5 metres")
        self.assertIn("Simulation completed successfully", res3.output)

        # Verify tool was called
        tool_name, args = self.mock_client.call_tool.call_args[0]
        self.assertEqual(tool_name, "generate_radio_map")
        self.assertEqual(args["scene_name"], "simple_reflector")
        self.assertEqual(args["cell_size"], 5.0)
        self.assertAlmostEqual(args["frequency_hz"], 3.5e9)

    async def test_06_follow_up_with_context(self):
        # Setup initial completed radio map
        self.mock_client.call_tool.return_value = {
            "status": "success",
            "experiment_id": "exp_init",
            "scene_name": "simple_reflector",
            "coverage_percentage": 92.0,
            "artifact_paths": {},
        }
        await self.executor.execute_instruction(
            "Generate a radio map for simple_reflector at 3.5 GHz. Cell size 5m. 10000 rays."
        )

        # Follow-up: "Now generate the same map at 5 GHz."
        self.mock_client.call_tool.return_value = {
            "status": "success",
            "experiment_id": "exp_followup",
            "scene_name": "simple_reflector",
            "coverage_percentage": 88.0,
            "artifact_paths": {},
        }
        res = await self.executor.execute_instruction("Now generate the same map at 5 GHz.")
        self.assertIn("Simulation completed successfully", res.output)

        # Verify second call inherited cell_size and scene, but updated frequency
        tool_name, args = self.mock_client.call_tool.call_args[0]
        self.assertEqual(tool_name, "generate_radio_map")
        self.assertEqual(args["scene_name"], "simple_reflector")
        self.assertEqual(args["cell_size"], 5.0)
        self.assertEqual(args["samples_per_tx"], 10000)
        self.assertAlmostEqual(args["frequency_hz"], 5.0e9)


if __name__ == "__main__":
    unittest.main()

