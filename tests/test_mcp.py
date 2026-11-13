"""Unit and integration tests for the Sionna RT MCP server (Phase 7).

Covers all 30 verification items specified in Phase 7:
1. Existing MCP tools remain registered.
2. Existing point-to-point tool schemas remain unchanged.
3. Existing point-to-point tests continue passing.
4. generate_radio_map is registered.
5. Valid inputs construct the correct configuration.
6. Engine invocation uses the actual implemented API.
7. Result extraction is invoked correctly.
8. Heatmap formatter is invoked correctly.
9. ExperimentStore saves the completed experiment.
10. Successful response contains the experiment ID.
11. Invalid configuration returns a useful error.
12. Simulation failure does not report success or save an incomplete experiment.
13. list_experiments is registered.
14. Empty experiment list is handled.
15. Saved experiments are returned correctly.
16. get_experiment_details retrieves the requested experiment.
17. Nonexistent experiment IDs return useful errors.
18. Corrupted experiment metadata is handled safely.
19. compare_experiments is registered.
20. Correct A and B IDs are passed to the comparator.
21. Response clearly identifies the B - A convention.
22. Comparison metrics are returned.
23. Heatmap paths are returned when available.
24. Incompatible experiments return a useful error.
25. Missing experiment IDs are handled safely.
26. NumPy values are converted to serializable values.
27. Non-finite values do not break JSON serialization.
28. Tool errors do not crash the MCP server.
29. All four new tools are discoverable through the MCP tool listing.
30. Existing tools remain discoverable after integration.
"""

import asyncio
import inspect
import json
import os
import shutil
import sys
import tempfile
from typing import Any, Dict
import unittest
from unittest.mock import MagicMock, patch

# Ensure repository root and src directory are on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_dir = os.path.join(repo_root, "src")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    import numpy as np
except (ImportError, ModuleNotFoundError):
    np = None

try:
    from mcp_server import ToolError, create_mcp_server, mcp
except (ImportError, ModuleNotFoundError):
    from src.mcp_server import ToolError, create_mcp_server, mcp

try:
    from radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from src.radio_map_result import RadioMapResult

try:
    from experiment_store import ExperimentStore
except (ImportError, ModuleNotFoundError):
    from src.experiment_store import ExperimentStore

try:
    from radio_map_formatter import RadioMapFormatter
except (ImportError, ModuleNotFoundError):
    from src.radio_map_formatter import RadioMapFormatter

def _harmonize_module_aliases() -> None:
    """Ensure modules imported via 'src.<mod>' and '<mod>' share identical class identities."""
    for mod_name in [
        "config",
        "engine",
        "result",
        "formatter",
        "simulation",
        "radio_map_config",
        "radio_map_engine",
        "radio_map_result",
        "radio_map_formatter",
        "experiment_store",
        "experiment_comparator",
    ]:
        src_name = f"src.{mod_name}"
        if src_name in sys.modules and mod_name not in sys.modules:
            sys.modules[mod_name] = sys.modules[src_name]
        elif mod_name in sys.modules and src_name not in sys.modules:
            sys.modules[src_name] = sys.modules[mod_name]

_harmonize_module_aliases()


def _extract_data(call_result: Any) -> Dict[str, Any]:
    """Helper to extract structured tool result payload from MCP CallToolResult or FastMCP tuple."""
    if isinstance(call_result, tuple):
        if len(call_result) > 1 and isinstance(call_result[1], dict):
            if "result" in call_result[1]:
                return call_result[1]["result"]
            return call_result[1]
        if len(call_result) > 0 and isinstance(call_result[0], list):
            if len(call_result[0]) > 0 and hasattr(call_result[0][0], "text") and call_result[0][0].text:
                try:
                    return json.loads(call_result[0][0].text)
                except Exception:
                    pass
    if hasattr(call_result, "structured_content") and call_result.structured_content:
        if "result" in call_result.structured_content:
            return call_result.structured_content["result"]
        return call_result.structured_content
    if hasattr(call_result, "content") and call_result.content and hasattr(call_result.content[0], "text"):
        return json.loads(call_result.content[0].text)
    return {}


