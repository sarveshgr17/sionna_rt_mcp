"""End-to-End Runtime and Deployment Readiness Verification Tests (Phase 8).

This module contains end-to-end integration and runtime verification tests for:
1. Complete experiment lifecycle: saving, metadata verification, array verification,
   independent multi-experiment isolation, and retrieval.
2. Experiment comparison and spatial difference analysis with manual numerical spot-checks.
3. Disabled heatmap behavior and artifact integrity.
4. Spatial incompatibility rejection.
5. Deployment security: path traversal protection and corrupted metadata handling.
6. Point-to-point tool regression verification and graceful fallback behavior.
7. Non-finite floating-point JSON serialization safeguards.
"""

import asyncio
import copy
import json
import math
import os
import shutil
import sys
import tempfile
from typing import Any, Dict, Tuple
import unittest

# Ensure repository root and src directory are on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_dir = os.path.join(_repo_root, "src")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import numpy as np

from radio_map_config import RadioMapConfig
from radio_map_result import RadioMapResult
from radio_map_formatter import RadioMapFormatter
from experiment_store import ExperimentStore
from experiment_comparator import ExperimentComparator, ComparisonResult
from mcp_server import ToolError, create_mcp_server


def _build_synthetic_radio_map_result(
    scene_name: str = "simple_reflector",
    frequency_hz: float = 3.5e9,
    tx_position: Tuple[float, float, float] = (0.0, -10.0, 5.0),
    tx_power_dbm: float = 30.0,
    ny: int = 10,
    nx: int = 10,
    cell_size: float = 1.0,
    height: float = 1.5,
    include_shadow: bool = True,
) -> RadioMapResult:
    """Build a realistic synthetic RadioMapResult for end-to-end testing."""
    x_coords = np.linspace(-float(nx) / 2.0 + 0.5, float(nx) / 2.0 - 0.5, nx) * cell_size
    y_coords = np.linspace(-float(ny) / 2.0 + 0.5, float(ny) / 2.0 - 0.5, ny) * cell_size

    xx, yy = np.meshgrid(x_coords, y_coords)
    zz = np.full_like(xx, height)
    cell_centers = np.stack([xx, yy, zz], axis=-1)

    # Calculate distance from TX to cell centers
    dx = xx - tx_position[0]
    dy = yy - tx_position[1]
    dz = zz - tx_position[2]
    dist = np.sqrt(dx**2 + dy**2 + dz**2)

    # Free-space path gain model: g = (c / (4 * pi * f * d))^2
    c = 299792458.0
    wavelength = c / frequency_hz
    path_gain_linear = (wavelength / (4.0 * np.pi * dist)) ** 2

    # Received power in Watts: P_rx = P_tx_watts * g
    tx_power_watts = 10.0 ** ((tx_power_dbm - 30.0) / 10.0)
    rss_watts = tx_power_watts * path_gain_linear

    # Add shadow region with zero power / zero gain if requested
    if include_shadow:
        path_gain_linear[0:2, 0:2] = 0.0
        rss_watts[0:2, 0:2] = 0.0

    # Convert to dB / dBm
    path_gain_db = np.full((ny, nx), -np.inf, dtype=np.float64)
    rss_dbm = np.full((ny, nx), -np.inf, dtype=np.float64)

    valid_mask = path_gain_linear > 0.0
    with np.errstate(divide="ignore"):
        path_gain_db[valid_mask] = 10.0 * np.log10(path_gain_linear[valid_mask])
        rss_dbm[valid_mask] = 10.0 * np.log10(rss_watts[valid_mask]) + 30.0

    x_min = float(np.min(x_coords)) - cell_size / 2.0
    x_max = float(np.max(x_coords)) + cell_size / 2.0
    y_min = float(np.min(y_coords)) - cell_size / 2.0
    y_max = float(np.max(y_coords)) + cell_size / 2.0

    return RadioMapResult(
        scene_name=scene_name,
        frequency_hz=frequency_hz,
        tx_position=tx_position,
        tx_power_dbm=tx_power_dbm,
        tx_orientation_deg=(0.0, 0.0, 0.0),
        antenna_type="isotropic",
        antenna_pattern="iso",
        polarization="V",
        measurement_height=height,
        region_bounds=(x_min, x_max, y_min, y_max),
        cell_size=(cell_size, cell_size),
        grid_dimensions=(ny, nx),
        solver_parameters={"samples_per_tx": 100000, "max_depth": 3},
        backend_variant="llvm_ad_mono_polarized",
        path_gain_linear=path_gain_linear,
        path_gain_db=path_gain_db,
        rss_watts=rss_watts,
        rss_dbm=rss_dbm,
        cell_centers=cell_centers,
        x_coordinates=x_coords,
        y_coordinates=y_coords,
    )


