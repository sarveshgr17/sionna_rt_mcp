"""Unit tests for RadioMapFormatter (Phase 4)."""

import os
import shutil
import sys
import tempfile
from typing import Any
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
    from radio_map_config import RadioMapConfig
except (ImportError, ModuleNotFoundError):
    from src.radio_map_config import RadioMapConfig

try:
    from radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from src.radio_map_result import RadioMapResult

try:
    from radio_map_formatter import MATPLOTLIB_AVAILABLE, RadioMapFormatter
except (ImportError, ModuleNotFoundError):
    from src.radio_map_formatter import MATPLOTLIB_AVAILABLE, RadioMapFormatter


class TestRadioMapFormatter(unittest.TestCase):
    """Unit tests for RadioMapFormatter covering text summaries and heatmap rendering."""

    def setUp(self):
        """Create a synthetic RadioMapResult with known values for testing."""
        if np is None:
            self.skipTest("NumPy is required for RadioMapFormatter tests.")

        self.temp_dir = tempfile.mkdtemp()

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

        ny, nx = 4, 5
        xs = np.linspace(-10.0, 10.0, nx)
        ys = np.linspace(-10.0, 10.0, ny)

        cell_centers = np.zeros((ny, nx, 3))
        for i, y in enumerate(ys):
            for j, x in enumerate(xs):
                cell_centers[i, j] = [x, y, 1.5]

        # Synthetic gain with one zero cell at [0, 0]
        gain = np.ones((ny, nx)) * 0.01
        gain[0, 0] = 0.0  # Zero gain / unreachable
        rss = gain * 1.0  # 1 Watt TX power

        raw_mock = MagicMock()
        raw_mock.path_gain = gain
        raw_mock.rss = rss
        raw_mock.cell_centers = cell_centers

        self.result = RadioMapResult.from_raw_radio_map(
            raw_mock,
            self.config,
            backend_variant="llvm_ad_mono_polarized",
            region_bounds=(-10.0, 10.0, -10.0, 10.0),
        )

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Text Summary Tests
    # -------------------------------------------------------------------------
    def test_format_summary_text_output(self):
        """Verify format_summary produces structured terminal output with core metrics."""
        summary = RadioMapFormatter.format_summary(self.result)

        self.assertIn("simple_reflector", summary)
        self.assertIn("3.50 GHz", summary)
        self.assertIn("Grid Dimensions:", summary)
        self.assertIn("Reached Cells:", summary)
        self.assertIn("Unreached Cells:", summary)
        self.assertIn("19 / 20", summary)  # 1 zero cell out of 20
        self.assertIn("Min Received Power:", summary)
        self.assertIn("Max Received Power:", summary)

    # -------------------------------------------------------------------------
    # 2. Heatmap Generation Tests (when Matplotlib is available)
    # -------------------------------------------------------------------------
    def test_plot_received_power_heatmap_creation(self):
        """Verify creation of RSS heatmap PNG with proper dimensions and labels."""
        if not MATPLOTLIB_AVAILABLE:
            self.skipTest("Matplotlib is not installed in the current environment.")

        out_path = os.path.join(self.temp_dir, "test_rss.png")
        saved_path = RadioMapFormatter.plot_received_power_heatmap(self.result, out_path)

        self.assertTrue(os.path.exists(saved_path))
        self.assertGreater(os.path.getsize(saved_path), 1000)

    def test_plot_path_gain_heatmap_creation(self):
        """Verify creation of Path Gain heatmap PNG."""
        if not MATPLOTLIB_AVAILABLE:
            self.skipTest("Matplotlib is not installed in the current environment.")

        out_path = os.path.join(self.temp_dir, "test_gain.png")
        saved_path = RadioMapFormatter.plot_path_gain_heatmap(self.result, out_path)

        self.assertTrue(os.path.exists(saved_path))
        self.assertGreater(os.path.getsize(saved_path), 1000)

    def test_generate_heatmaps_creates_both_files(self):
        """Verify generate_heatmaps outputs both RSS and Path-Gain files."""
        if not MATPLOTLIB_AVAILABLE:
            self.skipTest("Matplotlib is not installed in the current environment.")

        heatmaps = RadioMapFormatter.generate_heatmaps(
            self.result,
            self.temp_dir,
            prefix="sim_test",
        )

        self.assertIn("rss_heatmap", heatmaps)
        self.assertIn("path_gain_heatmap", heatmaps)
        self.assertTrue(os.path.exists(heatmaps["rss_heatmap"]))
        self.assertTrue(os.path.exists(heatmaps["path_gain_heatmap"]))

    # -------------------------------------------------------------------------
    # 3. Missing Visualization Dependency Handling
    # -------------------------------------------------------------------------
    def test_missing_matplotlib_handling(self):
        """Verify clear RuntimeError when matplotlib is unavailable."""
        with patch("radio_map_formatter.MATPLOTLIB_AVAILABLE", False):
            with self.assertRaises(RuntimeError) as ctx:
                RadioMapFormatter.plot_received_power_heatmap(
                    self.result,
                    os.path.join(self.temp_dir, "dummy.png"),
                )
            self.assertIn("Heatmap visualization requires 'matplotlib'", str(ctx.exception))

            with self.assertRaises(RuntimeError) as ctx2:
                RadioMapFormatter.plot_path_gain_heatmap(
                    self.result,
                    os.path.join(self.temp_dir, "dummy.png"),
                )
            self.assertIn("Heatmap visualization requires 'matplotlib'", str(ctx2.exception))


if __name__ == "__main__":
    unittest.main()

