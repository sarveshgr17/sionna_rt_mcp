"""Unit tests for ExperimentComparator (Phase 6).

Covers all 30 required specifications:
1. Compare two compatible experiments.
2. Verify RSS difference uses B minus A.
3. Verify path-gain difference uses B minus A.
4. Verify positive values mean B is stronger.
5. Verify negative values mean B is weaker.
6. Verify equal values produce zero difference.
7. Verify both-unreachable cells are invalid.
8. Verify one-sided unreachable cells are invalid.
9. Verify no invalid cell is converted to an artificial noise floor.
10. Verify summary metrics use valid cells only.
11. Verify no-valid-cell behavior.
12. Reject different scene names.
13. Reject different measurement heights.
14. Reject different grid dimensions.
15. Reject different cell sizes.
16. Reject different region bounds.
17. Reject misaligned cell centers.
18. Reject incompatible coordinate arrays.
19. Verify floating-point coordinate tolerance.
20. Verify different TX powers are allowed.
21. Verify different TX positions are allowed.
22. Verify different antenna configurations are allowed.
23. Preserve and report frequency differences.
24. Generate RSS difference heatmap.
25. Generate path-gain difference heatmap.
26. Verify invalid cells are masked.
27. Verify heatmap generation gracefully handles missing Matplotlib.
28. Verify original saved experiment arrays remain unchanged.
29. Handle nonexistent experiment IDs.
30. Verify comparison metadata and result structure.
Plus supplementary tests for 2D non-separable coordinates and equality tolerance.
"""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

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
    from experiment_store import ExperimentStore
except (ImportError, ModuleNotFoundError):
    from src.experiment_store import ExperimentStore

try:
    from radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from src.radio_map_result import RadioMapResult

try:
    from experiment_comparator import (
        DEFAULT_COORDINATE_TOLERANCE,
        DEFAULT_EQUALITY_TOLERANCE_DB,
        ComparisonResult,
        ExperimentComparator,
    )
except (ImportError, ModuleNotFoundError):
    from src.experiment_comparator import (
        DEFAULT_COORDINATE_TOLERANCE,
        DEFAULT_EQUALITY_TOLERANCE_DB,
        ComparisonResult,
        ExperimentComparator,
    )