class TestPhase8EndToEnd(unittest.TestCase):
    """End-to-end verification tests covering full radio-map lifecycles and deployment checks."""

    def setUp(self):
        """Create an isolated temporary storage directory for every test."""
        self.test_dir = tempfile.mkdtemp(prefix="sionna_test_p8_")
        self.store = ExperimentStore(storage_dir=self.test_dir)
        self.comparator = ExperimentComparator(experiment_store=self.store)

    def tearDown(self):
        """Clean up temporary test directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # =========================================================================
    # Step 3: Complete Experiment Lifecycle Test
    # =========================================================================

    def test_e2e_experiment_lifecycle_full_workflow(self):
        """Verify complete end-to-end experiment lifecycle (save, inspect, load, multi-experiment isolation)."""
        # 1. Build Experiment A (Baseline: 30 dBm)
        result_a = _build_synthetic_radio_map_result(tx_power_dbm=30.0, ny=8, nx=8)

        # Generate real heatmaps using RadioMapFormatter
        temp_plot_dir = tempfile.mkdtemp(prefix="p8_plots_")
        try:
            heatmaps_a = RadioMapFormatter.generate_heatmaps(result_a, temp_plot_dir)

            id_a = self.store.save_experiment(
                result=result_a,
                heatmap_paths=heatmaps_a,
                experiment_name="baseline_30dbm",
            )
            meta_a = self.store.get_experiment_details(id_a)
        finally:
            shutil.rmtree(temp_plot_dir, ignore_errors=True)

        # Verify Experiment A artifacts on disk
        exp_a_dir = os.path.join(self.test_dir, id_a)
        self.assertTrue(os.path.isdir(exp_a_dir))
        self.assertTrue(os.path.isfile(os.path.join(exp_a_dir, "metadata.json")))
        self.assertTrue(os.path.isfile(os.path.join(exp_a_dir, "radio_map_data.npz")))
        self.assertTrue(os.path.isfile(os.path.join(exp_a_dir, "rss_heatmap.png")))
        self.assertTrue(os.path.isfile(os.path.join(exp_a_dir, "path_gain_heatmap.png")))

        # Verify PNG file headers
        with open(os.path.join(exp_a_dir, "rss_heatmap.png"), "rb") as f:
            header = f.read(8)
            self.assertEqual(header, b"\x89PNG\r\n\x1a\n")

        # Verify NPZ array contents
        with np.load(os.path.join(exp_a_dir, "radio_map_data.npz")) as data:
            self.assertIn("rss_dbm", data)
            self.assertIn("path_gain_db", data)
            self.assertIn("cell_centers", data)
            self.assertIn("x_coordinates", data)
            self.assertIn("y_coordinates", data)
            self.assertEqual(data["rss_dbm"].shape, (8, 8))

        # Snapshot Experiment A metadata for isolation check
        snapshot_meta_a = copy.deepcopy(meta_a)

        # 2. Build Experiment B (Modified: 40 dBm, +10 dB power)
        result_b = _build_synthetic_radio_map_result(tx_power_dbm=40.0, ny=8, nx=8)
        id_b = self.store.save_experiment(
            result=result_b,
            experiment_name="boosted_40dbm",
        )

        # Verify unique IDs
        self.assertNotEqual(id_a, id_b)

        # 3. Verify Experiment Retrieval via list_experiments
        catalog = self.store.list_experiments()
        self.assertEqual(len(catalog), 2)
        exp_ids = [e["experiment_id"] for e in catalog]
        self.assertIn(id_a, exp_ids)
        self.assertIn(id_b, exp_ids)

        # 4. Verify Experiment Retrieval via get_experiment_details
        details_a = self.store.get_experiment_details(id_a)
        details_b = self.store.get_experiment_details(id_b)
        self.assertEqual(details_a["tx_power_dbm"], 30.0)
        self.assertEqual(details_b["tx_power_dbm"], 40.0)
        self.assertEqual(details_a["experiment_name"], "baseline_30dbm")
        self.assertEqual(details_b["experiment_name"], "boosted_40dbm")

        # 5. Verify Numerical Array Loading via load_experiment
        loaded_a = self.store.load_experiment(id_a)
        self.assertIsInstance(loaded_a, RadioMapResult)
        np.testing.assert_allclose(loaded_a.rss_dbm, result_a.rss_dbm, rtol=1e-5)
        np.testing.assert_allclose(loaded_a.path_gain_db, result_a.path_gain_db, rtol=1e-5)

        # 6. Verify Isolation: Experiment A is completely unmodified
        details_a_post = self.store.get_experiment_details(id_a)
        self.assertEqual(snapshot_meta_a["experiment_id"], details_a_post["experiment_id"])
        self.assertEqual(snapshot_meta_a["created_at"], details_a_post["created_at"])
        self.assertEqual(snapshot_meta_a["tx_power_dbm"], details_a_post["tx_power_dbm"])

    # =========================================================================
    # Step 4: Real Experiment Comparison & Numerical Spot-Checks
    # =========================================================================

    def test_e2e_comparison_numerical_spot_check(self):
        """Perform end-to-end experiment comparison with explicit numerical spot-checks."""
        # Baseline A (30 dBm) and Modified B (40 dBm = +10 dB higher power)
        result_a = _build_synthetic_radio_map_result(tx_power_dbm=30.0, ny=6, nx=6, include_shadow=True)
        result_b = _build_synthetic_radio_map_result(tx_power_dbm=40.0, ny=6, nx=6, include_shadow=True)

        id_a = self.store.save_experiment(result_a, experiment_name="exp_A")
        id_b = self.store.save_experiment(result_b, experiment_name="exp_B")

        # Run comparison with heatmaps enabled
        comp = self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=True)
        self.assertIsInstance(comp, ComparisonResult)
        self.assertEqual(comp.difference_convention, "B - A (Experiment B minus Experiment A)")

        # 1. Spot-check finite cells: delta_rss should be exactly +10.0 dB (B - A)
        # Check cell (3, 3)
        expected_diff_rss = result_b.rss_dbm[3, 3] - result_a.rss_dbm[3, 3]
        self.assertAlmostEqual(expected_diff_rss, 10.0, places=4)
        self.assertAlmostEqual(comp.delta_rss_dbm[3, 3], 10.0, places=4)

        # Check cell (4, 5)
        expected_diff_gain = result_b.path_gain_db[4, 5] - result_a.path_gain_db[4, 5]
        self.assertAlmostEqual(expected_diff_gain, 0.0, places=4)
        self.assertAlmostEqual(comp.delta_path_gain_db[4, 5], 0.0, places=4)

        # 2. Spot-check invalid / shadow cells (0, 0): must be masked as NaN
        self.assertTrue(np.isnan(comp.delta_rss_dbm[0, 0]))
        self.assertTrue(np.isnan(comp.delta_path_gain_db[0, 0]))
        self.assertFalse(comp.valid_mask[0, 0])

        # 3. Check statistical metrics
        rss_metrics = comp.rss_metrics
        self.assertEqual(rss_metrics["total_cells"], 36)
        self.assertEqual(rss_metrics["invalid_cells"], 4)  # 2x2 shadow corner
        self.assertEqual(rss_metrics["valid_cells"], 32)
        self.assertAlmostEqual(rss_metrics["mean_difference"], 10.0, places=4)
        self.assertEqual(rss_metrics["b_stronger_cells"], 32)
        self.assertEqual(rss_metrics["b_weaker_cells"], 0)
        self.assertEqual(rss_metrics["equal_cells"], 0)

        # Path gain difference metrics: identical geometry, so all valid cells are equal
        gain_metrics = comp.path_gain_metrics
        self.assertEqual(gain_metrics["equal_cells"], 32)
        self.assertAlmostEqual(gain_metrics["mean_difference"], 0.0, places=4)

        # 4. Check generated heatmaps on disk
        self.assertIn("rss_diff_heatmap", comp.heatmap_paths)
        self.assertIn("path_gain_diff_heatmap", comp.heatmap_paths)
        self.assertTrue(os.path.isfile(comp.heatmap_paths["rss_diff_heatmap"]))
        self.assertTrue(os.path.isfile(comp.heatmap_paths["path_gain_diff_heatmap"]))

    def test_e2e_comparison_disabled_heatmaps_creates_no_artifacts(self):
        """Verify that generate_heatmaps=False generates no PNG files and returns empty paths."""
        result_a = _build_synthetic_radio_map_result(tx_power_dbm=30.0, ny=4, nx=4)
        result_b = _build_synthetic_radio_map_result(tx_power_dbm=35.0, ny=4, nx=4)

        id_a = self.store.save_experiment(result_a)
        id_b = self.store.save_experiment(result_b)

        comp = self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=False)
        self.assertEqual(comp.heatmap_paths, {})
        self.assertFalse(comp.heatmaps_available.get("rss_diff_heatmap", False))
        self.assertFalse(comp.heatmaps_available.get("path_gain_diff_heatmap", False))

        # Confirm no PNG files created in comparator output directory
        if os.path.exists(self.comparator.output_dir):
            files = [f for f in os.listdir(self.comparator.output_dir) if f.endswith(".png")]
            self.assertEqual(len(files), 0)

    def test_e2e_comparison_spatial_mismatch_rejection(self):
        """Verify that incompatible spatial grids are rejected with informative errors."""
        res_a = _build_synthetic_radio_map_result(scene_name="scene_alpha", cell_size=1.0)
        res_b = _build_synthetic_radio_map_result(scene_name="scene_beta", cell_size=1.0)
        res_c = _build_synthetic_radio_map_result(scene_name="scene_alpha", cell_size=2.0)

        id_a = self.store.save_experiment(res_a)
        id_b = self.store.save_experiment(res_b)
        id_c = self.store.save_experiment(res_c)

        # Different scenes
        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(id_a, id_b)
        self.assertIn("scene_name differs", str(ctx.exception))

        # Different cell sizes
        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(id_a, id_c)
        self.assertIn("cell_size differs", str(ctx.exception))

    # =========================================================================
    # Step 7: Deployment-Readiness & Security Safeguards
    # =========================================================================

    def test_e2e_path_traversal_protection(self):
        """Verify that malicious experiment IDs attempting directory traversal are rejected."""
        traversal_attempts = [
            "../secret",
            "..\\windows\\system32",
            "../../etc/passwd",
            "sub/folder",
            "foo/bar",
            "foo\\bar",
            "exp\0null",
            ".",
            "..",
        ]
        for bad_id in traversal_attempts:
            with self.assertRaises(ValueError, msg=f"Failed to reject: {bad_id!r}"):
                self.store.get_experiment_details(bad_id)
            with self.assertRaises(ValueError, msg=f"Failed to reject: {bad_id!r}"):
                self.store.load_experiment(bad_id)

    def test_e2e_corrupted_metadata_handling(self):
        """Verify that corrupt or truncated metadata JSON raises informative ValueError."""
        # Create a valid experiment first
        res = _build_synthetic_radio_map_result(ny=4, nx=4)
        exp_id = self.store.save_experiment(res)

        # Corrupt the metadata file
        meta_file = os.path.join(self.test_dir, exp_id, "metadata.json")
        with open(meta_file, "w") as f:
            f.write("{ invalid json syntax ...")

        with self.assertRaises(ValueError) as ctx:
            self.store.get_experiment_details(exp_id)
        self.assertIn("Corrupted or invalid metadata JSON", str(ctx.exception))

    def test_e2e_json_serialization_of_non_finite_values(self):
        """Verify that non-finite floats (-inf, inf, nan) in comparison arrays serialize cleanly to JSON null."""
        # Baseline with shadow region producing -inf in raw arrays and NaNs in difference arrays
        res_a = _build_synthetic_radio_map_result(tx_power_dbm=30.0, ny=4, nx=4, include_shadow=True)
        res_b = _build_synthetic_radio_map_result(tx_power_dbm=35.0, ny=4, nx=4, include_shadow=True)

        id_a = self.store.save_experiment(res_a)
        id_b = self.store.save_experiment(res_b)

        comp = self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=False)
        payload = comp.to_dict(include_full_arrays=True)

        # Confirm payload contains None instead of NaN in difference matrices
        delta_rss = payload["delta_rss_dbm"]
        self.assertIsNone(delta_rss[0][0])  # Unreachable cell

        # Standard Python json.dumps without error
        json_str = json.dumps(payload)
        self.assertIsInstance(json_str, str)
        self.assertNotIn("NaN", json_str)
        self.assertNotIn("Infinity", json_str)
        self.assertIn("null", json_str)

        # Roundtrip parse
        parsed = json.loads(json_str)
        self.assertIsNone(parsed["delta_rss_dbm"][0][0])
        self.assertAlmostEqual(parsed["delta_rss_dbm"][3][3], 5.0, places=4)

    # =========================================================================
    # Step 6: Point-to-Point Regression Verification
    # =========================================================================

    def test_e2e_point_to_point_mcp_tools_operational(self):
        """Verify that existing point-to-point tools execute and report environment health correctly."""
        server = create_mcp_server()

        async def _run():
            def _extract(res):
                if isinstance(res, tuple):
                    if len(res) > 1 and isinstance(res[1], dict):
                        return res[1].get("result", res[1])
                    return json.loads(res[0][0].text)
                if hasattr(res, "structured_content") and res.structured_content:
                    return res.structured_content.get("result", res.structured_content)
                return json.loads(res.content[0].text)

            # check_environment
            env_res = await server.call_tool("check_environment", {})
            data = _extract(env_res)

            self.assertIn("python_version", data)
            self.assertIn("sionna_version", data)
            self.assertIn("mitsuba_version", data)
            self.assertIn("backend", data)
            self.assertIn("is_usable", data)
            self.assertIsInstance(data["is_usable"], bool)

            # list_scenes
            scenes_res = await server.call_tool("list_scenes", {})
            scenes_data = _extract(scenes_res)

            self.assertEqual(scenes_data["default_scene"], "simple_reflector")
            scenes_names = [s["name"] for s in scenes_data["scenes"]]
            self.assertIn("simple_reflector", scenes_names)

            # run_simulation parameter validation
            with self.assertRaises(ToolError):
                await server.call_tool(
                    "run_simulation",
                    {
                        "scene": "simple_reflector",
                        "frequency_hz": -1.0,  # Invalid frequency
                        "tx_position": [0.0, -10.0, 5.0],
                        "rx_position": [0.0, 10.0, 5.0],
                    },
                )

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
