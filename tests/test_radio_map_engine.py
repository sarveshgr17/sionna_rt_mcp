"""Unit and integration tests for RadioMapEngine (Phase 3)."""

import math
import os
import sys
from typing import Any, Dict, Tuple
import unittest
from unittest.mock import MagicMock, call, patch

# Ensure repository root and src directory are on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_dir = os.path.join(repo_root, "src")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    from radio_map_config import RadioMapConfig
except (ImportError, ModuleNotFoundError):
    from src.radio_map_config import RadioMapConfig

try:
    from radio_map_engine import RadioMapEngine
except (ImportError, ModuleNotFoundError):
    from src.radio_map_engine import RadioMapEngine


class TestRadioMapEngineUnit(unittest.TestCase):
    """Unit test suite for RadioMapEngine covering initialization, configuration, and execution."""

    def setUp(self):
        """Set up standard configuration and mock objects for unit tests."""
        self.config = RadioMapConfig(
            scene_name="simple_reflector",
            frequency_hz=3.5e9,
            tx_position=(0.0, -10.0, 5.0),
            tx_power_dbm=30.0,
            tx_orientation_deg=(45.0, 0.0, 0.0),
            antenna_type="directional",
            polarization="V",
            num_rows=2,
            num_cols=2,
            cell_size=1.0,
            receiver_height=1.5,
            samples_per_tx=100_000,
            max_depth=3,
        )
        self.engine = RadioMapEngine(self.config)

    # -------------------------------------------------------------------------
    # 1. Engine Initialization Tests
    # -------------------------------------------------------------------------
    def test_engine_initialization_defaults(self):
        """Verify default engine initialization."""
        engine = RadioMapEngine()
        self.assertIsInstance(engine.config, RadioMapConfig)
        self.assertIsNone(engine._backend)
        self.assertIsNone(engine.last_bounds)
        self.assertIsNone(engine.last_center)
        self.assertIsNone(engine.last_size)

    def test_engine_initialization_custom(self):
        """Verify custom configuration injection."""
        self.assertEqual(self.engine.config.scene_name, "simple_reflector")
        self.assertEqual(self.engine.config.antenna_pattern, "tr38901")

    def test_engine_run_invalid_config_type(self):
        """Verify TypeError/ValueError when non-RadioMapConfig is provided to run()."""
        with self.assertRaises(ValueError) as ctx:
            self.engine.run(config={"invalid": "dict"})  # type: ignore
        self.assertIn("Expected RadioMapConfig instance", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 2. Backend Property Tests
    # -------------------------------------------------------------------------
    @patch("radio_map_engine.ensure_mitsuba_variant", return_value="llvm_ad_mono_polarized")
    def test_backend_property_initialization(self, mock_variant):
        """Verify that engine.backend invokes ensure_mitsuba_variant and caches the result."""
        engine = RadioMapEngine(self.config)
        backend = engine.backend
        self.assertEqual(backend, "llvm_ad_mono_polarized")
        mock_variant.assert_called_once()

        # Second access should use cached variant
        cached_backend = engine.backend
        self.assertEqual(cached_backend, "llvm_ad_mono_polarized")
        self.assertEqual(mock_variant.call_count, 1)

    # -------------------------------------------------------------------------
    # 3. Scene Loading Tests
    # -------------------------------------------------------------------------
    def test_load_scene_builtin_source(self):
        """Verify loading built-in scene from rt.scene.<name>."""
        mock_rt = MagicMock()
        mock_scene_obj = MagicMock()
        mock_rt.scene.simple_reflector = "builtin_reflector_source"

        mock_load_fn = MagicMock(return_value=mock_scene_obj)

        scene = self.engine._load_scene(mock_rt, mock_load_fn, "simple_reflector")
        mock_load_fn.assert_called_once_with("builtin_reflector_source")
        self.assertEqual(scene, mock_scene_obj)

    def test_load_scene_custom_path(self):
        """Verify loading custom scene by string path when not in rt.scene."""
        mock_rt = MagicMock()
        mock_rt.scene = object()  # no custom_scene attribute
        mock_scene_obj = MagicMock()
        mock_load_fn = MagicMock(return_value=mock_scene_obj)

        scene = self.engine._load_scene(mock_rt, mock_load_fn, "custom_scene.xml")
        mock_load_fn.assert_called_once_with("custom_scene.xml")
        self.assertEqual(scene, mock_scene_obj)

    def test_load_scene_failure_raises_runtime_error(self):
        """Verify clear error when load_scene raises an exception."""
        mock_rt = MagicMock()
        mock_load_fn = MagicMock(side_effect=FileNotFoundError("Scene XML missing"))

        with self.assertRaises(RuntimeError) as ctx:
            self.engine._load_scene(mock_rt, mock_load_fn, "missing_scene.xml")
        self.assertIn("Scene loading failed for 'missing_scene.xml'", str(ctx.exception))

    def test_load_scene_none_result_raises_runtime_error(self):
        """Verify clear error when load_scene returns None."""
        mock_rt = MagicMock()
        mock_load_fn = MagicMock(return_value=None)

        with self.assertRaises(RuntimeError) as ctx:
            self.engine._load_scene(mock_rt, mock_load_fn, "corrupt_scene.xml")
        self.assertIn("load_scene returned None", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 4. Transmitter Configuration Tests
    # -------------------------------------------------------------------------
    def test_configure_transmitter_success(self):
        """Verify transmitter is created with Point3f, orientation radians, and added to scene."""
        mock_scene = MagicMock()
        mock_mi = MagicMock()
        mock_point = MagicMock()
        mock_mi.Point3f.return_value = mock_point

        mock_tx_cls = MagicMock()
        mock_tx_instance = MagicMock()
        mock_tx_cls.return_value = mock_tx_instance

        self.engine._configure_transmitter(mock_scene, mock_mi, mock_tx_cls, self.config)

        # Point3f created with config position
        mock_mi.Point3f.assert_called_once_with(0.0, -10.0, 5.0)

        # Transmitter created with radians: 45 deg -> pi/4 rad
        expected_rad = [float(math.radians(45.0)), 0.0, 0.0]
        mock_tx_cls.assert_called_once_with(
            name="tx",
            position=mock_point,
            power_dbm=30.0,
            orientation=expected_rad,
        )

        # Added to scene exactly once
        mock_scene.add.assert_called_once_with(mock_tx_instance)

    def test_configure_transmitter_orientation_fallback(self):
        """Verify fallback if Transmitter.__init__ rejects orientation argument."""
        mock_scene = MagicMock()
        mock_mi = MagicMock()

        mock_tx_instance = MagicMock()

        def mock_tx_init(*args, **kwargs):
            if "orientation" in kwargs:
                raise TypeError("unexpected keyword argument 'orientation'")
            return mock_tx_instance

        mock_tx_cls = MagicMock(side_effect=mock_tx_init)

        self.engine._configure_transmitter(mock_scene, mock_mi, mock_tx_cls, self.config)

        # Checked that orientation attribute was set
        self.assertEqual(mock_tx_instance.orientation, [float(math.radians(45.0)), 0.0, 0.0])
        mock_scene.add.assert_called_once_with(mock_tx_instance)

    def test_configure_transmitter_failure_raises_value_error(self):
        """Verify clear error when adding transmitter to scene fails."""
        mock_scene = MagicMock()
        mock_scene.add.side_effect = RuntimeError("Duplicate transmitter name")
        mock_mi = MagicMock()
        mock_tx_cls = MagicMock()

        with self.assertRaises(ValueError) as ctx:
            self.engine._configure_transmitter(mock_scene, mock_mi, mock_tx_cls, self.config)
        self.assertIn("Invalid transmitter configuration", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 5. Antenna Array Configuration Tests
    # -------------------------------------------------------------------------
    def test_configure_tx_array_success(self):
        """Verify PlanarArray is instantiated with mapped pattern and assigned to scene.tx_array."""
        mock_scene = MagicMock()
        mock_array_cls = MagicMock()
        mock_array_inst = MagicMock()
        mock_array_cls.return_value = mock_array_inst

        self.engine._configure_tx_array(mock_scene, mock_array_cls, self.config)

        mock_array_cls.assert_called_once_with(
            num_rows=2,
            num_cols=2,
            vertical_spacing=0.5,
            horizontal_spacing=0.5,
            pattern="tr38901",  # "directional" mapped to "tr38901"
            polarization="V",
        )
        self.assertEqual(mock_scene.tx_array, mock_array_inst)

    def test_configure_tx_array_failure_raises_value_error(self):
        """Verify clear error when PlanarArray configuration fails."""
        mock_scene = MagicMock()
        mock_array_cls = MagicMock(side_effect=ValueError("Unsupported polarization"))

        with self.assertRaises(ValueError) as ctx:
            self.engine._configure_tx_array(mock_scene, mock_array_cls, self.config)
        self.assertIn("Failed to configure transmitter antenna array", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 6. Receiver Measurement Region Tests: AUTO and MANUAL
    # -------------------------------------------------------------------------
    def test_auto_region_computation_from_mi_scene_bbox(self):
        """Verify AUTO region derivation from scene.mi_scene.bbox()."""
        mock_scene = MagicMock()
        mock_bbox = MagicMock()
        mock_bbox.min = [-10.0, -5.0, 0.0]
        mock_bbox.max = [10.0, 15.0, 10.0]
        mock_scene.mi_scene.bbox.return_value = mock_bbox

        auto_config = RadioMapConfig(
            region_mode="auto",
            auto_margin=10.0,
            auto_include_tx=True,
            tx_position=(0.0, -20.0, 5.0),
            receiver_height=1.5,
        )

        bounds, center, size = self.engine._compute_region(mock_scene, auto_config)

        # Expected X: [-10, 10] -> with margin 10: [-20, 20]
        # Expected Y: [-20 (tx), 15 (scene)] -> with margin 10: [-30, 25]
        self.assertEqual(bounds, (-20.0, 20.0, -30.0, 25.0))
        self.assertEqual(center, (0.0, -2.5, 1.5))
        self.assertEqual(size, (40.0, 55.0))

    def test_auto_region_computation_from_scene_bounding_box(self):
        """Verify AUTO region derivation from scene.bounding_box fallback."""
        mock_scene = MagicMock(spec=["bounding_box"])
        mock_bbox = MagicMock()
        mock_bbox.min = [-5.0, -5.0, 0.0]
        mock_bbox.max = [5.0, 5.0, 2.0]
        mock_scene.bounding_box.return_value = mock_bbox

        auto_config = RadioMapConfig(
            region_mode="auto",
            auto_margin=5.0,
            auto_include_tx=False,
            receiver_height=2.0,
        )

        bounds, center, size = self.engine._compute_region(mock_scene, auto_config)
        self.assertEqual(bounds, (-10.0, 10.0, -10.0, 10.0))
        self.assertEqual(center, (0.0, 0.0, 2.0))
        self.assertEqual(size, (20.0, 20.0))

    def test_auto_region_missing_bbox_raises_value_error(self):
        """Verify clear error when scene lacks bounding box attributes."""
        mock_scene = MagicMock(spec=[])  # Empty object with no bbox attrs

        auto_config = RadioMapConfig(region_mode="auto")
        with self.assertRaises(ValueError) as ctx:
            self.engine._compute_region(mock_scene, auto_config)
        self.assertIn("Invalid scene geometry bounds", str(ctx.exception))

    def test_manual_region_computation(self):
        """Verify MANUAL region ignores scene geometry and uses exact configured boundaries."""
        mock_scene = MagicMock()  # bbox should never be touched

        manual_config = RadioMapConfig(
            region_mode="manual",
            x_min=-25.0,
            x_max=25.0,
            y_min=-50.0,
            y_max=50.0,
            receiver_height=1.8,
            cell_size=2.0,
        )

        bounds, center, size = self.engine._compute_region(mock_scene, manual_config)
        self.assertEqual(bounds, (-25.0, 25.0, -50.0, 50.0))
        self.assertEqual(center, (0.0, 0.0, 1.8))
        self.assertEqual(size, (50.0, 100.0))
        mock_scene.mi_scene.bbox.assert_not_called()

    # -------------------------------------------------------------------------
    # 7. RadioMapSolver Argument Construction and Invocation Tests
    # -------------------------------------------------------------------------
    def test_execute_solver_argument_construction(self):
        """Verify RadioMapSolver is instantiated and called with exact parameters."""
        mock_radio_map = MagicMock()

        class DummySolver:
            def __init__(self):
                self.recorded_kwargs = None

            def __call__(self, scene, max_depth=3, samples_per_tx=1000, cell_size=None,
                         center=None, size=None, orientation=None, los=True,
                         specular_reflection=True, diffraction=True, seed=None):
                self.recorded_kwargs = {
                    "max_depth": max_depth,
                    "samples_per_tx": samples_per_tx,
                    "cell_size": cell_size,
                    "center": center,
                    "size": size,
                    "orientation": orientation,
                    "los": los,
                    "specular_reflection": specular_reflection,
                    "diffraction": diffraction,
                    "seed": seed,
                }
                return mock_radio_map

        solver_instance = DummySolver()
        mock_solver_cls = MagicMock(return_value=solver_instance)

        center = (0.0, 0.0, 1.5)
        size = (50.0, 50.0)
        mock_scene = MagicMock()

        result = self.engine._execute_solver(
            mock_solver_cls, mock_scene, self.config, center, size
        )

        self.assertEqual(result, mock_radio_map)
        mock_solver_cls.assert_called_once()

        # Check call arguments
        call_kwargs = solver_instance.recorded_kwargs
        self.assertIsNotNone(call_kwargs)
        self.assertEqual(call_kwargs["max_depth"], 3)
        self.assertEqual(call_kwargs["samples_per_tx"], 100_000)
        self.assertEqual(call_kwargs["cell_size"], [1.0, 1.0])
        self.assertEqual(call_kwargs["center"], [0.0, 0.0, 1.5])
        self.assertEqual(call_kwargs["size"], [50.0, 50.0])
        self.assertEqual(call_kwargs["orientation"], [0.0, 0.0, 0.0])
        self.assertTrue(call_kwargs["los"])
        self.assertTrue(call_kwargs["specular_reflection"])
        self.assertTrue(call_kwargs["diffraction"])

    def test_execute_solver_seed_injection(self):
        """Verify seed parameter is passed when configured."""
        config_with_seed = RadioMapConfig(seed=42)

        class DummySolverWithSeed:
            def __init__(self):
                self.recorded_seed = None

            def __call__(self, scene, seed=None, **kwargs):
                self.recorded_seed = seed
                return MagicMock()

        solver_instance = DummySolverWithSeed()
        mock_solver_cls = MagicMock(return_value=solver_instance)

        self.engine._execute_solver(
            mock_solver_cls, MagicMock(), config_with_seed, (0.0, 0.0, 1.5), (10.0, 10.0)
        )

        self.assertEqual(solver_instance.recorded_seed, 42)

    def test_execute_solver_diffuse_reflection_support(self):
        """Verify diffuse_reflection is passed when supported by solver signature."""
        config_scatter = RadioMapConfig(scattering=True)

        class DummySolverWithDiffuse:
            def __init__(self):
                self.recorded_diffuse = None

            def __call__(self, scene, diffuse_reflection=False, **kwargs):
                self.recorded_diffuse = diffuse_reflection
                return MagicMock()

        solver_instance = DummySolverWithDiffuse()
        mock_solver_cls = MagicMock(return_value=solver_instance)

        self.engine._execute_solver(
            mock_solver_cls, MagicMock(), config_scatter, (0.0, 0.0, 1.5), (10.0, 10.0)
        )

        self.assertTrue(solver_instance.recorded_diffuse)

    def test_execute_solver_unsupported_scattering_raises_error(self):
        """Verify clear error when scattering=True is requested but solver does not support it."""
        config_scatter = RadioMapConfig(scattering=True)

        mock_solver_cls = MagicMock()
        mock_solver_instance = MagicMock()
        mock_solver_cls.return_value = mock_solver_instance

        # Solver with no diffuse_reflection or scattering parameter
        def mock_call(scene, max_depth=3, **kwargs):
            return MagicMock()

        # Provide explicit signature without diffuse_reflection or scattering
        import inspect
        mock_call.__signature__ = inspect.Signature([
            inspect.Parameter("scene", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("max_depth", inspect.Parameter.KEYWORD_ONLY, default=3),
        ])
        mock_solver_instance.__call__ = mock_call

        with self.assertRaises(ValueError) as ctx:
            self.engine._execute_solver(
                mock_solver_cls, MagicMock(), config_scatter, (0.0, 0.0, 1.5), (10.0, 10.0)
            )
        self.assertIn("does not support 'diffuse_reflection' or 'scattering'", str(ctx.exception))

    def test_execute_solver_init_failure_raises_runtime_error(self):
        """Verify clear error when RadioMapSolver() initialization fails."""
        mock_solver_cls = MagicMock(side_effect=RuntimeError("OptiX pipeline error"))

        with self.assertRaises(RuntimeError) as ctx:
            self.engine._execute_solver(
                mock_solver_cls, MagicMock(), self.config, (0.0, 0.0, 1.5), (10.0, 10.0)
            )
        self.assertIn("RadioMapSolver initialization failed", str(ctx.exception))

    def test_execute_solver_computation_failure_raises_runtime_error(self):
        """Verify clear error when solver execution raises an error."""
        mock_solver_cls = MagicMock()
        mock_solver_instance = MagicMock(side_effect=RuntimeError("Out of GPU memory"))
        mock_solver_cls.return_value = mock_solver_instance

        with self.assertRaises(RuntimeError) as ctx:
            self.engine._execute_solver(
                mock_solver_cls, MagicMock(), self.config, (0.0, 0.0, 1.5), (10.0, 10.0)
            )
        self.assertIn("Radio-map computation failed during execution", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 8. Full End-to-End Mocked Run Test
    # -------------------------------------------------------------------------
    @patch("radio_map_engine.ensure_mitsuba_variant", return_value="llvm_ad_mono_polarized")
    def test_full_run_mocked_success(self, mock_variant):
        """Verify full run() workflow using comprehensive mocks."""
        mock_scene = MagicMock()
        mock_bbox = MagicMock()
        mock_bbox.min = [-20.0, -20.0, 0.0]
        mock_bbox.max = [20.0, 20.0, 10.0]
        mock_scene.mi_scene.bbox.return_value = mock_bbox

        mock_radio_map = MagicMock()

        # Mock rt and mitsuba modules
        mock_mi = MagicMock()
        mock_rt = MagicMock()
        mock_rt.scene.simple_reflector = "builtin_reflector"
        mock_load_scene = MagicMock(return_value=mock_scene)
        mock_planar_array = MagicMock()
        mock_tx_cls = MagicMock()
        mock_solver_cls = MagicMock()
        mock_solver_inst = MagicMock(return_value=mock_radio_map)
        mock_solver_cls.return_value = mock_solver_inst

        # Patch sys.modules for sionna.rt and mitsuba
        with patch.dict("sys.modules", {
            "mitsuba": mock_mi,
            "sionna": MagicMock(),
            "sionna.rt": mock_rt,
        }):
            mock_rt.load_scene = mock_load_scene
            mock_rt.PlanarArray = mock_planar_array
            mock_rt.Transmitter = mock_tx_cls
            mock_rt.RadioMapSolver = mock_solver_cls

            engine = RadioMapEngine(self.config)
            result = engine.run()

            # Verify return value
            self.assertEqual(result, mock_radio_map)

            # Verify frequency set
            self.assertEqual(mock_scene.frequency, 3.5e9)

            # Verify exactly one transmitter added and NO receiver added
            mock_scene.add.assert_called_once()

            # Verify recorded run state
            self.assertIsNotNone(engine.last_bounds)
            self.assertIsNotNone(engine.last_center)
            self.assertIsNotNone(engine.last_size)

    # -------------------------------------------------------------------------
    # 9. Real Integration Test Check
    # -------------------------------------------------------------------------
    def test_real_integration_test_availability(self):
        """Verify Sionna RT runtime availability without falsely claiming integration."""
        try:
            import mitsuba as mi
            import sionna.rt as rt
            sionna_available = True
        except ImportError:
            sionna_available = False

        if not sionna_available:
            # Expected in current Windows environment where sionna-rt is not installed
            self.skipTest(
                "NVIDIA Sionna RT is not installed in the current environment. "
                "Real integration test skipped; unit tests with mocks executed."
            )
        else:
            # If Sionna RT is installed, execute a real simulation
            engine = RadioMapEngine(RadioMapConfig(samples_per_tx=10_000, cell_size=2.0))
            real_rm = engine.run()
            self.assertIsNotNone(real_rm)


if __name__ == "__main__":
    unittest.main()