def _create_synthetic_result(
    scene_name: str = "munich",
    freq_hz: float = 3.5e9,
    measurement_height: float = 1.5,
    ny: int = 4,
    nx: int = 5,
    dx: float = 10.0,
    dy: float = 8.0,
    tx_position: tuple = (15.0, 20.0, 25.0),
    tx_power_dbm: float = 30.0,
    antenna_type: str = "directional",
    antenna_pattern: str = "tr38901",
    polarization: str = "V",
    separable: bool = True,
    gain_linear_matrix: "np.ndarray | None" = None,
    power_offset_dbm: float = 0.0,
) -> RadioMapResult:
    """Helper to generate a deterministic synthetic RadioMapResult instance."""
    if np is None:
        raise RuntimeError("NumPy is required to create synthetic RadioMapResult.")

    if gain_linear_matrix is not None:
        gain_lin = np.array(gain_linear_matrix, dtype=np.float64)
    else:
        gain_lin = np.zeros((ny, nx), dtype=np.float64)
        for r in range(ny):
            for c in range(nx):
                # Cells where (r + c) is divisible by 4 are unreachable (0 power)
                if (r + c) % 4 != 0:
                    gain_lin[r, c] = 1e-6 * (r * nx + c + 1)

    effective_tx_power_dbm = tx_power_dbm + power_offset_dbm
    tx_power_watts = 10.0 ** ((effective_tx_power_dbm - 30.0) / 10.0)
    rss_watts = gain_lin * tx_power_watts

    path_gain_db = np.full((ny, nx), -np.inf, dtype=np.float64)
    pos_gain = gain_lin > 0.0
    with np.errstate(divide="ignore"):
        path_gain_db[pos_gain] = 10.0 * np.log10(gain_lin[pos_gain])

    rss_dbm = np.full((ny, nx), -np.inf, dtype=np.float64)
    pos_rss = rss_watts > 0.0
    with np.errstate(divide="ignore"):
        rss_dbm[pos_rss] = 10.0 * np.log10(rss_watts[pos_rss]) + 30.0

    cell_centers = np.zeros((ny, nx, 3), dtype=np.float64)
    for r in range(ny):
        for c in range(nx):
            cell_centers[r, c] = [c * dx + dx / 2.0, r * dy + dy / 2.0, measurement_height]

    if separable:
        x_coords = np.array([c * dx + dx / 2.0 for c in range(nx)], dtype=np.float64)
        y_coords = np.array([r * dy + dy / 2.0 for r in range(ny)], dtype=np.float64)
    else:
        x_coords = cell_centers[:, :, 0]
        y_coords = cell_centers[:, :, 1]

    return RadioMapResult(
        scene_name=scene_name,
        frequency_hz=freq_hz,
        tx_position=tx_position,
        tx_power_dbm=effective_tx_power_dbm,
        tx_orientation_deg=(0.0, 0.0, 0.0),
        antenna_type=antenna_type,
        antenna_pattern=antenna_pattern,
        polarization=polarization,
        measurement_height=measurement_height,
        region_bounds=(0.0, float(nx * dx), 0.0, float(ny * dy)),
        cell_size=(float(dx), float(dy)),
        grid_dimensions=(ny, nx),
        solver_parameters={"samples_per_tx": 100000, "max_depth": 3, "seed": 42},
        simulation_timestamp="2026-11-01T12:00:00+00:00",
        backend_variant="llvm",
        path_gain_linear=gain_lin,
        path_gain_db=path_gain_db,
        rss_watts=rss_watts,
        rss_dbm=rss_dbm,
        cell_centers=cell_centers,
        x_coordinates=x_coords,
        y_coordinates=y_coords,
    )


