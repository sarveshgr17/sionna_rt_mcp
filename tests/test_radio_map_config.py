"""Unit tests for RadioMapConfig dataclass and validation (Phase 2)."""

import math
import sys
from typing import Any, Dict
try:
    import pytest
except ImportError:
    import contextlib
    import re

    class _PytestFallback:
        @staticmethod
        @contextlib.contextmanager
        def raises(expected_exception, match=None):
            try:
                yield
            except expected_exception as exc:
                if match:
                    if not re.search(match, str(exc)):
                        raise AssertionError(
                            f"Pattern '{match}' did not match exception message: '{str(exc)}'"
                        )
            except Exception as other:
                raise AssertionError(
                    f"Expected {expected_exception.__name__}, but caught {type(other).__name__}: {other}"
                )
            else:
                raise AssertionError(f"Expected {expected_exception.__name__} was not raised.")

        @staticmethod
        def approx(expected, rel=1e-5, abs=1e-5):
            class ApproxValue:
                def __eq__(self, actual):
                    return math.isclose(actual, expected, rel_tol=rel, abs_tol=abs)

                def __repr__(self):
                    return f"approx({expected})"

            return ApproxValue()

    pytest = _PytestFallback()

import os
import sys

# Ensure both repo root and src/ directory are accessible on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_dir = os.path.join(repo_root, "src")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    from radio_map_config import (
        ANTENNA_PATTERN_MAPPING,
        VALID_POLARIZATIONS,
        VALID_REGION_MODES,
        RadioMapConfig,
    )
except (ImportError, ModuleNotFoundError):
    from src.radio_map_config import (
        ANTENNA_PATTERN_MAPPING,
        VALID_POLARIZATIONS,
        VALID_REGION_MODES,
        RadioMapConfig,
    )


import unittest


