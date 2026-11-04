"""Unit tests for RadioMapResult and metric extraction (Phase 4)."""

import math
import os
import sys
from typing import Any
import unittest
from unittest.mock import MagicMock

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
    from radio_map_config import RadioMapConfig
except (ImportError, ModuleNotFoundError):
    from src.radio_map_config import RadioMapConfig

try:
    from radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from src.radio_map_result import RadioMapResult


class TestRadioMapResult(unittest.TestCase):
    """Unit tests for RadioMapResult metric extraction, validation, and conversions."""

    def setUp(self):
        """Set up standard RadioMapConfig and synthetic raw radio-map arrays."""
        if np is None:
            self.skipTest("NumPy is required for RadioMapResult tests.")

        self.config = RadioMapConfig(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            tx_orientation_deg=(0.0, 0.0, 0.0),
            antenna_type="isotropic",
            receiver_height=1.5,
            cell_size=2.0,
        )

        # 3 rows (Y) x 4 cols (X)
        self.ny, self.nx = 3, 4

        # Linear path gains (positive and one zero cell)
        self.gain_linear_2d = np.array([
            [1.0, 0.1, 0.01, 0.0],
            [0.5, 0.05, 0.005, 1e-4],
            [0.2, 0.02, 0.002, 0.0],
        ], dtype=np.float64)

        # RSS in Watts (TX power = 30 dBm = 1.0 Watt -> RSS = 1.0 * gain)
        self.rss_watts_2d = self.gain_linear_2d * 1.0

        # cell_centers: [3, 4, 3] with X in [-3, -1, 1, 3] and Y in [-2, 0, 2], Z=1.5
        xs = np.array([-3.0, -1.0, 1.0, 3.0])
        ys = np.array([-2.0, 0.0, 2.0])
        self.cell_centers_3d = np.zeros((self.ny, self.nx, 3), dtype=np.float64)
        for i, y in enumerate(ys):
            for j, x in enumerate(xs):
                self.cell_centers_3d[i, j] = [x, y, 1.5]

    def _create_raw_mock(self, gain, rss, centers):
        mock = MagicMock()
        mock.path_gain = gain
        mock.rss = rss
        mock.cell_centers = centers
        return mock

    # -------------------------------------------------------------------------
    # 1. Extraction from Raw 3D and 2D Tensors
    # -------------------------------------------------------------------------
    def test_from_raw_radio_map_valid_3d_tensors(self):
        """Verify extraction from documented 3D shape [1, Ny, Nx]."""
        raw_mock = self._create_raw_mock(
            gain=self.gain_linear_2d[np.newaxis, :, :],  # [1, 3, 4]
            rss=self.rss_watts_2d[np.newaxis, :, :],      # [1, 3, 4]
            centers=self.cell_centers_3d,                 # [3, 4, 3]
        )

        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config, backend_variant="llvm")

        self.assertEqual(result.grid_dimensions, (3, 4))
        self.assertEqual(result.num_cells, 12)
        self.assertEqual(result.path_gain_linear.shape, (3, 4))
        self.assertEqual(result.rss_watts.shape, (3, 4))
        self.assertEqual(result.cell_centers.shape, (3, 4, 3))
        self.assertEqual(result.backend_variant, "llvm")

    def test_from_raw_radio_map_valid_2d_tensors(self):
        """Verify extraction when inputs are already 2D [Ny, Nx]."""
        raw_mock = self._create_raw_mock(
            gain=self.gain_linear_2d,
            rss=self.rss_watts_2d,
            centers=self.cell_centers_3d,
        )

        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertEqual(result.grid_dimensions, (3, 4))
        self.assertEqual(result.path_gain_linear.shape, (3, 4))

    # -------------------------------------------------------------------------
    # 2. Single-Transmitter Dimension and Multi-Transmitter Rejection
    # -------------------------------------------------------------------------
    def test_multiple_transmitters_rejection(self):
        """Verify error when first dimension > 1 (multiple transmitters)."""
        multi_tx_gain = np.tile(self.gain_linear_2d[np.newaxis, :, :], (2, 1, 1))  # [2, 3, 4]
        raw_mock = self._create_raw_mock(
            gain=multi_tx_gain,
            rss=multi_tx_gain,
            centers=self.cell_centers_3d,
        )

        with self.assertRaises(ValueError) as ctx:
            RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertIn("Expected single transmitter radio map", str(ctx.exception))

    def test_invalid_tensor_ndim_rejection(self):
        """Verify rejection of 1D or 4D arrays."""
        raw_mock = self._create_raw_mock(
            gain=np.array([1.0, 2.0]),  # 1D
            rss=self.rss_watts_2d,
            centers=self.cell_centers_3d,
        )
        with self.assertRaises(ValueError) as ctx:
            RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertIn("Invalid path_gain array shape", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 3. Mathematical Unit Conversions (Watts -> dBm, Linear -> dB)
    # -------------------------------------------------------------------------
    def test_rss_watts_to_dbm_conversion(self):
        """Verify exact mathematical formula: 10 * log10(P_W) + 30."""
        # Test values: 1.0 W -> 30.0 dBm, 0.001 W -> 0.0 dBm, 1e-6 W -> -30.0 dBm
        test_rss_watts = np.array([[1.0, 1e-3], [1e-6, 1e-9]])
        test_gain = test_rss_watts
        centers = np.zeros((2, 2, 3))

        raw_mock = self._create_raw_mock(test_gain, test_rss_watts, centers)
        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config)

        self.assertAlmostEqual(result.rss_dbm[0, 0], 30.0, places=5)
        self.assertAlmostEqual(result.rss_dbm[0, 1], 0.0, places=5)
        self.assertAlmostEqual(result.rss_dbm[1, 0], -30.0, places=5)
        self.assertAlmostEqual(result.rss_dbm[1, 1], -60.0, places=5)

    def test_path_gain_linear_to_db_conversion(self):
        """Verify exact mathematical formula: 10 * log10(gain)."""
        test_gain = np.array([[1.0, 0.1], [0.01, 1e-4]])
        test_rss = test_gain
        centers = np.zeros((2, 2, 3))

        raw_mock = self._create_raw_mock(test_gain, test_rss, centers)
        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config)

        self.assertAlmostEqual(result.path_gain_db[0, 0], 0.0, places=5)
        self.assertAlmostEqual(result.path_gain_db[0, 1], -10.0, places=5)
        self.assertAlmostEqual(result.path_gain_db[1, 0], -20.0, places=5)
        self.assertAlmostEqual(result.path_gain_db[1, 1], -40.0, places=5)

    def test_zero_rss_and_path_gain_produces_negative_inf(self):
        """Verify that zero RSS and zero path gain strictly evaluate to -inf (no invented noise floor)."""
        raw_mock = self._create_raw_mock(
            gain=self.gain_linear_2d,
            rss=self.rss_watts_2d,
            centers=self.cell_centers_3d,
        )
        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config)

        # Cell [0, 3] and [2, 3] have 0.0 Watts RSS
        self.assertEqual(result.rss_watts[0, 3], 0.0)
        self.assertEqual(result.rss_dbm[0, 3], -np.inf)
        self.assertEqual(result.path_gain_db[0, 3], -np.inf)

        # Preserved linear values
        self.assertEqual(result.rss_watts[0, 3], 0.0)
        self.assertEqual(result.path_gain_linear[0, 3], 0.0)

    # -------------------------------------------------------------------------
    # 4. Negative and Invalid Data Rejection Tests
    # -------------------------------------------------------------------------
    def test_negative_rss_rejection(self):
        """Verify clear error when negative RSS power values exist."""
        bad_rss = self.rss_watts_2d.copy()
        bad_rss[1, 1] = -1e-5
        raw_mock = self._create_raw_mock(self.gain_linear_2d, bad_rss, self.cell_centers_3d)

        with self.assertRaises(ValueError) as ctx:
            RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertIn("Invalid negative RSS power detected", str(ctx.exception))

    def test_negative_path_gain_rejection(self):
        """Verify clear error when negative path gain values exist."""
        bad_gain = self.gain_linear_2d.copy()
        bad_gain[0, 0] = -0.5
        raw_mock = self._create_raw_mock(bad_gain, self.rss_watts_2d, self.cell_centers_3d)

        with self.assertRaises(ValueError) as ctx:
            RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertIn("Invalid negative path gain detected", str(ctx.exception))

    def test_nan_and_inf_in_raw_data_rejection(self):
        """Verify rejection of NaN and Inf in linear raw inputs."""
        nan_rss = self.rss_watts_2d.copy()
        nan_rss[0, 0] = np.nan
        raw_mock = self._create_raw_mock(self.gain_linear_2d, nan_rss, self.cell_centers_3d)

        with self.assertRaises(ValueError) as ctx:
            RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertIn("NaN values detected in raw Sionna RT simulation outputs", str(ctx.exception))

        inf_gain = self.gain_linear_2d.copy()
        inf_gain[0, 0] = np.inf
        raw_mock_inf = self._create_raw_mock(inf_gain, self.rss_watts_2d, self.cell_centers_3d)

        with self.assertRaises(ValueError) as ctx:
            RadioMapResult.from_raw_radio_map(raw_mock_inf, self.config)
        self.assertIn("Infinite values detected in raw Sionna RT linear simulation outputs", str(ctx.exception))

    def test_shape_mismatch_rejection(self):
        """Verify error when gain, rss, or cell_centers have mismatched dimensions."""
        mismatched_rss = np.ones((2, 4))  # 2 rows instead of 3
        raw_mock = self._create_raw_mock(self.gain_linear_2d, mismatched_rss, self.cell_centers_3d)

        with self.assertRaises(ValueError) as ctx:
            RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertIn("Shape mismatch", str(ctx.exception))

    def test_empty_grid_rejection(self):
        """Verify error when grid dimension is zero."""
        empty_gain = np.empty((0, 0))
        raw_mock = self._create_raw_mock(empty_gain, empty_gain, np.empty((0, 0, 3)))

        with self.assertRaises(ValueError) as ctx:
            RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertIn("Radio map grid is empty", str(ctx.exception))

    def test_missing_properties_rejection(self):
        """Verify AttributeError when raw object lacks required properties."""
        incomplete_mock = MagicMock(spec=["path_gain"])
        incomplete_mock.path_gain = self.gain_linear_2d

        with self.assertRaises(AttributeError) as ctx:
            RadioMapResult.from_raw_radio_map(incomplete_mock, self.config)
        self.assertIn("lacks required property 'rss'", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 5. Coordinate Extraction Tests
    # -------------------------------------------------------------------------
    def test_separable_coordinate_extraction(self):
        """Verify 1D coordinate extraction on axis-aligned regular rectangular grid."""
        raw_mock = self._create_raw_mock(
            gain=self.gain_linear_2d,
            rss=self.rss_watts_2d,
            centers=self.cell_centers_3d,
        )
        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config)

        # 1D separable coordinate arrays
        self.assertEqual(result.x_coordinates.ndim, 1)
        self.assertEqual(result.y_coordinates.ndim, 1)
        np.testing.assert_array_almost_equal(result.x_coordinates, [-3.0, -1.0, 1.0, 3.0])
        np.testing.assert_array_almost_equal(result.y_coordinates, [-2.0, 0.0, 2.0])
        self.assertAlmostEqual(result.measurement_height, 1.5, places=5)

    def test_non_separable_coordinate_extraction(self):
        """Verify full 2D coordinate preservation when grid is non-separable/rotated."""
        non_sep_centers = self.cell_centers_3d.copy()
        # Skew X along Y
        non_sep_centers[1, :, 0] += 0.5
        raw_mock = self._create_raw_mock(self.gain_linear_2d, self.rss_watts_2d, non_sep_centers)

        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config)
        self.assertEqual(result.x_coordinates.ndim, 2)
        self.assertEqual(result.y_coordinates.ndim, 2)

    # -------------------------------------------------------------------------
    # 6. Metadata and Summary Statistics Tests
    # -------------------------------------------------------------------------
    def test_metadata_and_summary_metrics(self):
        """Verify summary metrics: min/mean/max RSS, valid cell count, and coverage percentages."""
        raw_mock = self._create_raw_mock(
            gain=self.gain_linear_2d,
            rss=self.rss_watts_2d,
            centers=self.cell_centers_3d,
        )
        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config)

        self.assertEqual(result.scene_name, "simple_reflector")
        self.assertEqual(result.frequency_hz, 3.5e9)
        self.assertEqual(result.antenna_type, "isotropic")

        # Total 12 cells, 2 zero cells -> 10 valid cells
        self.assertEqual(result.num_cells, 12)
        self.assertEqual(result.valid_cells_count, 10)
        self.assertEqual(result.zero_power_cells_count, 2)
        self.assertAlmostEqual(result.coverage_percentage, (10 / 12) * 100.0, places=3)

        # Max power: 1.0 W = 30 dBm
        self.assertAlmostEqual(result.max_rss_dbm, 30.0, places=4)
        # Min power: 0.0001 W = -10 dBm
        self.assertAlmostEqual(result.min_rss_dbm, -10.0, places=4)
        self.assertIsNotNone(result.mean_rss_dbm)

        # Coverage threshold
        self.assertAlmostEqual(result.coverage_above_threshold(-10.0), (10 / 12) * 100.0, places=3)
        self.assertAlmostEqual(result.coverage_above_threshold(35.0), 0.0, places=3)

    def test_to_dict_serialization(self):
        """Verify dictionary serialization without and with full arrays."""
        raw_mock = self._create_raw_mock(
            gain=self.gain_linear_2d,
            rss=self.rss_watts_2d,
            centers=self.cell_centers_3d,
        )
        result = RadioMapResult.from_raw_radio_map(raw_mock, self.config)

        summary_dict = result.to_dict(include_full_arrays=False)
        self.assertIn("scene_name", summary_dict)
        self.assertIn("coverage_percentage", summary_dict)
        self.assertNotIn("path_gain_linear", summary_dict)

        full_dict = result.to_dict(include_full_arrays=True)
        self.assertIn("path_gain_linear", full_dict)
        self.assertEqual(len(full_dict["path_gain_linear"]), 3)
        self.assertEqual(len(full_dict["path_gain_linear"][0]), 4)


if __name__ == "__main__":
    unittest.main()