class TestExperimentComparator(unittest.TestCase):
    """Unit tests for ExperimentComparator spatial difference calculations and validations."""

    def setUp(self):
        """Set up temporary directories and initialized ExperimentStore and ExperimentComparator."""
        if np is None:
            self.skipTest("NumPy is required for ExperimentComparator tests.")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = os.path.join(self.temp_dir.name, "store")
        self.output_dir = os.path.join(self.temp_dir.name, "diff_heatmaps")
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        self.store = ExperimentStore(storage_dir=self.storage_dir)
        self.comparator = ExperimentComparator(
            experiment_store=self.store,
            output_dir=self.output_dir,
        )

        # Baseline Experiment A
        self.res_a = _create_synthetic_result(power_offset_dbm=0.0)
        self.exp_a_id = self.store.save_experiment(self.res_a, experiment_name="baseline_A")

        # Modified Experiment B (+6 dB power boost)
        self.res_b = _create_synthetic_result(power_offset_dbm=6.0)
        self.exp_b_id = self.store.save_experiment(self.res_b, experiment_name="boosted_B")

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # Test 1: Compare two compatible experiments
    # -------------------------------------------------------------------------
    def test_01_compare_two_compatible_experiments(self):
        """Verify comparing two compatible experiments succeeds and returns ComparisonResult."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=False)
        self.assertIsInstance(comp, ComparisonResult)
        self.assertEqual(comp.experiment_a_id, self.exp_a_id)
        self.assertEqual(comp.experiment_b_id, self.exp_b_id)
        self.assertEqual(comp.scene_name, self.res_a.scene_name)
        self.assertEqual(comp.difference_convention, "B - A (Experiment B minus Experiment A)")

    # -------------------------------------------------------------------------
    # Test 2: Verify RSS difference uses B minus A
    # -------------------------------------------------------------------------
    def test_02_verify_rss_difference_b_minus_a(self):
        """Verify delta_rss_dbm is strictly calculated as rss_dbm_B - rss_dbm_A."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=False)
        valid_indices = np.where(comp.valid_mask)
        self.assertTrue(len(valid_indices[0]) > 0)

        for r, c in zip(valid_indices[0], valid_indices[1]):
            expected = self.res_b.rss_dbm[r, c] - self.res_a.rss_dbm[r, c]
            self.assertAlmostEqual(comp.delta_rss_dbm[r, c], expected, places=5)
            # Since Exp B has +6 dB offset, expected difference is +6 dB
            self.assertAlmostEqual(comp.delta_rss_dbm[r, c], 6.0, places=4)

    # -------------------------------------------------------------------------
    # Test 3: Verify path-gain difference uses B minus A
    # -------------------------------------------------------------------------
    def test_03_verify_path_gain_difference_b_minus_a(self):
        """Verify delta_path_gain_db is strictly calculated as path_gain_db_B - path_gain_db_A."""
        # Baseline and modified with different path gains
        ny, nx = 4, 5
        gain_a = np.ones((ny, nx)) * 1e-5
        gain_b = np.ones((ny, nx)) * 1e-4  # +10 dB gain

        res_a = _create_synthetic_result(gain_linear_matrix=gain_a)
        res_b = _create_synthetic_result(gain_linear_matrix=gain_b)
        id_a = self.store.save_experiment(res_a)
        id_b = self.store.save_experiment(res_b)

        comp = self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=False)
        self.assertTrue(np.all(comp.valid_mask))
        self.assertTrue(np.allclose(comp.delta_path_gain_db, 10.0, atol=1e-4))

    # -------------------------------------------------------------------------
    # Test 4: Verify positive values mean B is stronger
    # -------------------------------------------------------------------------
    def test_04_verify_positive_values_mean_b_is_stronger(self):
        """Verify positive difference values indicate Experiment B has higher received power."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=False)
        self.assertTrue(np.all(comp.delta_rss_dbm[comp.valid_mask] > 0))
        self.assertEqual(comp.rss_metrics["b_stronger_cells"], comp.rss_metrics["valid_cells"])
        self.assertEqual(comp.rss_metrics["b_weaker_cells"], 0)

    # -------------------------------------------------------------------------
    # Test 5: Verify negative values mean B is weaker
    # -------------------------------------------------------------------------
    def test_05_verify_negative_values_mean_b_is_weaker(self):
        """Verify negative difference values indicate Experiment B has lower received power."""
        # Reverse order: compare B as baseline and A as new (A is weaker than B)
        comp = self.comparator.compare_experiments(self.exp_b_id, self.exp_a_id, generate_heatmaps=False)
        self.assertTrue(np.all(comp.delta_rss_dbm[comp.valid_mask] < 0))
        self.assertEqual(comp.rss_metrics["b_weaker_cells"], comp.rss_metrics["valid_cells"])
        self.assertEqual(comp.rss_metrics["b_stronger_cells"], 0)
        self.assertAlmostEqual(comp.rss_metrics["mean_difference"], -6.0, places=4)

    # -------------------------------------------------------------------------
    # Test 6: Verify equal values produce zero difference
    # -------------------------------------------------------------------------
    def test_06_verify_equal_values_produce_zero_difference(self):
        """Verify identical experiments evaluate to 0.0 dB difference and count as equal."""
        # Save identical copy
        id_a_copy = self.store.save_experiment(self.res_a, experiment_name="identical_copy")
        comp = self.comparator.compare_experiments(self.exp_a_id, id_a_copy, generate_heatmaps=False)

        valid_vals = comp.delta_rss_dbm[comp.valid_mask]
        self.assertTrue(np.allclose(valid_vals, 0.0, atol=1e-6))
        self.assertEqual(comp.rss_metrics["equal_cells"], comp.rss_metrics["valid_cells"])
        self.assertEqual(comp.rss_metrics["b_stronger_cells"], 0)
        self.assertEqual(comp.rss_metrics["b_weaker_cells"], 0)

    # -------------------------------------------------------------------------
    # Test 7: Verify both-unreachable cells are invalid
    # -------------------------------------------------------------------------
    def test_07_verify_both_unreachable_cells_are_invalid(self):
        """Verify cells where BOTH experiments receive zero power (-inf) are marked invalid (NaN)."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=False)
        both_zero_mask = (self.res_a.rss_watts == 0.0) & (self.res_b.rss_watts == 0.0)
        self.assertTrue(np.any(both_zero_mask))

        # Check valid_mask is False and delta is NaN
        self.assertFalse(np.any(comp.valid_mask[both_zero_mask]))
        self.assertTrue(np.all(np.isnan(comp.delta_rss_dbm[both_zero_mask])))
        self.assertTrue(np.all(np.isnan(comp.delta_path_gain_db[both_zero_mask])))

    # -------------------------------------------------------------------------
    # Test 8: Verify one-sided unreachable cells are invalid
    # -------------------------------------------------------------------------
    def test_08_verify_one_sided_unreachable_cells_are_invalid(self):
        """Verify cells where only ONE experiment receives zero power are marked invalid (NaN)."""
        ny, nx = 4, 5
        gain_a = np.ones((ny, nx)) * 1e-5
        gain_b = np.ones((ny, nx)) * 1e-5
        gain_a[0, 0] = 0.0  # Zero only in A
        gain_b[0, 1] = 0.0  # Zero only in B

        res_a = _create_synthetic_result(gain_linear_matrix=gain_a)
        res_b = _create_synthetic_result(gain_linear_matrix=gain_b)
        id_a = self.store.save_experiment(res_a)
        id_b = self.store.save_experiment(res_b)

        comp = self.comparator.compare_experiments(id_a, id_b, generate_heatmaps=False)
        self.assertFalse(comp.valid_mask[0, 0])
        self.assertFalse(comp.valid_mask[0, 1])
        self.assertTrue(np.isnan(comp.delta_rss_dbm[0, 0]))
        self.assertTrue(np.isnan(comp.delta_rss_dbm[0, 1]))

    # -------------------------------------------------------------------------
    # Test 9: Verify no invalid cell is converted to an artificial noise floor
    # -------------------------------------------------------------------------
    def test_09_verify_no_invalid_cell_converted_to_noise_floor(self):
        """Verify invalid cells are strictly NaN and not replaced with artificial noise floor."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=False)
        invalid_mask = ~comp.valid_mask
        self.assertTrue(np.any(invalid_mask))

        # Check that NO numerical non-NaN value exists in invalid cells
        invalid_rss_vals = comp.delta_rss_dbm[invalid_mask]
        invalid_gain_vals = comp.delta_path_gain_db[invalid_mask]
        self.assertTrue(np.all(np.isnan(invalid_rss_vals)))
        self.assertTrue(np.all(np.isnan(invalid_gain_vals)))

    # -------------------------------------------------------------------------
    # Test 10: Verify summary metrics use valid cells only
    # -------------------------------------------------------------------------
    def test_10_verify_summary_metrics_use_valid_cells_only(self):
        """Verify min, max, mean, and std summary statistics ignore invalid NaN cells."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=False)
        valid_rss = comp.delta_rss_dbm[comp.valid_mask]

        self.assertAlmostEqual(comp.rss_metrics["min_difference"], float(np.min(valid_rss)))
        self.assertAlmostEqual(comp.rss_metrics["max_difference"], float(np.max(valid_rss)))
        self.assertAlmostEqual(comp.rss_metrics["mean_difference"], float(np.mean(valid_rss)))
        self.assertAlmostEqual(comp.rss_metrics["std_difference"], float(np.std(valid_rss)))

    # -------------------------------------------------------------------------
    # Test 11: Verify no-valid-cell behavior
    # -------------------------------------------------------------------------
    def test_11_verify_no_valid_cell_behavior(self):
        """Verify experiments with zero overlapping valid cells return None for summary metrics without crashing."""
        ny, nx = 4, 5
        gain_zero = np.zeros((ny, nx))
        res_zero1 = _create_synthetic_result(gain_linear_matrix=gain_zero)
        res_zero2 = _create_synthetic_result(gain_linear_matrix=gain_zero)
        id_z1 = self.store.save_experiment(res_zero1)
        id_z2 = self.store.save_experiment(res_zero2)

        comp = self.comparator.compare_experiments(id_z1, id_z2, generate_heatmaps=False)
        self.assertEqual(comp.rss_metrics["valid_cells"], 0)
        self.assertEqual(comp.rss_metrics["valid_cells_percentage"], 0.0)
        self.assertIsNone(comp.rss_metrics["min_difference"])
        self.assertIsNone(comp.rss_metrics["max_difference"])
        self.assertIsNone(comp.rss_metrics["mean_difference"])
        self.assertIsNone(comp.rss_metrics["std_difference"])

    # -------------------------------------------------------------------------
    # Test 12: Reject different scene names
    # -------------------------------------------------------------------------
    def test_12_reject_different_scene_names(self):
        """Verify ValueError when comparing experiments with different scene names."""
        res_diff_scene = _create_synthetic_result(scene_name="frankfurt")
        id_diff = self.store.save_experiment(res_diff_scene)

        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(self.exp_a_id, id_diff, generate_heatmaps=False)
        self.assertIn("scene_name", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 13: Reject different measurement heights
    # -------------------------------------------------------------------------
    def test_13_reject_different_measurement_heights(self):
        """Verify ValueError when comparing experiments at different measurement heights."""
        res_diff_h = _create_synthetic_result(measurement_height=2.5)
        id_diff = self.store.save_experiment(res_diff_h)

        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(self.exp_a_id, id_diff, generate_heatmaps=False)
        self.assertIn("measurement_height", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 14: Reject different grid dimensions
    # -------------------------------------------------------------------------
    def test_14_reject_different_grid_dimensions(self):
        """Verify ValueError when grid dimensions (Ny, Nx) do not match."""
        res_diff_dims = _create_synthetic_result(ny=5, nx=4)
        id_diff = self.store.save_experiment(res_diff_dims)

        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(self.exp_a_id, id_diff, generate_heatmaps=False)
        self.assertIn("grid_dimensions", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 15: Reject different cell sizes
    # -------------------------------------------------------------------------
    def test_15_reject_different_cell_sizes(self):
        """Verify ValueError when cell sizes (dx, dy) do not match."""
        res_diff_cs = _create_synthetic_result(dx=5.0, dy=4.0)
        id_diff = self.store.save_experiment(res_diff_cs)

        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(self.exp_a_id, id_diff, generate_heatmaps=False)
        self.assertIn("cell_size", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 16: Reject different region bounds
    # -------------------------------------------------------------------------
    def test_16_reject_different_region_bounds(self):
        """Verify ValueError when bounding box coordinates do not align."""
        res_diff_bounds = _create_synthetic_result()
        res_diff_bounds.region_bounds = (10.0, 60.0, 0.0, 32.0)
        id_diff = self.store.save_experiment(res_diff_bounds)

        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(self.exp_a_id, id_diff, generate_heatmaps=False)
        self.assertIn("region_bounds", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 17: Reject misaligned cell centers
    # -------------------------------------------------------------------------
    def test_17_reject_misaligned_cell_centers(self):
        """Verify ValueError when cell center coordinates do not align within tolerance."""
        res_shifted = _create_synthetic_result()
        res_shifted.cell_centers = res_shifted.cell_centers + 0.5  # 50 cm shift
        id_diff = self.store.save_experiment(res_shifted)

        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(self.exp_a_id, id_diff, generate_heatmaps=False)
        self.assertIn("cell_centers", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 18: Reject incompatible coordinate arrays
    # -------------------------------------------------------------------------
    def test_18_reject_incompatible_coordinate_arrays(self):
        """Verify ValueError when x_coordinates or y_coordinates do not align."""
        res_shifted_x = _create_synthetic_result()
        res_shifted_x.x_coordinates = res_shifted_x.x_coordinates + 1.0
        id_diff = self.store.save_experiment(res_shifted_x)

        with self.assertRaises(ValueError) as ctx:
            self.comparator.compare_experiments(self.exp_a_id, id_diff, generate_heatmaps=False)
        self.assertIn("x_coordinates", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 19: Verify floating-point coordinate tolerance
    # -------------------------------------------------------------------------
    def test_19_verify_floating_point_coordinate_tolerance(self):
        """Verify small coordinate deviations within tolerance succeed, while deviations beyond tolerance fail."""
        # 1. Deviation within tolerance (1e-5 < 1e-3)
        res_micro_shift = _create_synthetic_result()
        res_micro_shift.cell_centers = res_micro_shift.cell_centers + 1e-5
        res_micro_shift.x_coordinates = res_micro_shift.x_coordinates + 1e-5
        res_micro_shift.y_coordinates = res_micro_shift.y_coordinates + 1e-5
        id_micro = self.store.save_experiment(res_micro_shift)

        comp = self.comparator.compare_experiments(self.exp_a_id, id_micro, generate_heatmaps=False)
        self.assertIsInstance(comp, ComparisonResult)

        # 2. Deviation beyond tolerance (0.01 > 1e-3)
        res_macro_shift = _create_synthetic_result()
        res_macro_shift.cell_centers = res_macro_shift.cell_centers + 0.01
        res_macro_shift.x_coordinates = res_macro_shift.x_coordinates + 0.01
        res_macro_shift.y_coordinates = res_macro_shift.y_coordinates + 0.01
        id_macro = self.store.save_experiment(res_macro_shift)

        with self.assertRaises(ValueError):
            self.comparator.compare_experiments(self.exp_a_id, id_macro, generate_heatmaps=False)

    # -------------------------------------------------------------------------
    # Test 20: Verify different TX powers are allowed
    # -------------------------------------------------------------------------
    def test_20_verify_different_tx_powers_allowed(self):
        """Verify experiments with different transmit powers can be compared."""
        res_pwr = _create_synthetic_result(tx_power_dbm=40.0)
        id_pwr = self.store.save_experiment(res_pwr)

        comp = self.comparator.compare_experiments(self.exp_a_id, id_pwr, generate_heatmaps=False)
        self.assertIsInstance(comp, ComparisonResult)

    # -------------------------------------------------------------------------
    # Test 21: Verify different TX positions are allowed
    # -------------------------------------------------------------------------
    def test_21_verify_different_tx_positions_allowed(self):
        """Verify experiments with different transmitter positions can be compared."""
        res_pos = _create_synthetic_result(tx_position=(100.0, 50.0, 40.0))
        id_pos = self.store.save_experiment(res_pos)

        comp = self.comparator.compare_experiments(self.exp_a_id, id_pos, generate_heatmaps=False)
        self.assertIsInstance(comp, ComparisonResult)

    # -------------------------------------------------------------------------
    # Test 22: Verify different antenna configurations are allowed
    # -------------------------------------------------------------------------
    def test_22_verify_different_antenna_configurations_allowed(self):
        """Verify experiments with different antenna types and polarizations can be compared."""
        res_ant = _create_synthetic_result(
            antenna_type="isotropic",
            antenna_pattern="iso",
            polarization="H",
        )
        id_ant = self.store.save_experiment(res_ant)

        comp = self.comparator.compare_experiments(self.exp_a_id, id_ant, generate_heatmaps=False)
        self.assertIsInstance(comp, ComparisonResult)

    # -------------------------------------------------------------------------
    # Test 23: Preserve and report frequency differences
    # -------------------------------------------------------------------------
    def test_23_preserve_and_report_frequency_differences(self):
        """Verify frequency differences are permitted, preserved, and reported in comparison metadata."""
        res_freq = _create_synthetic_result(freq_hz=28e9)  # 28 GHz vs 3.5 GHz
        id_freq = self.store.save_experiment(res_freq)

        comp = self.comparator.compare_experiments(self.exp_a_id, id_freq, generate_heatmaps=False)
        self.assertFalse(comp.frequency_match)
        self.assertEqual(comp.frequency_a_hz, 3.5e9)
        self.assertEqual(comp.frequency_b_hz, 28e9)

    # -------------------------------------------------------------------------
    # Test 24: Generate RSS difference heatmap
    # -------------------------------------------------------------------------
    def test_24_generate_rss_difference_heatmap(self):
        """Verify RSS difference heatmap PNG is created and saved to disk."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=True)
        self.assertTrue(comp.heatmaps_available["rss_diff_heatmap"])
        rss_path = comp.heatmap_paths["rss_diff_heatmap"]
        self.assertTrue(os.path.isfile(rss_path))
        self.assertGreater(os.path.getsize(rss_path), 0)

    # -------------------------------------------------------------------------
    # Test 25: Generate path-gain difference heatmap
    # -------------------------------------------------------------------------
    def test_25_generate_path_gain_difference_heatmap(self):
        """Verify Path-Gain difference heatmap PNG is created and saved to disk."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=True)
        self.assertTrue(comp.heatmaps_available["path_gain_diff_heatmap"])
        gain_path = comp.heatmap_paths["path_gain_diff_heatmap"]
        self.assertTrue(os.path.isfile(gain_path))
        self.assertGreater(os.path.getsize(gain_path), 0)

    # -------------------------------------------------------------------------
    # Test 26: Verify invalid cells are masked
    # -------------------------------------------------------------------------
    def test_26_verify_invalid_cells_are_masked(self):
        """Verify difference heatmap renders cleanly without raising errors on NaN / invalid cells."""
        # Both experiments have invalid cells; plotting must succeed with masking
        out_png = os.path.join(self.output_dir, "masked_test.png")
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=False)

        path = self.comparator.plot_difference_heatmap(
            delta_arr=comp.delta_rss_dbm,
            valid_mask=comp.valid_mask,
            x_coordinates=comp.x_coordinates,
            y_coordinates=comp.y_coordinates,
            cell_size=comp.cell_size,
            output_path=out_png,
            metric_title="Received Power Difference",
            unit_label="dB",
            exp_a_id=self.exp_a_id,
            exp_b_id=self.exp_b_id,
            scene_name=comp.scene_name,
            measurement_height=comp.measurement_height,
        )
        self.assertTrue(os.path.isfile(path))

    # -------------------------------------------------------------------------
    # Test 27: Verify heatmap generation gracefully handles missing Matplotlib
    # -------------------------------------------------------------------------
    def test_27_verify_heatmap_graceful_missing_matplotlib(self):
        """Verify numerical comparison succeeds even when matplotlib is unavailable."""
        with patch("experiment_comparator.MATPLOTLIB_AVAILABLE", False):
            comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=True)
            self.assertIsInstance(comp, ComparisonResult)
            self.assertFalse(comp.heatmaps_available["rss_diff_heatmap"])
            self.assertFalse(comp.heatmaps_available["path_gain_diff_heatmap"])
            self.assertEqual(comp.heatmap_paths, {})

    # -------------------------------------------------------------------------
    # Test 28: Verify original saved experiment arrays remain unchanged
    # -------------------------------------------------------------------------
    def test_28_verify_original_saved_experiments_unchanged(self):
        """Verify comparing experiments performs read-only operations and does not alter stored files."""
        # Load before comparison
        orig_a = self.store.load_experiment(self.exp_a_id)
        orig_b = self.store.load_experiment(self.exp_b_id)

        # Run comparison
        _ = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=True)

        # Load after comparison
        post_a = self.store.load_experiment(self.exp_a_id)
        post_b = self.store.load_experiment(self.exp_b_id)

        self.assertTrue(np.array_equal(orig_a.rss_dbm, post_a.rss_dbm, equal_nan=True))
        self.assertTrue(np.array_equal(orig_b.rss_dbm, post_b.rss_dbm, equal_nan=True))
        self.assertTrue(np.array_equal(orig_a.path_gain_db, post_a.path_gain_db, equal_nan=True))
        self.assertTrue(np.array_equal(orig_b.path_gain_db, post_b.path_gain_db, equal_nan=True))

    # -------------------------------------------------------------------------
    # Test 29: Handle nonexistent experiment IDs
    # -------------------------------------------------------------------------
    def test_29_handle_nonexistent_experiment_ids(self):
        """Verify FileNotFoundError when comparing nonexistent experiment IDs."""
        with self.assertRaises(FileNotFoundError):
            self.comparator.compare_experiments("nonexistent_id_123", self.exp_b_id)

        with self.assertRaises(FileNotFoundError):
            self.comparator.compare_experiments(self.exp_a_id, "nonexistent_id_456")

    # -------------------------------------------------------------------------
    # Test 30: Verify comparison metadata and result structure
    # -------------------------------------------------------------------------
    def test_30_verify_comparison_metadata_and_result_structure(self):
        """Verify ComparisonResult dictionary serialization both with and without full arrays."""
        comp = self.comparator.compare_experiments(self.exp_a_id, self.exp_b_id, generate_heatmaps=True)
        summary = comp.to_dict(include_full_arrays=False)

        self.assertEqual(summary["experiment_a_id"], self.exp_a_id)
        self.assertEqual(summary["experiment_b_id"], self.exp_b_id)
        self.assertIn("rss_metrics", summary)
        self.assertIn("path_gain_metrics", summary)
        self.assertNotIn("delta_rss_dbm", summary)

        full_payload = comp.to_dict(include_full_arrays=True)
        self.assertIn("delta_rss_dbm", full_payload)
        self.assertIn("delta_path_gain_db", full_payload)
        self.assertIn("valid_mask", full_payload)

        # Verify JSON serializability of the full payload
        json_str = json.dumps(full_payload)
        self.assertIsInstance(json_str, str)

    # -------------------------------------------------------------------------
    # Supplementary Test 31: Non-separable 2D coordinates comparison and heatmaps
    # -------------------------------------------------------------------------
    def test_31_non_separable_2d_coordinates_comparison_and_heatmaps(self):
        """Verify non-separable 2D coordinate grids compare and render difference heatmaps."""
        res_ns_a = _create_synthetic_result(separable=False, power_offset_dbm=0.0)
        res_ns_b = _create_synthetic_result(separable=False, power_offset_dbm=3.0)
        id_ns_a = self.store.save_experiment(res_ns_a)
        id_ns_b = self.store.save_experiment(res_ns_b)

        comp = self.comparator.compare_experiments(id_ns_a, id_ns_b, generate_heatmaps=True)
        self.assertEqual(comp.x_coordinates.ndim, 2)
        self.assertEqual(comp.y_coordinates.ndim, 2)
        self.assertTrue(comp.heatmaps_available["rss_diff_heatmap"])
        self.assertTrue(os.path.isfile(comp.heatmap_paths["rss_diff_heatmap"]))

    # -------------------------------------------------------------------------
    # Supplementary Test 32: Equality tolerance threshold
    # -------------------------------------------------------------------------
    def test_32_equality_tolerance_threshold(self):
        """Verify differences within equality_tolerance_db are classified as equal."""
        # Baseline with slight difference of 0.005 dB (below default tolerance 0.01 dB)
        res_slight = _create_synthetic_result(power_offset_dbm=0.005)
        id_slight = self.store.save_experiment(res_slight)

        comp = self.comparator.compare_experiments(
            self.exp_a_id, id_slight, generate_heatmaps=False, equality_tolerance_db=0.01
        )
        self.assertEqual(comp.rss_metrics["equal_cells"], comp.rss_metrics["valid_cells"])
        self.assertEqual(comp.rss_metrics["b_stronger_cells"], 0)


if __name__ == "__main__":
    unittest.main()

