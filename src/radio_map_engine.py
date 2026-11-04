"""Radio Map Simulation Engine wrapping NVIDIA Sionna RT.

This module implements RadioMapEngine, which is responsible for executing 2D spatial
radio map simulations using Sionna RT's RadioMapSolver.

Responsibilities:
1. Initialize the Mitsuba backend variant (CUDA OptiX or LLVM CPU fallback).
2. Load 3D scene geometry.
3. Set the carrier frequency.
4. Configure the transmitter antenna array (PlanarArray).
5. Instantiate and place exactly one transmitter (position, power, orientation).
6. Calculate the receiver measurement region (AUTO from geometry or MANUAL bounds).
7. Configure and invoke the native Sionna RT RadioMapSolver.
8. Return the raw radio-map result object for subsequent extraction.
"""

import inspect
import math
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Ensure repository root and src are on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_dir = os.path.abspath(os.path.dirname(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    from src.radio_map_config import RadioMapConfig
except (ImportError, ModuleNotFoundError):
    from radio_map_config import RadioMapConfig

# Reuse existing backend variant initialization from engine.py
try:
    from src.engine import ensure_mitsuba_variant
except (ImportError, ModuleNotFoundError):
    try:
        from engine import ensure_mitsuba_variant
    except (ImportError, ModuleNotFoundError):
        def ensure_mitsuba_variant() -> str:
            """Fallback Mitsuba variant probe."""
            import mitsuba as mi
            if mi.variant() is not None:
                return mi.variant()
            try:
                mi.set_variant("cuda_ad_mono_polarized")
                return "cuda_ad_mono_polarized"
            except Exception:
                mi.set_variant("llvm_ad_mono_polarized")
                return "llvm_ad_mono_polarized"


class RadioMapEngine:
    """Simulation engine that executes Sionna RT RadioMapSolver simulations.

    Encapsulates scene loading, transmitter placement, receiver measurement
    plane calculation, antenna array configuration, and ray-tracing execution.
    Does NOT create individual receiver objects or call point-to-point solvers.
    """

    def __init__(self, config: Optional[RadioMapConfig] = None) -> None:
        """Initialize the engine with an optional RadioMapConfig."""
        self.config: RadioMapConfig = config if config is not None else RadioMapConfig()
        self._backend: Optional[str] = None
        self._last_bounds: Optional[Tuple[float, float, float, float]] = None
        self._last_center: Optional[Tuple[float, float, float]] = None
        self._last_size: Optional[Tuple[float, float]] = None

    @property
    def backend(self) -> str:
        """Get the active Mitsuba backend variant, initializing it if necessary."""
        if self._backend is None:
            self._backend = ensure_mitsuba_variant()
        return self._backend

    @property
    def last_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """Return (x_min, x_max, y_min, y_max) from the most recent simulation run."""
        return self._last_bounds

    @property
    def last_center(self) -> Optional[Tuple[float, float, float]]:
        """Return (cx, cy, cz) from the most recent simulation run."""
        return self._last_center

    @property
    def last_size(self) -> Optional[Tuple[float, float]]:
        """Return (span_x, span_y) from the most recent simulation run."""
        return self._last_size

    def run(self, config: Optional[RadioMapConfig] = None) -> Any:
        """Execute the radio-map ray-tracing simulation.

        Args:
            config: Optional RadioMapConfig overriding the engine's default.

        Returns:
            The raw Sionna RT RadioMap object returned by RadioMapSolver.

        Raises:
            RuntimeError: If dependencies, scene loading, or solver fails.
            ValueError: If configuration, geometry, or parameters are invalid.
        """
        active_config = config if config is not None else self.config
        if not isinstance(active_config, RadioMapConfig):
            raise ValueError(f"Expected RadioMapConfig instance, got {type(active_config).__name__}.")

        # 1. Initialize Mitsuba computational backend
        _ = self.backend

        # 2. Import Sionna RT components
        try:
            import mitsuba as mi
            import sionna.rt as rt
            from sionna.rt import PlanarArray, RadioMapSolver, Transmitter, load_scene
        except ImportError as exc:
            raise RuntimeError(
                f"NVIDIA Sionna RT or Mitsuba is not installed or importable: {exc}. "
                "Please verify that 'sionna-rt>=2.2.0' and 'mitsuba' are installed."
            ) from exc

        # 3. Load scene geometry
        scene = self._load_scene(rt, load_scene, active_config.scene_name)

        # 4. Configure carrier frequency
        try:
            scene.frequency = float(active_config.frequency_hz)
        except Exception as exc:
            raise ValueError(f"Failed to set carrier frequency on scene: {exc}") from exc

        # 5. Configure transmitter antenna array
        self._configure_tx_array(scene, PlanarArray, active_config)

        # 6. Instantiate and add exactly one transmitter (no receivers)
        self._configure_transmitter(scene, mi, Transmitter, active_config)

        # 7. Compute receiver measurement region (center, size, and bounds)
        bounds, center, size = self._compute_region(scene, active_config)
        self._last_bounds = bounds
        self._last_center = center
        self._last_size = size

        # 8. Instantiate and execute RadioMapSolver
        radio_map = self._execute_solver(RadioMapSolver, scene, active_config, center, size)

        return radio_map

    def _load_scene(self, rt_module: Any, load_scene_fn: Any, scene_name: str) -> Any:
        """Load scene geometry from Sionna RT built-ins or an external file."""
        try:
            scene_source = getattr(rt_module.scene, scene_name, None)
            if scene_source is not None:
                scene = load_scene_fn(scene_source)
            else:
                scene = load_scene_fn(scene_name)

            if scene is None:
                raise RuntimeError(f"load_scene returned None for '{scene_name}'.")
            return scene
        except Exception as exc:
            raise RuntimeError(f"Scene loading failed for '{scene_name}': {exc}") from exc

    def _configure_tx_array(self, scene: Any, planar_array_cls: Any, config: RadioMapConfig) -> None:
        """Configure transmitter antenna array on scene.tx_array."""
        try:
            scene.tx_array = planar_array_cls(
                num_rows=config.num_rows,
                num_cols=config.num_cols,
                vertical_spacing=config.vertical_spacing,
                horizontal_spacing=config.horizontal_spacing,
                pattern=config.antenna_pattern,
                polarization=config.polarization,
            )
        except Exception as exc:
            raise ValueError(
                f"Failed to configure transmitter antenna array with pattern '{config.antenna_pattern}' "
                f"and polarization '{config.polarization}': {exc}"
            ) from exc

    def _configure_transmitter(
        self, scene: Any, mi_module: Any, transmitter_cls: Any, config: RadioMapConfig
    ) -> None:
        """Create and place exactly one transmitter node with orientation in radians."""
        try:
            position = mi_module.Point3f(*config.tx_position)
        except Exception as exc:
            raise ValueError(f"Failed to construct transmitter Point3f position: {exc}") from exc

        orientation_rad = list(config.tx_orientation_rad)

        try:
            # First attempt passing orientation in constructor
            tx = transmitter_cls(
                name=config.tx_name,
                position=position,
                power_dbm=config.tx_power_dbm,
                orientation=orientation_rad,
            )
        except TypeError:
            # Fallback if orientation is not accepted in constructor
            tx = transmitter_cls(
                name=config.tx_name,
                position=position,
                power_dbm=config.tx_power_dbm,
            )
            if hasattr(tx, "orientation"):
                tx.orientation = orientation_rad

        try:
            scene.add(tx)
        except Exception as exc:
            raise ValueError(f"Invalid transmitter configuration: failed to add transmitter to scene: {exc}") from exc

    def _extract_scene_bbox(
        self, scene: Any
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """Extract 3D bounding box ((min_x, min_y, min_z), (max_x, max_y, max_z)) from scene."""
        try:
            if hasattr(scene, "mi_scene") and hasattr(scene.mi_scene, "bbox"):
                mi_bbox = scene.mi_scene.bbox() if callable(scene.mi_scene.bbox) else scene.mi_scene.bbox
                min_pt = mi_bbox.min
                max_pt = mi_bbox.max
                min_tuple = (float(min_pt[0]), float(min_pt[1]), float(min_pt[2]))
                max_tuple = (float(max_pt[0]), float(max_pt[1]), float(max_pt[2]))
            elif hasattr(scene, "bbox"):
                bbox = scene.bbox() if callable(scene.bbox) else scene.bbox
                min_tuple = (float(bbox.min[0]), float(bbox.min[1]), float(bbox.min[2]))
                max_tuple = (float(bbox.max[0]), float(bbox.max[1]), float(bbox.max[2]))
            elif hasattr(scene, "bounding_box"):
                bbox = scene.bounding_box() if callable(scene.bounding_box) else scene.bounding_box
                min_tuple = (float(bbox.min[0]), float(bbox.min[1]), float(bbox.min[2]))
                max_tuple = (float(bbox.max[0]), float(bbox.max[1]), float(bbox.max[2]))
            else:
                raise AttributeError("Scene has neither 'mi_scene.bbox()' nor 'bbox'/'bounding_box'.")

            for coord in (*min_tuple, *max_tuple):
                if math.isnan(coord) or math.isinf(coord):
                    raise ValueError(f"Non-finite bounding box coordinate detected: {coord}")

            return min_tuple, max_tuple
        except Exception as exc:
            raise ValueError(f"Invalid scene geometry bounds: {exc}") from exc

    def _compute_region(
        self, scene: Any, config: RadioMapConfig
    ) -> Tuple[Tuple[float, float, float, float], Tuple[float, float, float], Tuple[float, float]]:
        """Compute the measurement region bounds, center, and size."""
        if config.region_mode == "auto":
            scene_bbox = self._extract_scene_bbox(scene)
            bounds = config.calculate_region_bounds(scene_bbox)
            center, size = config.calculate_center_and_size(scene_bbox)
        else:
            bounds = config.calculate_region_bounds()
            center, size = config.calculate_center_and_size()

        return bounds, center, size

    def _execute_solver(
        self,
        solver_cls: Any,
        scene: Any,
        config: RadioMapConfig,
        center: Tuple[float, float, float],
        size: Tuple[float, float],
    ) -> Any:
        """Instantiate and execute RadioMapSolver with verified parameters."""
        try:
            solver = solver_cls()
        except Exception as exc:
            raise RuntimeError(f"RadioMapSolver initialization failed: {exc}") from exc

        # Inspect solver parameters dynamically if supported
        sig = None
        try:
            sig = inspect.signature(solver.__call__)
        except (ValueError, TypeError):
            pass

        solver_kwargs: Dict[str, Any] = {
            "max_depth": config.max_depth,
            "samples_per_tx": config.samples_per_tx,
            "cell_size": list(config.cell_size_tuple),
            "center": list(center),
            "size": list(size),
            "orientation": [0.0, 0.0, 0.0],
            "los": config.los,
            "specular_reflection": config.specular_reflection,
            "diffraction": config.diffraction,
        }

        # Handle optional seed parameter
        if config.seed is not None:
            if sig is None or "seed" in sig.parameters:
                solver_kwargs["seed"] = config.seed

        # Handle diffuse reflection / scattering parameter verification
        if sig is not None:
            if "diffuse_reflection" in sig.parameters:
                solver_kwargs["diffuse_reflection"] = config.scattering
            elif "scattering" in sig.parameters:
                solver_kwargs["scattering"] = config.scattering
            elif config.scattering:
                raise ValueError(
                    "RadioMapConfig specifies scattering=True, but the installed Sionna RT "
                    "RadioMapSolver does not support 'diffuse_reflection' or 'scattering'."
                )
        else:
            # Fallback when signature is uninspectable (e.g. pybind11 callable)
            if config.scattering:
                solver_kwargs["diffuse_reflection"] = True

        try:
            # Call solver passing scene as first argument
            if sig is not None and "scene" in sig.parameters:
                radio_map = solver(scene=scene, **solver_kwargs)
            else:
                radio_map = solver(scene, **solver_kwargs)

            if radio_map is None:
                raise RuntimeError("RadioMapSolver returned None.")

            return radio_map
        except Exception as exc:
            raise RuntimeError(f"Radio-map computation failed during execution: {exc}") from exc