def _create_mock_raw_radio_map(ny: int = 4, nx: int = 5, height: float = 1.5) -> Any:
    """Create a mock raw Sionna RT RadioMap object for testing."""
    class MockRawRadioMap:
        def __init__(self):
            # Shape [1, Ny, Nx]
            gain = np.ones((1, ny, nx), dtype=np.float64) * 1e-5
            gain[0, 0, 0] = 0.0  # One unreachable cell (-inf)
            self.path_gain = gain
            self.rss = gain * 1.0  # 1 Watt
            # Shape [Ny, Nx, 3]
            centers = np.zeros((ny, nx, 3), dtype=np.float64)
            for r in range(ny):
                for c in range(nx):
                    centers[r, c] = [c * 10.0 + 5.0, r * 8.0 + 4.0, height]
            self.cell_centers = centers

    return MockRawRadioMap()


class TestMCPServer(unittest.TestCase):
    """Unit and integration test suite covering all 30 Phase 7 verification requirements."""

    def setUp(self):
        """Set up fresh server and temporary storage environment."""
        if np is None:
            self.skipTest("NumPy is required for MCP server tests.")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = os.path.join(self.temp_dir.name, "experiments")
        os.makedirs(self.storage_dir, exist_ok=True)

        self.store_patcher = patch(
            "experiment_store.DEFAULT_EXPERIMENTS_DIR", self.storage_dir
        )
        self.store_patcher.start()

        self.server = create_mcp_server()

    def tearDown(self):
        """Clean up patches and temporary directories."""
        self.store_patcher.stop()
        self.temp_dir.cleanup()

    # =========================================================================
    # Group 1: Existing Point-to-Point Functionality (Items 1, 2, 3)
    # =========================================================================

    def test_01_existing_mcp_tools_remain_registered(self):
        """Verify that existing point-to-point tools remain registered."""
        async def _check():
            tools = await self.server.list_tools()
            names = [t.name for t in tools]
            self.assertIn("check_environment", names)
            self.assertIn("list_scenes", names)
            self.assertIn("run_simulation", names)
        asyncio.run(_check())

    def test_02_existing_point_to_point_tool_schemas_unchanged(self):
        """Verify that existing run_simulation parameter signature remains backward-compatible."""
        # Find run_simulation tool
        tool_func = self.server._tools["run_simulation"]["func"]
        sig = inspect.signature(tool_func)
        param_names = list(sig.parameters.keys())
        expected_params = [
            "scene",
            "frequency_hz",
            "tx_position",
            "rx_position",
            "tx_power_dbm",
            "antenna_type",
            "polarization",
            "num_rows",
            "num_cols",
            "horizontal_spacing",
            "vertical_spacing",
            "max_depth",
            "tx_antenna_type",
            "rx_antenna_type",
            "tx_orientation_deg",
            "rx_orientation_deg",
        ]
        self.assertEqual(param_names, expected_params)

    def test_03_existing_point_to_point_tests_continue_passing(self):
        """Verify existing point-to-point tools execute and return valid structures."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "scene_name": "munich",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, 0.0, 35.0],
            "rx_position": [60.0, 20.0, 1.5],
            "tx_power_dbm": 30.0,
            "backend": "llvm_ad_mono_polarized",
            "num_paths": 2,
            "total_path_loss": 66.8,
            "received_power": -36.8,
            "path_delays": [66.7, 74.6],
            "path_distances": [20.0, 22.36],
            "path_gains": [-66.8, -72.0],
            "interaction_types": ["Line of Sight", "Specular Reflection"],
        }

        async def _run():
            # 1. check_environment
            env_res = await self.server.call_tool("check_environment", {})
            env_data = _extract_data(env_res)
            self.assertIn("python_version", env_data)
            self.assertIn("backend", env_data)

            # 2. list_scenes
            scenes_res = await self.server.call_tool("list_scenes", {})
            scenes_data = _extract_data(scenes_res)
            self.assertEqual(scenes_data["default_scene"], "munich")

            # 3. run_simulation
            with patch("mcp_server.SimulationEngine") as mock_engine_cls:
                mock_engine_cls.return_value.run.return_value = mock_result
                params = {
                    "scene": "munich",
                    "frequency_hz": 3.5e9,
                    "tx_position": [0.0, 0.0, 35.0],
                    "rx_position": [60.0, 20.0, 1.5],
                    "tx_power_dbm": 30.0,
                }
                sim_res = await self.server.call_tool("run_simulation", params)
                sim_data = _extract_data(sim_res)
                self.assertEqual(sim_data["scene_name"], "munich")
                self.assertEqual(sim_data["num_paths"], 2)

        asyncio.run(_run())

    # =========================================================================
    # Group 2: Radio-Map Generation (Items 4, 5, 6, 7, 8, 9, 10, 11, 12)
    # =========================================================================

    def test_04_generate_radio_map_is_registered(self):
        """Verify generate_radio_map is registered on the MCP server."""
        async def _check():
            tools = await self.server.list_tools()
            names = [t.name for t in tools]
            self.assertIn("generate_radio_map", names)
        asyncio.run(_check())

    def test_05_valid_inputs_construct_correct_configuration(self):
        """Verify valid tool inputs construct a valid RadioMapConfig instance."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5, height=2.0)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                params = {
                    "scene_name": "simple_reflector",
                    "frequency_hz": 5.0e9,
                    "tx_position": [10.0, 20.0, 15.0],
                    "tx_power_dbm": 25.0,
                    "antenna_type": "dipole",
                    "polarization": "V",
                    "receiver_height": 2.0,
                    "cell_size": 2.0,
                }
                res = await self.server.call_tool("generate_radio_map", params)
                data = _extract_data(res)
                self.assertEqual(data["scene_name"], "simple_reflector")
                self.assertEqual(data["frequency_hz"], 5.0e9)
                self.assertEqual(data["tx_power_dbm"], 25.0)
                self.assertEqual(data["antenna_type"], "dipole")
                self.assertEqual(data["measurement_height"], 2.0)

        asyncio.run(_run())

    def test_06_engine_invocation_uses_actual_api(self):
        """Verify RadioMapEngine is instantiated with RadioMapConfig and run() is called."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                _ = await self.server.call_tool("generate_radio_map", {})
                self.assertTrue(mock_engine_cls.called)
                self.assertTrue(mock_inst.run.called)

        asyncio.run(_run())

    def test_07_result_extraction_invoked_correctly(self):
        """Verify RadioMapResult.from_raw_radio_map extracts numerical fields."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls, \
                 patch.object(RadioMapResult, "from_raw_radio_map", wraps=RadioMapResult.from_raw_radio_map) as mock_extract:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                _ = await self.server.call_tool("generate_radio_map", {})
                self.assertTrue(mock_extract.called)

        asyncio.run(_run())

    def test_08_heatmap_formatter_invoked_correctly(self):
        """Verify RadioMapFormatter.generate_heatmaps is invoked when visualization is available."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls, \
                 patch.object(RadioMapFormatter, "generate_heatmaps", wraps=RadioMapFormatter.generate_heatmaps) as mock_vis:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res = await self.server.call_tool("generate_radio_map", {})
                data = _extract_data(res)
                if RadioMapFormatter.is_visualization_available():
                    self.assertTrue(mock_vis.called)
                    self.assertTrue(data["heatmaps_available"]["rss_heatmap"])

        asyncio.run(_run())

    def test_09_experiment_store_saves_completed_experiment(self):
        """Verify ExperimentStore persists the completed experiment to disk."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res = await self.server.call_tool("generate_radio_map", {})
                exp_id = _extract_data(res)["experiment_id"]

                store = ExperimentStore(self.storage_dir)
                exp_dir = os.path.join(self.storage_dir, exp_id)
                self.assertTrue(os.path.isdir(exp_dir))
                self.assertTrue(os.path.isfile(os.path.join(exp_dir, "metadata.json")))
                self.assertTrue(os.path.isfile(os.path.join(exp_dir, "radio_map_data.npz")))

        asyncio.run(_run())

    def test_10_successful_response_contains_experiment_id(self):
        """Verify successful response contains non-empty experiment_id string."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res = await self.server.call_tool("generate_radio_map", {})
                data = _extract_data(res)
                self.assertEqual(data["status"], "success")
                self.assertIsInstance(data["experiment_id"], str)
                self.assertTrue(data["experiment_id"].startswith("experiment_"))

        asyncio.run(_run())

    def test_11_invalid_configuration_returns_useful_error(self):
        """Verify invalid configuration inputs raise ToolError with descriptive message."""
        async def _run():
            with self.assertRaises(ToolError) as ctx:
                await self.server.call_tool("generate_radio_map", {"antenna_type": "invalid_pattern_xyz"})
            self.assertIn("Invalid antenna_type", str(ctx.exception))

            with self.assertRaises(ToolError) as ctx:
                await self.server.call_tool("generate_radio_map", {"frequency_hz": -1.0})
            self.assertIn("frequency_hz must be a positive", str(ctx.exception))

        asyncio.run(_run())

    def test_12_simulation_failure_does_not_save_incomplete_experiment(self):
        """Verify simulation failure raises ToolError and does not leave partial directories."""
        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.run.side_effect = RuntimeError("GPU ray tracer fault")
                mock_engine_cls.return_value = mock_inst

                with self.assertRaises(ToolError) as ctx:
                    await self.server.call_tool("generate_radio_map", {})
                self.assertIn("Radio map simulation execution failed", str(ctx.exception))

            store = ExperimentStore(self.storage_dir)
            self.assertEqual(len(store.list_experiments()), 0)

        asyncio.run(_run())

    # =========================================================================
    # Group 3: Experiment Retrieval (Items 13, 14, 15, 16, 17, 18)
    # =========================================================================

    def test_13_list_experiments_is_registered(self):
        """Verify list_experiments is registered on the server."""
        async def _check():
            tools = await self.server.list_tools()
            names = [t.name for t in tools]
            self.assertIn("list_experiments", names)
        asyncio.run(_check())

    def test_14_empty_experiment_list_handled(self):
        """Verify list_experiments returns count 0 when no experiments exist."""
        async def _run():
            res = await self.server.call_tool("list_experiments", {})
            data = _extract_data(res)
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["count"], 0)
            self.assertEqual(data["experiments"], [])
        asyncio.run(_run())

    def test_15_saved_experiments_returned_correctly(self):
        """Verify list_experiments lists saved experiments."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res1 = await self.server.call_tool("generate_radio_map", {"experiment_name": "alpha"})
                id1 = _extract_data(res1)["experiment_id"]

                list_res = await self.server.call_tool("list_experiments", {})
                data = _extract_data(list_res)
                self.assertEqual(data["count"], 1)
                self.assertEqual(data["experiments"][0]["experiment_id"], id1)
                self.assertEqual(data["experiments"][0]["experiment_name"], "alpha")

        asyncio.run(_run())

    def test_16_get_experiment_details_retrieves_requested_experiment(self):
        """Verify get_experiment_details retrieves full metadata and artifact paths."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res = await self.server.call_tool("generate_radio_map", {"experiment_name": "detail_check"})
                exp_id = _extract_data(res)["experiment_id"]

                det_res = await self.server.call_tool("get_experiment_details", {"experiment_id": exp_id})
                data = _extract_data(det_res)
                self.assertEqual(data["status"], "success")
                self.assertEqual(data["experiment_id"], exp_id)
                self.assertEqual(data["experiment_name"], "detail_check")
                self.assertIn("artifact_paths", data)

        asyncio.run(_run())

    def test_17_get_experiment_details_nonexistent_id_returns_error(self):
        """Verify ToolError on nonexistent experiment ID."""
        async def _run():
            with self.assertRaises(ToolError) as ctx:
                await self.server.call_tool("get_experiment_details", {"experiment_id": "experiment_ghost_999"})
            self.assertIn("not found", str(ctx.exception).lower())
        asyncio.run(_run())

    def test_18_corrupted_experiment_metadata_handled_safely(self):
        """Verify ToolError is raised when metadata is corrupted without crashing server."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res = await self.server.call_tool("generate_radio_map", {})
                exp_id = _extract_data(res)["experiment_id"]

                meta_path = os.path.join(self.storage_dir, exp_id, "metadata.json")
                with open(meta_path, "w") as f:
                    f.write("{ invalid syntax")

                with self.assertRaises(ToolError) as ctx:
                    await self.server.call_tool("get_experiment_details", {"experiment_id": exp_id})
                self.assertIn("corrupted", str(ctx.exception).lower())
        asyncio.run(_run())

    # =========================================================================
    # Group 4: Experiment Comparison (Items 19, 20, 21, 22, 23, 24, 25)
    # =========================================================================

    def test_19_compare_experiments_is_registered(self):
        """Verify compare_experiments is registered on the server."""
        async def _check():
            tools = await self.server.list_tools()
            names = [t.name for t in tools]
            self.assertIn("compare_experiments", names)
        asyncio.run(_check())

    def test_20_correct_a_and_b_ids_passed_to_comparator(self):
        """Verify experiment_id_a and experiment_id_b are passed and reflected in result."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res_a = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 20.0})
                id_a = _extract_data(res_a)["experiment_id"]

                res_b = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 30.0})
                id_b = _extract_data(res_b)["experiment_id"]

                comp_res = await self.server.call_tool(
                    "compare_experiments",
                    {"experiment_id_a": id_a, "experiment_id_b": id_b},
                )
                data = _extract_data(comp_res)
                self.assertEqual(data["experiment_a_id"], id_a)
                self.assertEqual(data["experiment_b_id"], id_b)

        asyncio.run(_run())

    def test_21_response_clearly_identifies_b_minus_a_convention(self):
        """Verify comparison response clearly identifies B - A difference convention."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res_a = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 20.0})
                id_a = _extract_data(res_a)["experiment_id"]
                res_b = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 30.0})
                id_b = _extract_data(res_b)["experiment_id"]

                comp_res = await self.server.call_tool(
                    "compare_experiments",
                    {"experiment_id_a": id_a, "experiment_id_b": id_b},
                )
                data = _extract_data(comp_res)
                self.assertEqual(data["difference_convention"], "B - A (Experiment B minus Experiment A)")

        asyncio.run(_run())

    def test_22_comparison_metrics_returned(self):
        """Verify comparison metrics (total, valid, min/max/mean, stronger/weaker) are returned."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res_a = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 20.0})
                id_a = _extract_data(res_a)["experiment_id"]
                res_b = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 30.0})
                id_b = _extract_data(res_b)["experiment_id"]

                comp_res = await self.server.call_tool(
                    "compare_experiments",
                    {"experiment_id_a": id_a, "experiment_id_b": id_b},
                )
                data = _extract_data(comp_res)
                self.assertIn("rss_difference_metrics", data)
                self.assertIn("path_gain_difference_metrics", data)
                self.assertEqual(data["total_cells"], 20)
                self.assertIn("valid_cells", data)
                self.assertIn("b_stronger_cells", data["rss_difference_metrics"])

        asyncio.run(_run())

    def test_23_heatmap_paths_returned_when_available(self):
        """Verify difference heatmap paths are returned in comparison result."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res_a = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 20.0})
                id_a = _extract_data(res_a)["experiment_id"]
                res_b = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 30.0})
                id_b = _extract_data(res_b)["experiment_id"]

                comp_res = await self.server.call_tool(
                    "compare_experiments",
                    {"experiment_id_a": id_a, "experiment_id_b": id_b, "generate_heatmaps": True},
                )
                data = _extract_data(comp_res)
                self.assertIn("heatmaps", data)
                self.assertIn("artifacts", data)
                self.assertIn("heatmaps_available", data)

                # Verify both RSS and Path Gain difference heatmaps are present when enabled
                heatmaps = data["heatmaps"]
                self.assertIn("rss_diff_heatmap", heatmaps)
                self.assertIn("path_gain_diff_heatmap", heatmaps)
                self.assertTrue(heatmaps["rss_diff_heatmap"].endswith(".png"))
                self.assertTrue(heatmaps["path_gain_diff_heatmap"].endswith(".png"))
                self.assertTrue(os.path.exists(heatmaps["rss_diff_heatmap"]))
                self.assertTrue(os.path.exists(heatmaps["path_gain_diff_heatmap"]))

                # Verify artifacts dict also exposes both heatmaps
                artifacts = data["artifacts"]
                self.assertEqual(artifacts["rss_diff_heatmap"], heatmaps["rss_diff_heatmap"])
                self.assertEqual(artifacts["path_gain_diff_heatmap"], heatmaps["path_gain_diff_heatmap"])

                # Verify availability flags
                self.assertTrue(data["heatmaps_available"]["rss_diff_heatmap"])
                self.assertTrue(data["heatmaps_available"]["path_gain_diff_heatmap"])

        asyncio.run(_run())

    def test_24_incompatible_experiments_return_useful_error(self):
        """Verify spatial mismatch raises ToolError identifying the exact mismatching property."""
        mock_raw1 = _create_mock_raw_radio_map(ny=4, nx=5)
        mock_raw2 = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw1
                mock_engine_cls.return_value = mock_inst

                # Exp A height 1.5 m
                res_a = await self.server.call_tool("generate_radio_map", {"receiver_height": 1.5})
                id_a = _extract_data(res_a)["experiment_id"]

                # Exp B height 2.5 m
                mock_raw2.cell_centers[:, :, 2] = 2.5
                mock_inst.run.return_value = mock_raw2
                res_b = await self.server.call_tool("generate_radio_map", {"receiver_height": 2.5})
                id_b = _extract_data(res_b)["experiment_id"]

                with self.assertRaises(ToolError) as ctx:
                    await self.server.call_tool(
                        "compare_experiments",
                        {"experiment_id_a": id_a, "experiment_id_b": id_b},
                    )
                self.assertIn("measurement_height", str(ctx.exception))

        asyncio.run(_run())

    def test_25_missing_experiment_ids_handled_safely(self):
        """Verify ToolError when comparing nonexistent experiment IDs."""
        async def _run():
            with self.assertRaises(ToolError) as ctx:
                await self.server.call_tool(
                    "compare_experiments",
                    {"experiment_id_a": "ghost_1", "experiment_id_b": "ghost_2"},
                )
            self.assertIn("not found", str(ctx.exception).lower())
        asyncio.run(_run())

    # =========================================================================
    # Group 5: Response Integrity & Discovery (Items 26, 27, 28, 29, 30)
    # =========================================================================

    def test_26_numpy_values_converted_to_serializable_values(self):
        """Verify all response values are native Python types and json-dump cleanly."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res = await self.server.call_tool("generate_radio_map", {})
                data = _extract_data(res)

                # Check types
                self.assertIsInstance(data["frequency_hz"], (int, float))
                self.assertIsInstance(data["grid_dimensions"], list)
                self.assertIsInstance(data["tx_position"], list)

        asyncio.run(_run())

    def test_27_non_finite_values_do_not_break_json_serialization(self):
        """Verify non-finite -inf values in radio maps serialize cleanly to JSON."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res = await self.server.call_tool("generate_radio_map", {})
                data = _extract_data(res)

                json_str = json.dumps(data)
                self.assertIsInstance(json_str, str)
                self.assertNotIn("NaN", json_str)
                self.assertNotIn("Infinity", json_str)

        asyncio.run(_run())

    def test_28_tool_errors_do_not_crash_server(self):
        """Verify tool errors do not crash or corrupt the MCP server state."""
        async def _run():
            for _ in range(3):
                with self.assertRaises(ToolError):
                    await self.server.call_tool("generate_radio_map", {"frequency_hz": -1.0})

            # Normal operations continue working
            res = await self.server.call_tool("list_scenes", {})
            data = _extract_data(res)
            self.assertEqual(data["default_scene"], "munich")

        asyncio.run(_run())

    def test_29_all_four_new_tools_discoverable(self):
        """Verify all 4 new radio-map tools are discoverable in list_tools()."""
        async def _check():
            tools = await self.server.list_tools()
            names = [t.name for t in tools]
            self.assertIn("generate_radio_map", names)
            self.assertIn("list_experiments", names)
            self.assertIn("get_experiment_details", names)
            self.assertIn("compare_experiments", names)
        asyncio.run(_check())

    def test_30_existing_tools_remain_discoverable(self):
        """Verify existing point-to-point tools remain discoverable alongside new tools."""
        async def _check():
            tools = await self.server.list_tools()
            names = [t.name for t in tools]
            self.assertIn("check_environment", names)
            self.assertIn("list_scenes", names)
            self.assertIn("run_simulation", names)
        asyncio.run(_check())

    def test_31_compare_experiments_heatmaps_disabled_handling(self):
        """Verify that when heatmap generation is disabled, neither artifact is reported."""
        mock_raw = _create_mock_raw_radio_map(ny=4, nx=5)

        async def _run():
            with patch("mcp_server.RadioMapEngine") as mock_engine_cls:
                mock_inst = MagicMock()
                mock_inst.backend = "llvm_ad_mono_polarized"
                mock_inst.last_bounds = (0.0, 50.0, 0.0, 32.0)
                mock_inst.run.return_value = mock_raw
                mock_engine_cls.return_value = mock_inst

                res_a = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 20.0})
                id_a = _extract_data(res_a)["experiment_id"]
                res_b = await self.server.call_tool("generate_radio_map", {"tx_power_dbm": 30.0})
                id_b = _extract_data(res_b)["experiment_id"]

                # 1. Test generate_heatmaps=False (plural)
                comp_res_1 = await self.server.call_tool(
                    "compare_experiments",
                    {"experiment_id_a": id_a, "experiment_id_b": id_b, "generate_heatmaps": False},
                )
                data_1 = _extract_data(comp_res_1)
                self.assertEqual(data_1["heatmaps"], {})
                self.assertEqual(data_1["artifacts"], {})
                self.assertNotIn("rss_diff_heatmap", data_1["heatmaps"])
                self.assertNotIn("path_gain_diff_heatmap", data_1["heatmaps"])
                self.assertFalse(data_1["heatmaps_available"]["rss_diff_heatmap"])
                self.assertFalse(data_1["heatmaps_available"]["path_gain_diff_heatmap"])

                # 2. Test generate_heatmap=False (singular alias)
                comp_res_2 = await self.server.call_tool(
                    "compare_experiments",
                    {"experiment_id_a": id_a, "experiment_id_b": id_b, "generate_heatmap": False},
                )
                data_2 = _extract_data(comp_res_2)
                self.assertEqual(data_2["heatmaps"], {})
                self.assertEqual(data_2["artifacts"], {})
                self.assertFalse(data_2["heatmaps_available"]["rss_diff_heatmap"])
                self.assertFalse(data_2["heatmaps_available"]["path_gain_diff_heatmap"])

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
