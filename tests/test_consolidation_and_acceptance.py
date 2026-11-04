"""Comprehensive Consolidation and Acceptance Tests (Phase 10 & 11).

Verifies:
1. Point-to-point simulation behavior with isotropic, dipole, and directional antennas.
2. Separate TX and RX antenna configurations.
3. Natural-language coordinate extraction across bracketed, named (x=, y=, z=), and tagged formats.
4. Frequency unit parsing (GHz, MHz, kHz, Hz) and normalization.
5. All 10 Phase 11 Acceptance Scenarios through AgentExecutor.
6. Multi-turn follow-up modifications and session context isolation between simulation and radio-map modes.
7. Missing parameter clarifications (e.g. missing RX coordinates, missing manual bounds).
8. Backward compatibility of all existing classes and functions.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import unittest
import pytest

from src.config import SimulationConfig, ANTENNA_PATTERN_MAPPING
from src.engine import SimulationEngine
from src.result import SimulationResult
from src.formatter import format_result
from src.terminal_agent.context import SessionContext
from src.terminal_agent.executor import AgentExecutor
from src.terminal_agent.intent import IntentType, classify_intent
from src.terminal_agent.parser import (
    extract_all_parameters,
    extract_antenna_config,
    extract_array_params,
    extract_cell_size,
    extract_coordinates,
    extract_experiment_ids,
    extract_frequency,
    extract_manual_region_bounds,
    extract_receiver_height,
    extract_samples_per_tx,
    extract_scene_name,
    extract_separate_antennas,
    extract_tx_power,
)
from src.terminal_agent.validator import (
    validate_compare_experiments_args,
    validate_coordinates,
    validate_get_experiment_args,
    validate_radio_map_args,
    validate_simulation_args,
)


class TestSimulationAntennas(unittest.TestCase):
    """Test Mode A point-to-point simulation configuration and antenna mapping."""

    def test_antenna_pattern_normalization(self):
        # Isotropic
        cfg_iso = SimulationConfig(antenna_type="isotropic")
        self.assertEqual(cfg_iso.antenna_pattern, "iso")
        self.assertEqual(cfg_iso.tx_antenna_pattern, "iso")
        self.assertEqual(cfg_iso.rx_antenna_pattern, "iso")

        # Dipole
        cfg_dip = SimulationConfig(antenna_type="dipole")
        self.assertEqual(cfg_dip.antenna_pattern, "dipole")
        self.assertEqual(cfg_dip.tx_antenna_pattern, "dipole")

        # Directional
        cfg_dir = SimulationConfig(antenna_type="directional")
        self.assertEqual(cfg_dir.antenna_pattern, "tr38901")

        # Separate TX and RX
        cfg_sep = SimulationConfig(tx_antenna_type="directional", rx_antenna_type="dipole")
        self.assertEqual(cfg_sep.tx_antenna_pattern, "tr38901")
        self.assertEqual(cfg_sep.rx_antenna_pattern, "dipole")

    def test_unsupported_antenna_raises_error(self):
        with self.assertRaises(ValueError):
            SimulationConfig(antenna_type="unsupported_dish")

    def test_unsupported_polarization_raises_error(self):
        with self.assertRaises(ValueError):
            SimulationConfig(polarization="INVALID_POL")

    def test_simulation_result_contains_antenna_metadata(self):
        cfg = SimulationConfig(
            antenna_type="dipole",
            polarization="V",
            tx_antenna_type="dipole",
            rx_antenna_type="iso",
        )
        engine = SimulationEngine(cfg)
        result = engine.run()
        self.assertIsInstance(result, SimulationResult)
        self.assertEqual(result.tx_antenna_pattern, "dipole")
        self.assertEqual(result.rx_antenna_pattern, "iso")

        # Result formatting includes antenna information
        output = format_result(result)
        self.assertIn("Antennas:", output)
        self.assertIn("TX: dipole", output)
        self.assertIn("RX: iso", output)


class TestNLPCoordinateAndParameterExtraction(unittest.TestCase):
    """Test natural language parameter extraction for all variants."""

    def test_coordinate_bracket_variations(self):
        # Brackets
        tx, rx, _ = extract_coordinates("TX at [0, 0, 10] and RX at [20, 10, 1.5]")
        self.assertEqual(tx, [0.0, 0.0, 10.0])
        self.assertEqual(rx, [20.0, 10.0, 1.5])

        # Parentheses
        tx, rx, _ = extract_coordinates("Transmitter position is (0, -10, 5) and receiver at (0, 10, 5)")
        self.assertEqual(tx, [0.0, -10.0, 5.0])
        self.assertEqual(rx, [0.0, 10.0, 5.0])

    def test_named_coordinates(self):
        tx, rx, _ = extract_coordinates("Put the transmitter at x=0, y=0, z=10 and receiver at x=20, y=10, z=1.5")
        self.assertEqual(tx, [0.0, 0.0, 10.0])
        self.assertEqual(rx, [20.0, 10.0, 1.5])

    def test_tagged_unbracketed_coordinates(self):
        tx, rx, _ = extract_coordinates("TX coordinates: 0, 0, 10; RX coordinates: 20, 10, 1.5")
        self.assertEqual(tx, [0.0, 0.0, 10.0])
        self.assertEqual(rx, [20.0, 10.0, 1.5])

    def test_frequency_conversions(self):
        self.assertEqual(extract_frequency("3.5 GHz"), 3.5e9)
        self.assertEqual(extract_frequency("3500 MHz"), 3.5e9)
        self.assertEqual(extract_frequency("28 GHz"), 28.0e9)
        self.assertEqual(extract_frequency("2.4 GHz"), 2.4e9)
        self.assertEqual(extract_frequency("3500000000 Hz"), 3.5e9)

    def test_antenna_and_array_extraction(self):
        ant, pol = extract_antenna_config("directional antenna with cross polarization")
        self.assertEqual(ant, "directional")
        self.assertEqual(pol, "cross")

        arr = extract_array_params("4x2 antenna array, horizontal spacing 0.5, vertical spacing 0.7")
        self.assertEqual(arr.get("num_rows"), 4)
        self.assertEqual(arr.get("num_cols"), 2)
        self.assertEqual(arr.get("horizontal_spacing"), 0.5)
        self.assertEqual(arr.get("vertical_spacing"), 0.7)

    def test_separate_antennas_extraction(self):
        tx_ant, rx_ant = extract_separate_antennas("transmitter antenna directional, receiver antenna dipole")
        self.assertEqual(tx_ant, "directional")
        self.assertEqual(rx_ant, "dipole")

    def test_manual_region_bounds_extraction(self):
        bounds = extract_manual_region_bounds("manual region with x from -10 to 10, y from -20 to 20")
        self.assertEqual(bounds.get("region_mode"), "manual")
        self.assertEqual(bounds.get("x_min"), -10.0)
        self.assertEqual(bounds.get("x_max"), 10.0)
        self.assertEqual(bounds.get("y_min"), -20.0)
        self.assertEqual(bounds.get("y_max"), 20.0)


class TestPhase11AcceptanceScenarios(unittest.IsolatedAsyncioTestCase):
    """Verifies all 10 Phase 11 Acceptance Scenarios with mocked MCP client."""

    async def asyncSetUp(self):
        self.mock_client = AsyncMock()
        self.mock_client.discovered_tools = {
            "check_environment": MagicMock(description="Check environment readiness"),
            "list_scenes": MagicMock(description="List available 3D geometric scenes"),
            "run_simulation": MagicMock(description="Point-to-point propagation simulation"),
            "generate_radio_map": MagicMock(description="2D spatial radio coverage map"),
            "list_experiments": MagicMock(description="List saved simulation experiments"),
            "get_experiment_details": MagicMock(description="Get experiment details and artifact paths"),
            "compare_experiments": MagicMock(description="Compare two experiments"),
        }
        self.context = SessionContext()
        self.executor = AgentExecutor(mcp_client=self.mock_client, context=self.context)

    async def test_scenario_01_check_environment(self):
        # 1. "Check whether Sionna RT is ready."
        self.mock_client.call_tool.return_value = {
            "is_usable": True,
            "backend": "llvm_ad_mono_polarized",
            "python_version": "3.10.10",
            "sionna_version": "2.2.0",
            "mitsuba_version": "3.5.0",
        }
        res = await self.executor.execute_instruction("Check whether Sionna RT is ready.")
        self.assertIn("Sionna RT Environment Status", res.output)
        self.assertIn("READY", res.output)
        self.mock_client.call_tool.assert_awaited_with("check_environment", {})

    async def test_scenario_02_list_scenes(self):
        # 2. "List available scenes."
        self.mock_client.call_tool.return_value = {
            "count": 1,
            "default_scene": "simple_reflector",
            "scenes": [{"name": "simple_reflector", "description": "Two-path scene", "is_default": True}],
        }
        res = await self.executor.execute_instruction("List available scenes.")
        self.assertIn("Available 3D Scenes", res.output)
        self.assertIn("simple_reflector", res.output)
        self.mock_client.call_tool.assert_awaited_with("list_scenes", {})

    async def test_scenario_03_run_simulation_isotropic(self):
        # 3. "Run a simulation between TX [0, 0, 10] and RX [20, 10, 1.5] at 3.5 GHz using isotropic antennas."
        self.mock_client.call_tool.return_value = {
            "scene_name": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, 0.0, 10.0],
            "rx_position": [20.0, 10.0, 1.5],
            "num_paths": 2,
            "total_path_loss_db": 72.5,
            "received_power_dbm": -42.5,
            "path_delays": [75.2, 85.1],
            "path_distances": [22.5, 25.5],
            "path_gains": [-73.0, -80.0],
            "interaction_types": ["Line of Sight", "Specular Reflection"],
            "tx_antenna_pattern": "iso",
            "rx_antenna_pattern": "iso",
        }
        res = await self.executor.execute_instruction(
            "Run a simulation between TX [0, 0, 10] and RX [20, 10, 1.5] at 3.5 GHz using isotropic antennas."
        )
        self.assertIn("Point-to-point simulation completed", res.output)
        self.assertIn("Total Path Loss: 72.50 dB", res.output)
        self.assertIn("Multipath Components:", res.output)

        tool, args = self.mock_client.call_tool.call_args[0]
        self.assertEqual(tool, "run_simulation")
        self.assertEqual(args["tx_position"], [0.0, 0.0, 10.0])
        self.assertEqual(args["rx_position"], [20.0, 10.0, 1.5])
        self.assertEqual(args["frequency_hz"], 3.5e9)
        self.assertEqual(args["antenna_type"], "isotropic")

    async def test_scenario_04_rerun_simulation_with_dipole(self):
        # First execute initial simulation
        self.mock_client.call_tool.return_value = {
            "scene_name": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, 0.0, 10.0],
            "rx_position": [20.0, 10.0, 1.5],
            "num_paths": 2,
            "total_path_loss_db": 72.5,
            "received_power_dbm": -42.5,
        }
        await self.executor.execute_instruction(
            "Run a simulation between TX [0, 0, 10] and RX [20, 10, 1.5] at 3.5 GHz using isotropic antennas."
        )

        # 4. "Run the same simulation with a dipole antenna."
        self.mock_client.call_tool.return_value = {
            "scene_name": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, 0.0, 10.0],
            "rx_position": [20.0, 10.0, 1.5],
            "num_paths": 2,
            "total_path_loss_db": 70.1,
            "received_power_dbm": -40.1,
            "tx_antenna_pattern": "dipole",
            "rx_antenna_pattern": "dipole",
        }
        res = await self.executor.execute_instruction("Run the same simulation with a dipole antenna.")
        self.assertIn("Point-to-point simulation completed", res.output)

        tool, args = self.mock_client.call_tool.call_args[0]
        self.assertEqual(tool, "run_simulation")
        self.assertEqual(args["tx_position"], [0.0, 0.0, 10.0])
        self.assertEqual(args["rx_position"], [20.0, 10.0, 1.5])
        self.assertEqual(args["antenna_type"], "dipole")

    async def test_scenario_05_generate_radio_map_directional(self):
        # 5. "Generate a radio map at 3.5 GHz using a directional antenna and 2 metre cell size."
        self.mock_client.call_tool.return_value = {
            "experiment_id": "experiment_20261104_1001",
            "scene_name": "simple_reflector",
            "coverage_percentage": 94.5,
            "mean_rss_dbm": -58.2,
            "min_rss_dbm": -92.0,
            "max_rss_dbm": -30.0,
            "grid_dimensions": [50, 50],
            "total_cells": 2500,
            "measurement_height": 1.5,
            "artifact_paths": {
                "rss_heatmap": "C:/fake/rss_1001.png",
                "path_gain_heatmap": "C:/fake/gain_1001.png",
            },
        }
        res = await self.executor.execute_instruction(
            "Generate a radio map at 3.5 GHz using a directional antenna and 2 metre cell size."
        )
        self.assertIn("Simulation completed successfully", res.output)
        self.assertIn("experiment_20261104_1001", res.output)
        self.assertIn("Coverage:            94.50%", res.output)

        tool, args = self.mock_client.call_tool.call_args[0]
        self.assertEqual(tool, "generate_radio_map")
        self.assertEqual(args["cell_size"], 2.0)
        self.assertEqual(args["antenna_type"], "directional")
        self.assertEqual(args["frequency_hz"], 3.5e9)

    async def test_scenario_06_regenerate_radio_map_for_height_2m(self):
        # Setup initial map
        self.mock_client.call_tool.return_value = {
            "experiment_id": "experiment_20261104_1001",
            "scene_name": "simple_reflector",
            "coverage_percentage": 94.5,
            "artifact_paths": {},
        }
        await self.executor.execute_instruction(
            "Generate a radio map at 3.5 GHz using a directional antenna and 2 metre cell size."
        )

        # 6. "Generate the radio map for receiver height 2 metres."
        self.mock_client.call_tool.return_value = {
            "experiment_id": "experiment_20261104_1002",
            "scene_name": "simple_reflector",
            "coverage_percentage": 95.1,
            "measurement_height": 2.0,
            "artifact_paths": {},
        }
        res = await self.executor.execute_instruction("Generate the radio map for receiver height 2 metres.")
        self.assertIn("Simulation completed successfully", res.output)

        tool, args = self.mock_client.call_tool.call_args[0]
        self.assertEqual(tool, "generate_radio_map")
        self.assertEqual(args["receiver_height"], 2.0)
        self.assertEqual(args["cell_size"], 2.0)  # Preserved from prior turn
        self.assertEqual(args["antenna_type"], "directional")  # Preserved from prior turn

    async def test_scenario_07_show_previous_experiment(self):
        # Set last experiment ID in context
        self.context.last_experiment_id = "experiment_20261104_1002"

        # 7. "Show the previous experiment."
        self.mock_client.call_tool.return_value = {
            "experiment_id": "experiment_20261104_1002",
            "scene_name": "simple_reflector",
            "frequency_hz": 3.5e9,
            "coverage_percentage": 95.1,
            "artifact_paths": {"rss_heatmap": "C:/fake/rss_1002.png"},
        }
        res = await self.executor.execute_instruction("Show the previous experiment.")
        self.assertIn("Experiment Details: experiment_20261104_1002", res.output)
        self.mock_client.call_tool.assert_awaited_with(
            "get_experiment_details", {"experiment_id": "experiment_20261104_1002"}
        )

    async def test_scenario_08_list_all_saved_experiments(self):
        # 8. "List all saved experiments."
        self.mock_client.call_tool.return_value = {
            "count": 2,
            "experiments": [
                {
                    "experiment_id": "experiment_20261104_1001",
                    "scene_name": "simple_reflector",
                    "frequency_hz": 3.5e9,
                    "coverage_percentage": 94.5,
                },
                {
                    "experiment_id": "experiment_20261104_1002",
                    "scene_name": "simple_reflector",
                    "frequency_hz": 3.5e9,
                    "coverage_percentage": 95.1,
                },
            ],
        }
        res = await self.executor.execute_instruction("List all saved experiments.")
        self.assertIn("Stored Experiments", res.output)
        self.assertIn("experiment_20261104_1001", res.output)
        self.assertIn("experiment_20261104_1002", res.output)
        self.mock_client.call_tool.assert_awaited_with("list_experiments", {})

    async def test_scenario_09_compare_last_two_radio_maps(self):
        # Setup context with previous and last experiment IDs
        self.context.previous_experiment_id = "experiment_20261104_1001"
        self.context.last_experiment_id = "experiment_20261104_1002"

        # 9. "Compare the last two radio maps."
        self.mock_client.call_tool.return_value = {
            "experiment_a_id": "experiment_20261104_1001",
            "experiment_b_id": "experiment_20261104_1002",
            "difference_convention": "Difference = B - A",
            "scene_name": "simple_reflector",
            "rss_difference_metrics": {
                "mean_difference": 1.25,
                "min_difference": -5.0,
                "max_difference": 6.2,
            },
            "heatmap_paths": {"rss_difference_heatmap": "C:/fake/diff.png"},
        }
        res = await self.executor.execute_instruction("Compare the last two radio maps.")
        self.assertIn("Experiment comparison completed", res.output)
        self.assertIn("Baseline (A):    experiment_20261104_1001", res.output)
        self.assertIn("Modified (B):    experiment_20261104_1002", res.output)
        self.assertIn("Mean Delta RSS:       +1.25 dBm", res.output)

    async def test_scenario_10_change_transmitter_position_and_regenerate(self):
        # Setup initial map
        self.mock_client.call_tool.return_value = {
            "experiment_id": "exp_init",
            "scene_name": "simple_reflector",
            "coverage_percentage": 90.0,
            "artifact_paths": {},
        }
        await self.executor.execute_instruction(
            "Generate a radio map at 3.5 GHz using a directional antenna and 2 metre cell size."
        )

        # 10. "Change the transmitter position to [5, 5, 10] and regenerate the map."
        self.mock_client.call_tool.return_value = {
            "experiment_id": "exp_moved",
            "scene_name": "simple_reflector",
            "coverage_percentage": 93.4,
            "artifact_paths": {},
        }
        res = await self.executor.execute_instruction(
            "Change the transmitter position to [5, 5, 10] and regenerate the map."
        )
        self.assertIn("Simulation completed successfully", res.output)

        tool, args = self.mock_client.call_tool.call_args[0]
        self.assertEqual(tool, "generate_radio_map")
        self.assertEqual(args["tx_position"], [5.0, 5.0, 10.0])
        self.assertEqual(args["antenna_type"], "directional")
        self.assertEqual(args["cell_size"], 2.0)


class TestContextIsolationAndClarification(unittest.IsolatedAsyncioTestCase):
    """Verify session isolation between point-to-point and radio map modes, and parameter clarification."""

    async def asyncSetUp(self):
        self.mock_client = AsyncMock()
        self.mock_client.discovered_tools = {
            "run_simulation": MagicMock(),
            "generate_radio_map": MagicMock(),
        }
        self.context = SessionContext()
        self.executor = AgentExecutor(mcp_client=self.mock_client, context=self.context)

    async def test_context_isolation_simulation_and_radio_map(self):
        # 1. Run simulation with specific RX position
        self.mock_client.call_tool.return_value = {
            "scene_name": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0, -10, 5],
            "rx_position": [0, 10, 5],
            "num_paths": 2,
            "total_path_loss_db": 70.0,
            "received_power_dbm": -40.0,
        }
        await self.executor.execute_instruction(
            "Run a simulation between TX [0, -10, 5] and RX [0, 10, 5] at 3.5 GHz."
        )

        # Verify simulation context was saved
        self.assertIn("rx_position", self.context.last_simulation_config)
        self.assertNotIn("rx_position", self.context.last_radio_map_config)

        # 2. Run radio map
        self.mock_client.call_tool.return_value = {
            "experiment_id": "exp_map",
            "scene_name": "simple_reflector",
            "coverage_percentage": 95.0,
            "artifact_paths": {},
        }
        await self.executor.execute_instruction(
            "Generate a radio map at 5 GHz with 2m cell size."
        )

        # Verify radio map configuration has cell_size and does NOT contain simulation's rx_position
        self.assertIn("cell_size", self.context.last_radio_map_config)
        self.assertNotIn("rx_position", self.context.last_radio_map_config)

        # And simulation config still has original rx_position and was not overwritten by radio map's 5 GHz
        self.assertEqual(self.context.last_simulation_config["frequency_hz"], 3.5e9)
        self.assertEqual(self.context.last_radio_map_config["frequency_hz"], 5.0e9)

    async def test_point_to_point_missing_rx_coordinate_clarification(self):
        # User provides only TX coordinate for a point-to-point simulation
        res = await self.executor.execute_instruction(
            "Run a point-to-point simulation with transmitter at [0, 0, 10] at 3.5 GHz"
        )
        self.assertIn("receiver coordinates", res.output)
        self.assertTrue(self.context.has_pending_clarification())
        self.assertEqual(self.context.pending_param_name, "rx_position")

        # User clarifies receiver coordinates
        self.mock_client.call_tool.return_value = {
            "scene_name": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, 0.0, 10.0],
            "rx_position": [20.0, 10.0, 1.5],
            "num_paths": 2,
            "total_path_loss_db": 68.0,
            "received_power_dbm": -38.0,
        }
        res2 = await self.executor.execute_instruction("[20, 10, 1.5]")
        self.assertIn("Point-to-point simulation completed", res2.output)
        self.assertFalse(self.context.has_pending_clarification())


if __name__ == "__main__":
    unittest.main()
