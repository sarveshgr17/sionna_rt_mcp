"""Radio Map Result Data Model and Metric Extraction.

This module defines RadioMapResult, which encapsulates the numerical outputs and
simulation metadata extracted from NVIDIA Sionna RT's RadioMapSolver.

Key components:
- RadioMapResult: Comprehensive result container storing 2D spatial matrices,
  Cartesian coordinates, coverage metrics, and simulation metadata.
- Extraction and validation from raw Sionna RT RadioMap objects.
- Rigorous mathematical conversions:
  - RSS: Watts -> dBm (10 * log10(P_W) + 30) with exact -inf handling for zero power.
  - Path Gain: Linear -> dB (10 * log10(g)) with exact -inf handling for zero gain.
  - Rejection of invalid, negative, NaN, or dimensionally incompatible tensors.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    import numpy as np
except (ImportError, ModuleNotFoundError):
    np = None  # Handled with informative errors if numpy is missing

# Ensure repository root and src directory are on sys.path
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


def _to_numpy_array(tensor: Any, name: str) -> "np.ndarray":
    """Convert a tensor (Dr.Jit, Mitsuba, PyTorch, TensorFlow, or NumPy) to a NumPy ndarray."""
    if np is None:
        raise RuntimeError("NumPy is required for RadioMapResult processing, but is not installed.")

    if isinstance(tensor, np.ndarray):
        return np.array(tensor, copy=True)

    # Handle objects with a .numpy() method (PyTorch / TensorFlow)
    if hasattr(tensor, "numpy") and callable(tensor.numpy):
        try:
            return np.array(tensor.numpy(), copy=True)
        except Exception as exc:
            raise ValueError(f"Failed to convert '{name}' using .numpy(): {exc}") from exc

    # Handle Dr.Jit / Mitsuba array types or Python sequences
    try:
        return np.asarray(tensor)
    except Exception as exc:
        raise ValueError(f"Failed to convert '{name}' to NumPy ndarray: {exc}") from exc


@dataclass
class RadioMapResult:
    """Container for 2D spatial radio-map simulation results and metadata."""

    # -------------------------------------------------------------------------
    # 1. Metadata
    # -------------------------------------------------------------------------
    scene_name: str
    frequency_hz: float
    tx_position: Tuple[float, float, float]
    tx_power_dbm: float
    tx_orientation_deg: Tuple[float, float, float]
    antenna_type: str
    antenna_pattern: str
    polarization: str
    measurement_height: float
    region_bounds: Tuple[float, float, float, float]  # (x_min, x_max, y_min, y_max)
    cell_size: Tuple[float, float]  # (dx, dy) in meters
    grid_dimensions: Tuple[int, int]  # (num_cells_y, num_cells_x)
    solver_parameters: Dict[str, Any]
    simulation_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    backend_variant: str = "unknown"

    # -------------------------------------------------------------------------
    # 2. Numerical Arrays
    # -------------------------------------------------------------------------
    path_gain_linear: Any = None  # 2D np.ndarray [Ny, Nx]
    path_gain_db: Any = None  # 2D np.ndarray [Ny, Nx]
    rss_watts: Any = None  # 2D np.ndarray [Ny, Nx]
    rss_dbm: Any = None  # 2D np.ndarray [Ny, Nx]
    cell_centers: Any = None  # 3D np.ndarray [Ny, Nx, 3]
    x_coordinates: Any = None  # 1D or 2D np.ndarray
    y_coordinates: Any = None  # 1D or 2D np.ndarray

    def __post_init__(self) -> None:
        """Validate array dimensions and numerical integrity."""
        if np is None:
            raise RuntimeError("NumPy is required for RadioMapResult, but is not installed.")

        # Ensure arrays are valid numpy ndarrays
        if self.path_gain_linear is None or self.rss_watts is None or self.cell_centers is None:
            raise ValueError("path_gain_linear, rss_watts, and cell_centers must be provided.")

        ny, nx = self.grid_dimensions
        if ny <= 0 or nx <= 0:
            raise ValueError(f"Grid dimensions must be positive, got ({ny}, {nx}).")

        if self.path_gain_linear.shape != (ny, nx):
            raise ValueError(
                f"path_gain_linear shape {self.path_gain_linear.shape} does not match grid dimensions ({ny}, {nx})."
            )
        if self.rss_watts.shape != (ny, nx):
            raise ValueError(
                f"rss_watts shape {self.rss_watts.shape} does not match grid dimensions ({ny}, {nx})."
            )
        if self.cell_centers.shape != (ny, nx, 3):
            raise ValueError(
                f"cell_centers shape {self.cell_centers.shape} does not match expected ({ny}, {nx}, 3)."
            )

        # Derive path_gain_db if omitted
        if self.path_gain_db is None and self.path_gain_linear is not None:
            pg_db = np.full((ny, nx), -np.inf, dtype=np.float64)
            pos_gain_mask = self.path_gain_linear > 0.0
            with np.errstate(divide="ignore"):
                pg_db[pos_gain_mask] = 10.0 * np.log10(self.path_gain_linear[pos_gain_mask])
            self.path_gain_db = pg_db

        # Derive rss_dbm if omitted
        if self.rss_dbm is None and self.rss_watts is not None:
            r_dbm = np.full((ny, nx), -np.inf, dtype=np.float64)
            pos_rss_mask = self.rss_watts > 0.0
            with np.errstate(divide="ignore"):
                r_dbm[pos_rss_mask] = 10.0 * np.log10(self.rss_watts[pos_rss_mask]) + 30.0
            self.rss_dbm = r_dbm

        # Derive x_coordinates and y_coordinates from cell_centers if omitted
        if (self.x_coordinates is None or self.y_coordinates is None) and self.cell_centers is not None:
            x_grid = self.cell_centers[:, :, 0]
            y_grid = self.cell_centers[:, :, 1]
            x_separable = bool(np.allclose(x_grid, x_grid[0:1, :], atol=1e-4))
            y_separable = bool(np.allclose(y_grid, y_grid[:, 0:1], atol=1e-4))
            if self.x_coordinates is None:
                if x_separable:
                    self.x_coordinates = np.array(x_grid[0, :], dtype=np.float64, copy=True)
                else:
                    self.x_coordinates = np.array(x_grid, dtype=np.float64, copy=True)
            if self.y_coordinates is None:
                if y_separable:
                    self.y_coordinates = np.array(y_grid[:, 0], dtype=np.float64, copy=True)
                else:
                    self.y_coordinates = np.array(y_grid, dtype=np.float64, copy=True)

    # -------------------------------------------------------------------------
    # Summary Metrics & Property Accessors
    # -------------------------------------------------------------------------
    @property
    def num_cells(self) -> int:
        """Total number of evaluation cells in the grid."""
        return self.grid_dimensions[0] * self.grid_dimensions[1]

    @property
    def valid_cells_count(self) -> int:
        """Count of cells with finite received power (RSS > 0 Watts)."""
        if self.rss_dbm is None:
            return 0
        return int(np.count_nonzero(np.isfinite(self.rss_dbm)))

    @property
    def zero_power_cells_count(self) -> int:
        """Count of unreached cells receiving zero RF power."""
        if self.rss_watts is None:
            return 0
        return int(np.count_nonzero(self.rss_watts == 0.0))

    @property
    def min_rss_dbm(self) -> Optional[float]:
        """Minimum finite received power across the grid in dBm."""
        if self.rss_dbm is None:
            return None
        valid_mask = np.isfinite(self.rss_dbm)
        if not np.any(valid_mask):
            return None
        return float(np.min(self.rss_dbm[valid_mask]))

    @property
    def max_rss_dbm(self) -> Optional[float]:
        """Maximum finite received power across the grid in dBm."""
        if self.rss_dbm is None:
            return None
        valid_mask = np.isfinite(self.rss_dbm)
        if not np.any(valid_mask):
            return None
        return float(np.max(self.rss_dbm[valid_mask]))

    @property
    def mean_rss_dbm(self) -> Optional[float]:
        """Average finite received power across the grid in dBm."""
        if self.rss_dbm is None:
            return None
        valid_mask = np.isfinite(self.rss_dbm)
        if not np.any(valid_mask):
            return None
        return float(np.mean(self.rss_dbm[valid_mask]))

    @property
    def coverage_percentage(self) -> float:
        """Percentage of grid cells receiving non-zero RF power."""
        if self.num_cells == 0:
            return 0.0
        return float((self.valid_cells_count / self.num_cells) * 100.0)

    def coverage_above_threshold(self, threshold_dbm: float = -100.0) -> float:
        """Percentage of grid cells with RSS >= threshold_dbm."""
        if self.num_cells == 0 or self.rss_dbm is None:
            return 0.0
        above_count = np.count_nonzero(np.isfinite(self.rss_dbm) & (self.rss_dbm >= threshold_dbm))
        return float((above_count / self.num_cells) * 100.0)

    # -------------------------------------------------------------------------
    # Factory Extraction Method from Sionna RT Raw Object
    # -------------------------------------------------------------------------
    @classmethod
    def from_raw_radio_map(
        cls,
        raw_radio_map: Any,
        config: RadioMapConfig,
        backend_variant: str = "unknown",
        region_bounds: Optional[Tuple[float, float, float, float]] = None,
    ) -> "RadioMapResult":
        """Extract and validate numerical data from a raw Sionna RT RadioMap object.

        Args:
            raw_radio_map: Raw object returned by Sionna RT's RadioMapSolver.
            config: RadioMapConfig used to produce the simulation.
            backend_variant: Active Mitsuba backend variant.
            region_bounds: Optional (x_min, x_max, y_min, y_max) bounds.

        Returns:
            Fully populated, validated RadioMapResult instance.

        Raises:
            ValueError: If tensor shapes, coordinates, or values are invalid.
            AttributeError: If required properties are missing on raw_radio_map.
        """
        if np is None:
            raise RuntimeError("NumPy is required to extract radio map results.")

        # 1. Validate required raw object properties
        for prop in ("path_gain", "rss", "cell_centers"):
            if not hasattr(raw_radio_map, prop):
                raise AttributeError(
                    f"Raw radio map object lacks required property '{prop}'."
                )

        # 2. Convert raw tensors to NumPy arrays
        raw_path_gain = _to_numpy_array(raw_radio_map.path_gain, "path_gain")
        raw_rss = _to_numpy_array(raw_radio_map.rss, "rss")
        raw_cell_centers = _to_numpy_array(raw_radio_map.cell_centers, "cell_centers")

        # 3. Check for NaNs and Infs in raw data
        if np.isnan(raw_path_gain).any() or np.isnan(raw_rss).any() or np.isnan(raw_cell_centers).any():
            raise ValueError("NaN values detected in raw Sionna RT simulation outputs.")
        if np.isinf(raw_path_gain).any() or np.isinf(raw_rss).any() or np.isinf(raw_cell_centers).any():
            raise ValueError("Infinite values detected in raw Sionna RT linear simulation outputs.")

        # 4. Dimension & Single-Transmitter Verification
        # Documented shape: [1, num_cells_y, num_cells_x] or [num_cells_y, num_cells_x]
        if raw_path_gain.ndim == 3:
            if raw_path_gain.shape[0] != 1:
                raise ValueError(
                    f"Expected single transmitter radio map (first dim == 1), got {raw_path_gain.shape[0]} transmitters."
                )
            path_gain_2d = raw_path_gain[0]
        elif raw_path_gain.ndim == 2:
            path_gain_2d = raw_path_gain
        else:
            raise ValueError(
                f"Invalid path_gain array shape: {raw_path_gain.shape}. Expected [1, Ny, Nx] or [Ny, Nx]."
            )

        if raw_rss.ndim == 3:
            if raw_rss.shape[0] != 1:
                raise ValueError(
                    f"Expected single transmitter RSS array (first dim == 1), got {raw_rss.shape[0]} transmitters."
                )
            rss_2d = raw_rss[0]
        elif raw_rss.ndim == 2:
            rss_2d = raw_rss
        else:
            raise ValueError(
                f"Invalid rss array shape: {raw_rss.shape}. Expected [1, Ny, Nx] or [Ny, Nx]."
            )

        # cell_centers shape: [Ny, Nx, 3]
        if raw_cell_centers.ndim != 3 or raw_cell_centers.shape[-1] != 3:
            raise ValueError(
                f"Invalid cell_centers shape: {raw_cell_centers.shape}. Expected [Ny, Nx, 3]."
            )

        ny, nx = path_gain_2d.shape
        if ny == 0 or nx == 0:
            raise ValueError("Radio map grid is empty (0 cells).")

        if rss_2d.shape != (ny, nx):
            raise ValueError(
                f"Shape mismatch: path_gain is ({ny}, {nx}) but rss is {rss_2d.shape}."
            )
        if raw_cell_centers.shape[:2] != (ny, nx):
            raise ValueError(
                f"Shape mismatch: grid is ({ny}, {nx}) but cell_centers is {raw_cell_centers.shape[:2]}."
            )

        # 5. Numerical Validity Checks (Negative Values)
        if np.any(path_gain_2d < 0.0):
            min_gain = float(np.min(path_gain_2d))
            raise ValueError(f"Invalid negative path gain detected: min={min_gain}.")

        if np.any(rss_2d < 0.0):
            min_rss = float(np.min(rss_2d))
            raise ValueError(f"Invalid negative RSS power detected: min={min_rss} Watts.")

        # 6. Exact Unit Conversions
        # Path Gain: Linear -> dB (10 * log10(gain)). Zero gain -> -inf
        path_gain_db = np.full((ny, nx), -np.inf, dtype=np.float64)
        pos_gain_mask = path_gain_2d > 0.0
        with np.errstate(divide="ignore"):
            path_gain_db[pos_gain_mask] = 10.0 * np.log10(path_gain_2d[pos_gain_mask])

        # RSS: Watts -> dBm (10 * log10(P_W) + 30). Zero power -> -inf
        rss_dbm = np.full((ny, nx), -np.inf, dtype=np.float64)
        pos_rss_mask = rss_2d > 0.0
        with np.errstate(divide="ignore"):
            rss_dbm[pos_rss_mask] = 10.0 * np.log10(rss_2d[pos_rss_mask]) + 30.0

        # 7. Coordinate Extraction
        # cell_centers: [Ny, Nx, 3] where [..., 0]=X, [..., 1]=Y, [..., 2]=Z
        x_grid = raw_cell_centers[:, :, 0]
        y_grid = raw_cell_centers[:, :, 1]
        z_grid = raw_cell_centers[:, :, 2]

        # Check if coordinates form an axis-aligned separable rectangular grid
        x_separable = bool(np.allclose(x_grid, x_grid[0:1, :], atol=1e-4))
        y_separable = bool(np.allclose(y_grid, y_grid[:, 0:1], atol=1e-4))

        if x_separable and y_separable:
            x_coordinates = np.array(x_grid[0, :], copy=True)
            y_coordinates = np.array(y_grid[:, 0], copy=True)
        else:
            # Preserve full 2D coordinate matrices if non-separable
            x_coordinates = np.array(x_grid, copy=True)
            y_coordinates = np.array(y_grid, copy=True)

        # Actual measurement plane height
        actual_height = float(np.mean(z_grid))

        # Resolution and bounds
        dx, dy = config.cell_size_tuple
        if region_bounds is None:
            # Fallback bounds from coordinate limits
            min_x = float(np.min(x_grid)) - dx / 2.0
            max_x = float(np.max(x_grid)) + dx / 2.0
            min_y = float(np.min(y_grid)) - dy / 2.0
            max_y = float(np.max(y_grid)) + dy / 2.0
            region_bounds = (min_x, max_x, min_y, max_y)

        solver_params = {
            "samples_per_tx": config.samples_per_tx,
            "max_depth": config.max_depth,
            "seed": config.seed,
            "los": config.los,
            "specular_reflection": config.specular_reflection,
            "diffraction": config.diffraction,
            "scattering": config.scattering,
        }

        return cls(
            scene_name=config.scene_name,
            frequency_hz=config.frequency_hz,
            tx_position=config.tx_position,
            tx_power_dbm=config.tx_power_dbm,
            tx_orientation_deg=config.tx_orientation_deg,
            antenna_type=config.antenna_type,
            antenna_pattern=config.antenna_pattern,
            polarization=config.polarization,
            measurement_height=actual_height,
            region_bounds=region_bounds,
            cell_size=(float(dx), float(dy)),
            grid_dimensions=(int(ny), int(nx)),
            solver_parameters=solver_params,
            simulation_timestamp=datetime.now(timezone.utc).isoformat(),
            backend_variant=backend_variant,
            path_gain_linear=path_gain_2d,
            path_gain_db=path_gain_db,
            rss_watts=rss_2d,
            rss_dbm=rss_dbm,
            cell_centers=raw_cell_centers,
            x_coordinates=x_coordinates,
            y_coordinates=y_coordinates,
        )

    # -------------------------------------------------------------------------
    # Dictionary Serialization
    # -------------------------------------------------------------------------
    def to_dict(self, include_full_arrays: bool = False) -> Dict[str, Any]:
        """Convert result metadata and metrics to a dictionary.

        Args:
            include_full_arrays: If True, serialize full numerical matrices.
                                If False, return summary statistics and spatial metadata.
        """
        payload: Dict[str, Any] = {
            "scene_name": self.scene_name,
            "frequency_hz": float(self.frequency_hz),
            "tx_position": list(self.tx_position),
            "tx_power_dbm": float(self.tx_power_dbm),
            "tx_orientation_deg": list(self.tx_orientation_deg),
            "antenna_type": self.antenna_type,
            "antenna_pattern": self.antenna_pattern,
            "polarization": self.polarization,
            "measurement_height": float(self.measurement_height),
            "region_bounds": list(self.region_bounds),
            "cell_size": list(self.cell_size),
            "grid_dimensions": list(self.grid_dimensions),
            "total_cells": self.num_cells,
            "valid_cells": self.valid_cells_count,
            "zero_power_cells": self.zero_power_cells_count,
            "coverage_percentage": self.coverage_percentage,
            "min_rss_dbm": self.min_rss_dbm,
            "mean_rss_dbm": self.mean_rss_dbm,
            "max_rss_dbm": self.max_rss_dbm,
            "solver_parameters": dict(self.solver_parameters),
            "simulation_timestamp": self.simulation_timestamp,
            "backend_variant": self.backend_variant,
        }

        if include_full_arrays:
            payload["path_gain_linear"] = self.path_gain_linear.tolist()
            payload["path_gain_db"] = self.path_gain_db.tolist()
            payload["rss_watts"] = self.rss_watts.tolist()
            payload["rss_dbm"] = self.rss_dbm.tolist()
            payload["cell_centers"] = self.cell_centers.tolist()
            payload["x_coordinates"] = self.x_coordinates.tolist()
            payload["y_coordinates"] = self.y_coordinates.tolist()

        return payload

