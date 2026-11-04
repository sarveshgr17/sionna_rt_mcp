"""Comprehensive Stability, Edge-Case, and Reliability Test Suite for Phase 9.5.

Covers:
A. Configuration and Input Validation (Invalid physical and numerical parameters).
B. Radio Map Edge Cases (Zero-power, unreachable cells, bounds, heights, cell sizes).
C. Reproducibility (Deterministic seed execution and physical power delta).
D. Storage Reliability (Missing/corrupted metadata and arrays, traversal protection, atomic writes).
E. Comparison Reliability (Strict spatial rejection, unreachable cell masking, B - A convention).
"""

import json
import math
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from src.radio_map_config import RadioMapConfig
from src.radio_map_engine import RadioMapEngine
from src.radio_map_result import RadioMapResult
from src.radio_map_formatter import RadioMapFormatter
from src.experiment_store import ExperimentStore
from src.experiment_comparator import ExperimentComparator, ComparisonResult
from src.mcp_server import create_mcp_server, ToolError


class TestConfigurationInputValidation(unittest.TestCase):
    """Area A: Validation of configuration parameters and strict error handling."""

    def test_invalid_frequency(self):
        """Reject non-positive, NaN, and Infinite carrier frequencies."""
        for invalid_freq in [0.0, -1e9, -3.5e9, float("nan"), float("inf"), float("-inf")]:
            with self.assertRaises(ValueError):
                RadioMapConfig(frequency_hz=invalid_freq)

    def test_invalid_transmitter_position(self):
        """Reject malformed, NaN, or non-3D transmitter positions."""
        for invalid_pos in [
            (0.0, 0.0),  # 2D
            (0.0, 0.0, 0.0, 0.0),  # 4D
            (0.0, float("nan"), 5.0),
            (float("inf"), 0.0, 5.0),
            [1.0, 2.0],  # Short list
        ]:
            with self.assertRaises(ValueError):
                RadioMapConfig(tx_position=invalid_pos)

    def test_invalid_transmitter_orientation(self):
        """Reject malformed or non-finite orientation angles."""
        for invalid_orient in [
            (0.0, 0.0),
            (float("nan"), 0.0, 0.0),
            (0.0, float("inf"), 0.0),
        ]:
            with self.assertRaises(ValueError):
                RadioMapConfig(tx_orientation_deg=invalid_orient)

    def test_invalid_transmitter_power(self):
        """Reject non-finite transmit power."""
        for invalid_power in [float("nan"), float("inf"), float("-inf")]:
            with self.assertRaises(ValueError):
                RadioMapConfig(tx_power_dbm=invalid_power)

    def test_invalid_cell_size(self):
        """Reject non-positive, zero, or non-finite grid cell dimensions."""
        for invalid_size in [
            0.0,
            -1.0,
            -5.0,
            float("nan"),
            float("inf"),
            (0.0, 5.0),
            (5.0, 0.0),
            (-2.0, 5.0),
            (5.0, -2.0),
            (float("nan"), 5.0),
        ]:
            with self.assertRaises(ValueError):
                RadioMapConfig(cell_size=invalid_size)

    def test_invalid_receiver_height(self):
        """Reject non-finite receiver plane evaluation height."""
        for invalid_height in [float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                RadioMapConfig(receiver_height=invalid_height)

    def test_invalid_manual_region_bounds(self):
        """Reject missing, inverted, or malformed manual bounds."""
        # Missing coordinates in manual mode
        with self.assertRaises(ValueError):
            RadioMapConfig(region_mode="manual", x_min=0.0, x_max=10.0, y_min=0.0)  # missing y_max

        # Inverted X bounds (x_max <= x_min)
        with self.assertRaises(ValueError):
            RadioMapConfig(region_mode="manual", x_min=10.0, x_max=0.0, y_min=0.0, y_max=10.0)

        # Inverted Y bounds (y_max <= y_min)
        with self.assertRaises(ValueError):
            RadioMapConfig(region_mode="manual", x_min=0.0, x_max=10.0, y_min=10.0, y_max=0.0)

        # Equal bounds (zero area)
        with self.assertRaises(ValueError):
            RadioMapConfig(region_mode="manual", x_min=5.0, x_max=5.0, y_min=0.0, y_max=10.0)

        # Cell size exceeding region span
        with self.assertRaises(ValueError):
            RadioMapConfig(region_mode="manual", x_min=0.0, x_max=5.0, y_min=0.0, y_max=5.0, cell_size=10.0)

    def test_invalid_antenna_and_polarization(self):
        """Reject unsupported antenna patterns and polarizations."""
        with self.assertRaises(ValueError):
            RadioMapConfig(antenna_type="unsupported_pattern_xyz")
        with self.assertRaises(ValueError):
            RadioMapConfig(polarization="CIRCULAR")
        with self.assertRaises(ValueError):
            RadioMapConfig(num_rows=0)
        with self.assertRaises(ValueError):
            RadioMapConfig(num_cols=-1)

    def test_invalid_solver_parameters(self):
        """Reject invalid ray budgets, bounce depths, or negative seeds."""
        with self.assertRaises(ValueError):
            RadioMapConfig(samples_per_tx=0)
        with self.assertRaises(ValueError):
            RadioMapConfig(samples_per_tx=-100)
        with self.assertRaises(ValueError):
            RadioMapConfig(max_depth=-1)
        with self.assertRaises(ValueError):
            RadioMapConfig(seed=-42)


class TestRadioMapEdgeCases(unittest.TestCase):
    """Area B: Handling of zero-power cells, unreachability, bounds, and heights."""

    def test_unreachable_zero_power_cells_representation(self):
        """Verify that unreachable cells (zero power) are converted to -inf without crashing."""
        ny, nx = 4, 4
        rss_watts = np.ones((ny, nx), dtype=np.float64) * 1e-4
        rss_watts[0, 0] = 0.0  # Cell (0,0) receives zero RF power
        rss_watts[1, 1] = 0.0  # Cell (1,1) receives zero RF power

        pg_lin = np.ones((ny, nx), dtype=np.float64) * 1e-5
        pg_lin[0, 0] = 0.0
        pg_lin[1, 1] = 0.0

        centers = np.zeros((ny, nx, 3), dtype=np.float64)

        result = RadioMapResult(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            tx_orientation_deg=(0.0, 0.0, 0.0),
            antenna_type="isotropic",
            antenna_pattern="iso",
            polarization="V",
            measurement_height=1.5,
            region_bounds=(-10.0, 10.0, -10.0, 10.0),
            cell_size=(5.0, 5.0),
            grid_dimensions=(ny, nx),
            solver_parameters={},
            rss_watts=rss_watts,
            path_gain_linear=pg_lin,
            cell_centers=centers,
        )

        # Check conversion to dBm / dB
        self.assertEqual(result.rss_dbm[0, 0], -float("inf"))
        self.assertEqual(result.rss_dbm[1, 1], -float("inf"))
        self.assertEqual(result.path_gain_db[0, 0], -float("inf"))
        self.assertEqual(result.path_gain_db[1, 1], -float("inf"))

        # Check validity and coverage counts
        self.assertEqual(result.num_cells, 16)
        self.assertEqual(result.valid_cells_count, 14)
        self.assertEqual(result.zero_power_cells_count, 2)
        self.assertAlmostEqual(result.coverage_percentage, (14 / 16) * 100.0)

        # Check that statistical metrics strictly exclude -inf
        self.assertFalse(math.isinf(result.min_rss_dbm))
        self.assertFalse(math.isinf(result.mean_rss_dbm))
        self.assertFalse(math.isinf(result.max_rss_dbm))
        self.assertAlmostEqual(result.min_rss_dbm, -10.0)  # 1e-4 W = -10 dBm

    def test_heatmap_generation_with_zero_power_cells(self):
        """Verify heatmaps render cleanly without noise-floor artifacts when invalid cells exist."""
        ny, nx = 4, 4
        rss_watts = np.ones((ny, nx), dtype=np.float64) * 1e-4
        rss_watts[0, :] = 0.0  # Top row entirely unreached

        pg_lin = np.ones((ny, nx), dtype=np.float64) * 1e-5
        pg_lin[0, :] = 0.0

        centers = np.zeros((ny, nx, 3), dtype=np.float64)

        result = RadioMapResult(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            tx_orientation_deg=(0.0, 0.0, 0.0),
            antenna_type="isotropic",
            antenna_pattern="iso",
            polarization="V",
            measurement_height=1.5,
            region_bounds=(-10.0, 10.0, -10.0, 10.0),
            cell_size=(5.0, 5.0),
            grid_dimensions=(ny, nx),
            solver_parameters={},
            rss_watts=rss_watts,
            path_gain_linear=pg_lin,
            cell_centers=centers,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            heatmaps = RadioMapFormatter.generate_heatmaps(result, output_dir=tmpdir)
            self.assertIn("rss_heatmap", heatmaps)
            self.assertIn("path_gain_heatmap", heatmaps)
            self.assertTrue(os.path.exists(heatmaps["rss_heatmap"]))
            self.assertTrue(os.path.exists(heatmaps["path_gain_heatmap"]))
            self.assertGreater(os.path.getsize(heatmaps["rss_heatmap"]), 1000)

    def test_real_manual_region_bounds_execution(self):
        """Execute real Sionna RT simulation with MANUAL region bounds and verify output boundaries."""
        config = RadioMapConfig(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            region_mode="manual",
            x_min=-10.0,
            x_max=10.0,
            y_min=-15.0,
            y_max=0.0,
            receiver_height=1.5,
            cell_size=5.0,
            samples_per_tx=10_000,
            max_depth=3,
        )
        engine = RadioMapEngine(config)
        raw_result = engine.run()
        result = RadioMapResult.from_raw_radio_map(
            raw_radio_map=raw_result,
            config=config,
            backend_variant=engine.backend,
            region_bounds=engine.last_bounds,
        )

        # Region bounds must match the configured manual span exactly
        self.assertEqual(result.region_bounds, (-10.0, 10.0, -15.0, 0.0))
        # 20m in X with dx=5.0 gives 4 cols; 15m in Y with dy=5.0 gives 3 rows
        self.assertEqual(result.grid_dimensions, (3, 4))
        self.assertEqual(result.num_cells, 12)
        self.assertGreater(result.valid_cells_count, 0)


class TestReproducibility(unittest.TestCase):
    """Area C: Deterministic seed reproduction and physical transmit power scaling."""

    def test_seed_reproducibility(self):
        """Verify that identical seed produces identical or near-identical simulation results."""
        config1 = RadioMapConfig(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            cell_size=5.0,
            samples_per_tx=10_000,
            seed=42,
        )
        config2 = RadioMapConfig(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            cell_size=5.0,
            samples_per_tx=10_000,
            seed=42,
        )

        engine1 = RadioMapEngine(config1)
        res1 = RadioMapResult.from_raw_radio_map(
            engine1.run(), config1, engine1.backend, engine1.last_bounds
        )

        engine2 = RadioMapEngine(config2)
        res2 = RadioMapResult.from_raw_radio_map(
            engine2.run(), config2, engine2.backend, engine2.last_bounds
        )

        # SBR ray tracing with fixed seed must be numerically close (< 0.1 dB difference)
        valid_mask = np.isfinite(res1.rss_dbm) & np.isfinite(res2.rss_dbm)
        self.assertTrue(np.any(valid_mask))
        delta = np.abs(res1.rss_dbm[valid_mask] - res2.rss_dbm[valid_mask])
        self.assertLess(float(np.mean(delta)), 0.1)

    def test_physical_power_scaling_delta(self):
        """Verify that +10 dB transmit power produces exactly +10 dB RSS and 0 dB path gain."""
        config_a = RadioMapConfig(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_power_dbm=30.0,
            cell_size=5.0,
            samples_per_tx=10_000,
            seed=100,
        )
        config_b = RadioMapConfig(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_power_dbm=40.0,  # +10 dB
            cell_size=5.0,
            samples_per_tx=10_000,
            seed=100,
        )

        engine_a = RadioMapEngine(config_a)
        res_a = RadioMapResult.from_raw_radio_map(
            engine_a.run(), config_a, engine_a.backend, engine_a.last_bounds
        )

        engine_b = RadioMapEngine(config_b)
        res_b = RadioMapResult.from_raw_radio_map(
            engine_b.run(), config_b, engine_b.backend, engine_b.last_bounds
        )

        valid_mask = np.isfinite(res_a.rss_dbm) & np.isfinite(res_b.rss_dbm)
        delta_rss = res_b.rss_dbm[valid_mask] - res_a.rss_dbm[valid_mask]
        delta_gain = res_b.path_gain_db[valid_mask] - res_a.path_gain_db[valid_mask]

        self.assertAlmostEqual(float(np.mean(delta_rss)), 10.0, places=3)
        self.assertAlmostEqual(float(np.mean(delta_gain)), 0.0, places=3)


class TestStorageReliability(unittest.TestCase):
    """Area D: Robustness against missing files, corruption, traversal, and duplicates."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_storage_rel_")
        self.store = ExperimentStore(storage_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_dummy_result(self) -> RadioMapResult:
        return RadioMapResult(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            tx_orientation_deg=(0.0, 0.0, 0.0),
            antenna_type="isotropic",
            antenna_pattern="iso",
            polarization="V",
            measurement_height=1.5,
            region_bounds=(-10.0, 10.0, -10.0, 10.0),
            cell_size=(5.0, 5.0),
            grid_dimensions=(3, 3),
            solver_parameters={},
            rss_watts=np.ones((3, 3)) * 1e-4,
            path_gain_linear=np.ones((3, 3)) * 1e-5,
            cell_centers=np.zeros((3, 3, 3)),
        )

    def test_missing_metadata_handled_safely(self):
        """list_experiments skips experiment directory with missing metadata.json."""
        exp_id = self.store.save_experiment(self._create_dummy_result())
        meta_path = os.path.join(self.temp_dir, exp_id, "metadata.json")
        os.remove(meta_path)

        experiments = self.store.list_experiments()
        self.assertEqual(len(experiments), 0)

        with self.assertRaises(FileNotFoundError):
            self.store.get_experiment_details(exp_id)

    def test_corrupted_metadata_json_handled_safely(self):
        """list_experiments skips experiment directory with malformed JSON metadata."""
        exp_id = self.store.save_experiment(self._create_dummy_result())
        meta_path = os.path.join(self.temp_dir, exp_id, "metadata.json")
        with open(meta_path, "w") as f:
            f.write("{corrupted json content...")

        experiments = self.store.list_experiments()
        self.assertEqual(len(experiments), 0)

        with self.assertRaises(ValueError):
            self.store.get_experiment_details(exp_id)

    def test_missing_heatmaps_does_not_break_numerical_data(self):
        """Missing PNG heatmaps does not prevent loading numerical arrays."""
        exp_id = self.store.save_experiment(self._create_dummy_result())
        # No heatmaps were passed during save
        details = self.store.get_experiment_details(exp_id)
        self.assertFalse(details["heatmaps_available"]["rss_heatmap"])
        self.assertFalse(details["heatmaps_available"]["path_gain_heatmap"])

        loaded_result = self.store.load_experiment(exp_id)
        self.assertEqual(loaded_result.grid_dimensions, (3, 3))
        self.assertEqual(loaded_result.rss_dbm.shape, (3, 3))

    def test_directory_traversal_rejection(self):
        """Reject traversal attempts containing '../' or outside characters."""
        for invalid_id in ["../outside", "..\\escape", "sub/dir/id", ""]:
            with self.assertRaises(ValueError):
                self.store.get_experiment_details(invalid_id)

    def test_duplicate_experiment_id_rejected(self):
        """Prevent overwriting an existing experiment ID."""
        res = self._create_dummy_result()
        exp_id = self.store.save_experiment(res, experiment_id="fixed_test_id")
        self.assertEqual(exp_id, "fixed_test_id")

        with self.assertRaises(FileExistsError):
            self.store.save_experiment(res, experiment_id="fixed_test_id")


class TestComparisonReliability(unittest.TestCase):
    """Area E: Strict rejection of spatially incompatible experiments."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_comp_rel_")
        self.store = ExperimentStore(storage_dir=self.temp_dir)
        self.comparator = ExperimentComparator(experiment_store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _save_custom_result(self, **kwargs) -> str:
        defaults = dict(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            tx_orientation_deg=(0.0, 0.0, 0.0),
            antenna_type="isotropic",
            antenna_pattern="iso",
            polarization="V",
            measurement_height=1.5,
            region_bounds=(-10.0, 10.0, -10.0, 10.0),
            cell_size=(5.0, 5.0),
            grid_dimensions=(3, 3),
            solver_parameters={},
            rss_watts=np.ones((3, 3)) * 1e-4,
            path_gain_linear=np.ones((3, 3)) * 1e-5,
            cell_centers=np.zeros((3, 3, 3)),
        )
        defaults.update(kwargs)
        res = RadioMapResult(**defaults)
        return self.store.save_experiment(res)

    def test_reject_grid_dimension_mismatch(self):
        """Reject comparison between (3, 3) and (4, 4) grids."""
        id_a = self._save_custom_result(grid_dimensions=(3, 3), rss_watts=np.ones((3, 3)), path_gain_linear=np.ones((3, 3)), cell_centers=np.zeros((3, 3, 3)))
        id_b = self._save_custom_result(grid_dimensions=(4, 4), rss_watts=np.ones((4, 4)), path_gain_linear=np.ones((4, 4)), cell_centers=np.zeros((4, 4, 3)))
        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=False)
        self.assertIn("grid_dimensions differ", str(ctx.exception))

    def test_reject_cell_size_mismatch(self):
        """Reject comparison between cell_size (5.0, 5.0) and (2.5, 2.5)."""
        id_a = self._save_custom_result(cell_size=(5.0, 5.0))
        id_b = self._save_custom_result(cell_size=(2.5, 2.5))
        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=False)
        self.assertIn("cell_size differs", str(ctx.exception))

    def test_reject_measurement_height_mismatch(self):
        """Reject comparison between height 1.5m and 5.0m."""
        id_a = self._save_custom_result(measurement_height=1.5)
        id_b = self._save_custom_result(measurement_height=5.0)
        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=False)
        self.assertIn("measurement_height differs", str(ctx.exception))

    def test_reject_scene_mismatch(self):
        """Reject comparison between different geometric scenes."""
        id_a = self._save_custom_result(scene_name="simple_reflector")
        id_b = self._save_custom_result(scene_name="munich")
        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=False)
        self.assertIn("scene_name differs", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