class TestRadioMapConfig(unittest.TestCase):
    """Unit test suite for RadioMapConfig dataclass and validation."""

    # -------------------------------------------------------------------------
    # 1. Default Configuration Tests
    # -------------------------------------------------------------------------
    def test_default_config_initialization(self):
        """Verify that default RadioMapConfig initializes with physically valid parameters."""
        cfg = RadioMapConfig()

        self.assertEqual(cfg.scene_name, "simple_reflector")
        self.assertEqual(cfg.frequency_hz, 3.5e9)
        self.assertEqual(cfg.tx_name, "tx")
        self.assertEqual(cfg.tx_position, (0.0, -10.0, 5.0))
        self.assertEqual(cfg.tx_power_dbm, 30.0)
        self.assertEqual(cfg.tx_orientation_deg, (0.0, 0.0, 0.0))
        self.assertEqual(cfg.tx_orientation_rad, (0.0, 0.0, 0.0))

        # Antenna defaults
        self.assertEqual(cfg.antenna_type, "isotropic")
        self.assertEqual(cfg.antenna_pattern, "iso")
        self.assertEqual(cfg.polarization, "V")
        self.assertEqual(cfg.num_rows, 1)
        self.assertEqual(cfg.num_cols, 1)
        self.assertEqual(cfg.horizontal_spacing, 0.5)
        self.assertEqual(cfg.vertical_spacing, 0.5)

        # Region defaults
        self.assertEqual(cfg.region_mode, "auto")
        self.assertEqual(cfg.auto_margin, 5.0)
        self.assertTrue(cfg.auto_include_tx)
        self.assertIsNone(cfg.x_min)
        self.assertEqual(cfg.receiver_height, 1.5)
        self.assertEqual(cfg.cell_size, 1.0)
        self.assertEqual(cfg.cell_size_tuple, (1.0, 1.0))

        # Solver defaults
        self.assertEqual(cfg.samples_per_tx, 1_000_000)
        self.assertEqual(cfg.max_depth, 3)
        self.assertIsNone(cfg.seed)
        self.assertTrue(cfg.los)
        self.assertTrue(cfg.specular_reflection)
        self.assertTrue(cfg.diffraction)
        self.assertFalse(cfg.scattering)

    # -------------------------------------------------------------------------
    # 2. Antenna Category Mapping & Pattern Validation Tests
    # -------------------------------------------------------------------------
    def test_antenna_type_mapping_and_resolution(self):
        """Verify that user-facing antenna categories map to verified Sionna RT patterns."""
        # Isotropic
        cfg_iso = RadioMapConfig(antenna_type="isotropic")
        self.assertEqual(cfg_iso.antenna_pattern, "iso")

        cfg_iso_alias = RadioMapConfig(antenna_type="iso")
        self.assertEqual(cfg_iso_alias.antenna_pattern, "iso")

        # Dipole
        cfg_dip = RadioMapConfig(antenna_type="dipole")
        self.assertEqual(cfg_dip.antenna_pattern, "dipole")

        cfg_hw_dip = RadioMapConfig(antenna_type="hw_dipole")
        self.assertEqual(cfg_hw_dip.antenna_pattern, "dipole")

        # Directional (maps to 3GPP TR 38.901)
        cfg_dir = RadioMapConfig(antenna_type="directional")
        self.assertEqual(cfg_dir.antenna_pattern, "tr38901")

        cfg_tr = RadioMapConfig(antenna_type="tr38901")
        self.assertEqual(cfg_tr.antenna_pattern, "tr38901")

        # Case insensitivity
        cfg_case = RadioMapConfig(antenna_type="DIRECTIONAL")
        self.assertEqual(cfg_case.antenna_pattern, "tr38901")

    def test_invalid_antenna_type_rejection(self):
        """Verify that unknown/unsupported antenna patterns are rejected."""
        with pytest.raises(ValueError, match="Invalid antenna_type 'patch'"):
            RadioMapConfig(antenna_type="patch")

        with pytest.raises(ValueError, match="Invalid antenna_type ''"):
            RadioMapConfig(antenna_type="")

    def test_antenna_polarization_validation(self):
        """Verify antenna polarization validation."""
        for pol in ["V", "H", "VH", "cross"]:
            cfg = RadioMapConfig(polarization=pol)
            self.assertEqual(cfg.polarization, pol)

        with pytest.raises(ValueError, match="Invalid polarization 'circular'"):
            RadioMapConfig(polarization="circular")

    def test_antenna_array_dimensions_validation(self):
        """Verify num_rows, num_cols, and spacing validation."""
        with pytest.raises(ValueError, match="num_rows must be an integer >= 1"):
            RadioMapConfig(num_rows=0)

        with pytest.raises(ValueError, match="num_cols must be an integer >= 1"):
            RadioMapConfig(num_cols=-2)

        with pytest.raises(ValueError, match="horizontal_spacing must be a positive finite number"):
            RadioMapConfig(horizontal_spacing=-0.5)

        with pytest.raises(ValueError, match="vertical_spacing must be a positive finite number"):
            RadioMapConfig(vertical_spacing=0.0)

    # -------------------------------------------------------------------------
    # 3. Transmitter & Orientation Tests
    # -------------------------------------------------------------------------
    def test_tx_orientation_conversion_to_radians(self):
        """Verify that orientation angles in degrees are correctly converted to radians."""
        cfg = RadioMapConfig(tx_orientation_deg=(90.0, 45.0, -180.0))
        rad = cfg.tx_orientation_rad

        self.assertAlmostEqual(rad[0], math.pi / 2.0, places=5)
        self.assertAlmostEqual(rad[1], math.pi / 4.0, places=5)
        self.assertAlmostEqual(rad[2], -math.pi, places=5)

    def test_tx_position_and_power_validation(self):
        """Verify validation of transmitter 3D coordinates and power."""
        # Invalid length
        with pytest.raises(ValueError, match="tx_position must contain exactly 3 numeric coordinates"):
            RadioMapConfig(tx_position=(0.0, 1.0))

        # Non-finite coordinate
        with pytest.raises(ValueError, match="tx_position coordinates must be finite numbers"):
            RadioMapConfig(tx_position=(0.0, float("nan"), 5.0))

        # Non-finite power
        with pytest.raises(ValueError, match="tx_power_dbm must be a finite numeric value"):
            RadioMapConfig(tx_power_dbm=float("inf"))

    # -------------------------------------------------------------------------
    # 4. Region Configuration: AUTO Mode Tests
    # -------------------------------------------------------------------------
    def test_auto_region_bounds_calculation(self):
        """Verify automatic bounding box derivation from scene bounds and transmitter position."""
        cfg = RadioMapConfig(
            region_mode="auto",
            auto_margin=10.0,
            auto_include_tx=True,
            tx_position=(0.0, -20.0, 5.0),
            receiver_height=2.0,
        )

        # Simulated scene bounds: X in [-10, 10], Y in [-5, 15]
        scene_bbox = ((-10.0, -5.0, 0.0), (10.0, 15.0, 10.0))

        bounds = cfg.calculate_region_bounds(scene_bbox)
        # X range: [-10, 10] -> with margin 10: [-20, 20]
        # Y range: [-20 (tx), 15 (scene)] -> with margin 10: [-30, 25]
        self.assertEqual(bounds, (-20.0, 20.0, -30.0, 25.0))

        center, size = cfg.calculate_center_and_size(scene_bbox)
        # Center X: 0.0, Center Y: (-30 + 25) / 2 = -2.5, Height: 2.0
        self.assertEqual(center, (0.0, -2.5, 2.0))
        # Size X: 40.0, Size Y: 55.0
        self.assertEqual(size, (40.0, 55.0))

    def test_auto_region_without_tx_inclusion(self):
        """Verify automatic bounds when transmitter inclusion is disabled."""
        cfg = RadioMapConfig(
            region_mode="auto",
            auto_margin=2.0,
            auto_include_tx=False,
            tx_position=(0.0, -100.0, 5.0),  # Far outside
        )
        scene_bbox = ((-5.0, -5.0, 0.0), (5.0, 5.0, 10.0))
        bounds = cfg.calculate_region_bounds(scene_bbox)

        # Does NOT expand to -100
        self.assertEqual(bounds, (-7.0, 7.0, -7.0, 7.0))

    def test_auto_region_missing_scene_bbox_raises_error(self):
        """Verify that calculate_region_bounds requires scene_bbox in auto mode."""
        cfg = RadioMapConfig(region_mode="auto")
        with pytest.raises(ValueError, match="scene_bbox must be provided when region_mode is 'auto'"):
            cfg.calculate_region_bounds(None)

    def test_auto_margin_validation(self):
        """Verify auto_margin validation."""
        with pytest.raises(ValueError, match="auto_margin must be a non-negative finite number"):
            RadioMapConfig(auto_margin=-1.0)

    # -------------------------------------------------------------------------
    # 5. Region Configuration: MANUAL Mode Tests
    # -------------------------------------------------------------------------
    def test_manual_region_valid_configuration(self):
        """Verify manual region bounding coordinates and solver center/size computation."""
        cfg = RadioMapConfig(
            region_mode="manual",
            x_min=-25.0,
            x_max=25.0,
            y_min=-50.0,
            y_max=50.0,
            receiver_height=1.8,
            cell_size=2.0,
        )

        bounds = cfg.calculate_region_bounds()
        self.assertEqual(bounds, (-25.0, 25.0, -50.0, 50.0))

        center, size = cfg.calculate_center_and_size()
        self.assertEqual(center, (0.0, 0.0, 1.8))
        self.assertEqual(size, (50.0, 100.0))

    def test_manual_region_missing_coordinates(self):
        """Verify error when any of the 4 manual bounding coordinates is omitted."""
        with pytest.raises(ValueError, match="In manual region mode, 'x_max' must be specified"):
            RadioMapConfig(region_mode="manual", x_min=0.0, y_min=0.0, y_max=10.0)

    def test_manual_region_inverted_coordinates(self):
        """Verify error when max boundary is not strictly greater than min boundary."""
        with pytest.raises(ValueError, match="x_max .* must be strictly greater than x_min"):
            RadioMapConfig(region_mode="manual", x_min=20.0, x_max=10.0, y_min=0.0, y_max=10.0)

        with pytest.raises(ValueError, match="y_max .* must be strictly greater than y_min"):
            RadioMapConfig(region_mode="manual", x_min=0.0, x_max=10.0, y_min=10.0, y_max=10.0)

    # -------------------------------------------------------------------------
    # 6. Receiver Measurement Plane & Cell Size Tests
    # -------------------------------------------------------------------------
    def test_cell_size_scalar_and_tuple(self):
        """Verify cell_size handling as both scalar and (dx, dy) tuple."""
        # Scalar float
        cfg_scalar = RadioMapConfig(cell_size=2.5)
        self.assertEqual(cfg_scalar.cell_size, 2.5)
        self.assertEqual(cfg_scalar.cell_size_tuple, (2.5, 2.5))

        # 2D Tuple
        cfg_tuple = RadioMapConfig(cell_size=(1.0, 2.0))
        self.assertEqual(cfg_tuple.cell_size, (1.0, 2.0))
        self.assertEqual(cfg_tuple.cell_size_tuple, (1.0, 2.0))

    def test_cell_size_invalid_values(self):
        """Verify rejection of zero, negative, or excessive cell sizes."""
        with pytest.raises(ValueError, match="cell_size must be a positive finite number"):
            RadioMapConfig(cell_size=0.0)

        with pytest.raises(ValueError, match="cell_size must be a positive finite number"):
            RadioMapConfig(cell_size=-1.5)

        with pytest.raises(ValueError, match="cell_size dx .* exceeds region X span"):
            RadioMapConfig(
                region_mode="manual",
                x_min=0.0,
                x_max=5.0,
                y_min=0.0,
                y_max=10.0,
                cell_size=10.0,  # 10.0 > 5.0
            )

    # -------------------------------------------------------------------------
    # 7. Solver Parameters Validation Tests
    # -------------------------------------------------------------------------
    def test_solver_parameters_validation(self):
        """Verify samples_per_tx, max_depth, and seed validation."""
        # Valid custom solver params
        cfg = RadioMapConfig(samples_per_tx=500_000, max_depth=5, seed=42)
        self.assertEqual(cfg.samples_per_tx, 500_000)
        self.assertEqual(cfg.max_depth, 5)
        self.assertEqual(cfg.seed, 42)

        with pytest.raises(ValueError, match="samples_per_tx must be an integer >= 1"):
            RadioMapConfig(samples_per_tx=0)

        with pytest.raises(ValueError, match="max_depth must be an integer >= 0"):
            RadioMapConfig(max_depth=-1)

        with pytest.raises(ValueError, match="seed must be None or an integer >= 0"):
            RadioMapConfig(seed=-5)

    # -------------------------------------------------------------------------
    # 8. Serialization & Alias Tests
    # -------------------------------------------------------------------------
    def test_aliases_and_serialization(self):
        """Verify aliases and dictionary serialization / deserialization round-trip."""
        cfg = RadioMapConfig(
            scene="custom_scene",
            frequency=28.0e9,
            power_dbm=23.0,
            antenna_type="directional",
            cell_size=(1.5, 1.5),
        )

        self.assertEqual(cfg.scene_name, "custom_scene")
        self.assertEqual(cfg.frequency_hz, 28.0e9)
        self.assertEqual(cfg.tx_power_dbm, 23.0)
        self.assertEqual(cfg.antenna_pattern, "tr38901")

        d = cfg.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["scene_name"], "custom_scene")
        self.assertEqual(d["frequency_hz"], 28.0e9)
        self.assertEqual(d["antenna_pattern"], "tr38901")
        self.assertEqual(d["cell_size"], [1.5, 1.5])

        # Reconstruct from dict
        restored = RadioMapConfig.from_dict(d)
        self.assertEqual(restored.scene_name, cfg.scene_name)
        self.assertEqual(restored.frequency_hz, cfg.frequency_hz)
        self.assertEqual(restored.tx_power_dbm, cfg.tx_power_dbm)
        self.assertEqual(restored.antenna_type, cfg.antenna_type)
        self.assertEqual(restored.antenna_pattern, cfg.antenna_pattern)
        self.assertEqual(restored.cell_size_tuple, cfg.cell_size_tuple)


if __name__ == "__main__":
    unittest.main()
