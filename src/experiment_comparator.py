"""Experiment Comparison and Spatial Difference Analysis.

This module provides ExperimentComparator and ComparisonResult for comparing two
previously saved radio-map simulation experiments.

Comparison Convention:
    Difference = Experiment B − Experiment A
    delta_rss_dbm = rss_dbm_B − rss_dbm_A
    delta_path_gain_db = path_gain_db_B − path_gain_db_A

Interpretation:
    - Positive (> 0): Experiment B has stronger received power / higher path gain.
    - Negative (< 0): Experiment B has weaker received power / lower path gain.
    - Zero (== 0): Both experiments have identical power / path gain.

Validation & Safeguards:
    - Enforces spatial compatibility: scene name, measurement height, grid dimensions,
      cell size, region bounds, cell centers, and coordinate vectors must align within
      documented floating-point tolerances.
    - Unreachable/invalid cells (-inf in either experiment) are marked as invalid (NaN in
      difference array) and excluded from statistical calculations.
    - Never substitutes an invented RF noise floor for -inf cells.
    - Diverging difference heatmaps centered at 0.0 dB with transparent masking of invalid cells.
    - Graceful fallback when matplotlib is unavailable.
    - Read-only operations ensure saved experiment data is never mutated.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import numpy as np
except (ImportError, ModuleNotFoundError):
    np = None

# Matplotlib availability detection
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    MATPLOTLIB_AVAILABLE = False
    plt = None
    mcolors = None

# Ensure repository root and src directory are on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_dir = os.path.abspath(os.path.dirname(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    from src.experiment_store import ExperimentStore
except (ImportError, ModuleNotFoundError):
    from experiment_store import ExperimentStore

try:
    from src.radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from radio_map_result import RadioMapResult


DEFAULT_COORDINATE_TOLERANCE = 1e-3  # 1 mm tolerance for floating-point coordinate alignment
DEFAULT_EQUALITY_TOLERANCE_DB = 0.01  # 0.01 dB tolerance for classifying values as equal


@dataclass
class ComparisonResult:
    """Encapsulates the numerical, statistical, and visual comparison between two experiments."""

    experiment_a_id: str
    experiment_b_id: str
    difference_convention: str  # "B - A (Experiment B minus Experiment A)"
    comparison_timestamp: str
    scene_name: str
    measurement_height: float
    grid_dimensions: Tuple[int, int]  # (Ny, Nx)
    cell_size: Tuple[float, float]  # (dx, dy)
    region_bounds: Tuple[float, float, float, float]  # (xmin, xmax, ymin, ymax)

    # Metadata dictionaries from ExperimentStore
    metadata_a: Dict[str, Any]
    metadata_b: Dict[str, Any]

    # Frequency comparison
    frequency_a_hz: float
    frequency_b_hz: float
    frequency_match: bool

    # Numerical difference matrices [Ny, Nx] (NaN for invalid / unreachable cells)
    delta_rss_dbm: Any
    delta_path_gain_db: Any
    valid_mask: Any  # Boolean 2D array [Ny, Nx] where True indicates finite values in both A and B

    # Spatial coordinates
    cell_centers: Any  # [Ny, Nx, 3]
    x_coordinates: Any  # 1D or 2D array
    y_coordinates: Any  # 1D or 2D array

    # Statistical summary metrics
    rss_metrics: Dict[str, Any]
    path_gain_metrics: Dict[str, Any]

    # Heatmaps
    heatmap_paths: Dict[str, str] = field(default_factory=dict)
    heatmaps_available: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self, include_full_arrays: bool = False) -> Dict[str, Any]:
        """Convert comparison summary and metrics to a JSON-serializable dictionary.

        Args:
            include_full_arrays: If True, serialize full numerical difference arrays
                                 with NaNs converted to null for JSON compliance.
        """
        payload: Dict[str, Any] = {
            "experiment_a_id": self.experiment_a_id,
            "experiment_b_id": self.experiment_b_id,
            "difference_convention": self.difference_convention,
            "comparison_timestamp": self.comparison_timestamp,
            "scene_name": self.scene_name,
            "measurement_height": float(self.measurement_height),
            "grid_dimensions": list(self.grid_dimensions),
            "cell_size": list(self.cell_size),
            "region_bounds": list(self.region_bounds),
            "frequency_a_hz": float(self.frequency_a_hz),
            "frequency_b_hz": float(self.frequency_b_hz),
            "frequency_match": bool(self.frequency_match),
            "rss_metrics": dict(self.rss_metrics),
            "path_gain_metrics": dict(self.path_gain_metrics),
            "heatmap_paths": dict(self.heatmap_paths),
            "heatmaps_available": dict(self.heatmaps_available),
            "metadata_a": {
                k: v for k, v in self.metadata_a.items() if k not in ("array_shapes", "heatmaps")
            },
            "metadata_b": {
                k: v for k, v in self.metadata_b.items() if k not in ("array_shapes", "heatmaps")
            },
        }

        if include_full_arrays and np is not None:
            # Helper to convert ndarray with NaNs into JSON-safe lists with None
            def _clean_array(arr: np.ndarray) -> List[Any]:
                flat = arr.tolist()
                return json.loads(
                    json.dumps(flat).replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
                )

            payload["delta_rss_dbm"] = _clean_array(np.asarray(self.delta_rss_dbm))
            payload["delta_path_gain_db"] = _clean_array(np.asarray(self.delta_path_gain_db))
            payload["valid_mask"] = np.asarray(self.valid_mask).tolist()
            payload["cell_centers"] = np.asarray(self.cell_centers).tolist()
            payload["x_coordinates"] = np.asarray(self.x_coordinates).tolist()
            payload["y_coordinates"] = np.asarray(self.y_coordinates).tolist()

        return payload


class ExperimentComparator:
    """Compares saved radio-map experiments, performs spatial validation, and generates difference heatmaps."""

    def __init__(
        self,
        experiment_store: ExperimentStore,
        output_dir: Optional[str] = None,
    ) -> None:
        """Initialize ExperimentComparator with an ExperimentStore instance.

        Args:
            experiment_store: Configured ExperimentStore instance for loading experiments.
            output_dir: Optional output directory for difference heatmaps. Defaults to
                        '<experiment_store.storage_dir>/comparisons'.
        """
        if not isinstance(experiment_store, ExperimentStore):
            raise ValueError(
                f"Expected experiment_store to be an ExperimentStore instance, got {type(experiment_store).__name__}."
            )

        self.experiment_store = experiment_store
        if output_dir is not None:
            self.output_dir = os.path.abspath(output_dir)
        else:
            self.output_dir = os.path.join(self.experiment_store.storage_dir, "comparisons")

    @staticmethod
    def _sanitize_for_filename(name: str) -> str:
        """Sanitize an experiment ID string for use in output filenames."""
        return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)

    # -------------------------------------------------------------------------
    # Spatial Compatibility Validation
    # -------------------------------------------------------------------------
    @classmethod
    def validate_spatial_compatibility(
        cls,
        result_a: RadioMapResult,
        result_b: RadioMapResult,
        coord_tolerance: float = DEFAULT_COORDINATE_TOLERANCE,
    ) -> None:
        """Verify that two experiments share an identical spatial evaluation grid.

        Validates:
            - scene_name (exact string match)
            - measurement_height (within coord_tolerance)
            - grid_dimensions (exact tuple match)
            - cell_size (within coord_tolerance)
            - region_bounds (within coord_tolerance)
            - cell_centers shape and values (within coord_tolerance)
            - x_coordinates shape and values (within coord_tolerance)
            - y_coordinates shape and values (within coord_tolerance)
            - Numerical array shapes matching grid_dimensions

        Raises:
            ValueError: If any spatial property fails to align, identifying the differing property.
            RuntimeError: If NumPy is unavailable.
        """
        if np is None:
            raise RuntimeError("NumPy is required for spatial validation, but is not installed.")

        # 1. Scene Name Validation
        if result_a.scene_name != result_b.scene_name:
            raise ValueError(
                f"Spatial mismatch: scene_name differs ('{result_a.scene_name}' vs '{result_b.scene_name}'). "
                f"Cannot compare experiments evaluated in different geometric environments."
            )

        # 2. Measurement Height Validation
        if abs(result_a.measurement_height - result_b.measurement_height) > coord_tolerance:
            raise ValueError(
                f"Spatial mismatch: measurement_height differs ({result_a.measurement_height} m vs "
                f"{result_b.measurement_height} m, tolerance={coord_tolerance})."
            )

        # 3. Grid Dimensions Validation
        if tuple(result_a.grid_dimensions) != tuple(result_b.grid_dimensions):
            raise ValueError(
                f"Spatial mismatch: grid_dimensions differ ({result_a.grid_dimensions} vs "
                f"{result_b.grid_dimensions}). Cannot compare arrays of different shapes."
            )

        # 4. Cell Size Validation
        if not np.allclose(result_a.cell_size, result_b.cell_size, atol=coord_tolerance):
            raise ValueError(
                f"Spatial mismatch: cell_size differs ({result_a.cell_size} vs "
                f"{result_b.cell_size}, tolerance={coord_tolerance})."
            )

        # 5. Region Bounds Validation
        if not np.allclose(result_a.region_bounds, result_b.region_bounds, atol=coord_tolerance):
            raise ValueError(
                f"Spatial mismatch: region_bounds differ ({result_a.region_bounds} vs "
                f"{result_b.region_bounds}, tolerance={coord_tolerance})."
            )

        # 6. Cell Centers Shape and Values Validation
        if result_a.cell_centers.shape != result_b.cell_centers.shape:
            raise ValueError(
                f"Spatial mismatch: cell_centers shape differs ({result_a.cell_centers.shape} vs "
                f"{result_b.cell_centers.shape})."
            )
        if not np.allclose(result_a.cell_centers, result_b.cell_centers, atol=coord_tolerance):
            raise ValueError(
                "Spatial mismatch: cell_centers coordinates do not align within tolerance. "
                "The evaluation measurement planes do not occupy identical 3D spatial points."
            )

        # 7. Coordinate Arrays (X and Y) Validation
        if result_a.x_coordinates.shape != result_b.x_coordinates.shape:
            raise ValueError(
                f"Spatial mismatch: x_coordinates shape differs ({result_a.x_coordinates.shape} vs "
                f"{result_b.x_coordinates.shape})."
            )
        if not np.allclose(result_a.x_coordinates, result_b.x_coordinates, atol=coord_tolerance):
            raise ValueError(
                "Spatial mismatch: x_coordinates do not align within tolerance."
            )

        if result_a.y_coordinates.shape != result_b.y_coordinates.shape:
            raise ValueError(
                f"Spatial mismatch: y_coordinates shape differs ({result_a.y_coordinates.shape} vs "
                f"{result_b.y_coordinates.shape})."
            )
        if not np.allclose(result_a.y_coordinates, result_b.y_coordinates, atol=coord_tolerance):
            raise ValueError(
                "Spatial mismatch: y_coordinates do not align within tolerance."
            )

        # 8. Numerical Matrix Shapes Validation
        expected_shape = tuple(result_a.grid_dimensions)
        for name, arr in [
            ("A.path_gain_db", result_a.path_gain_db),
            ("A.rss_dbm", result_a.rss_dbm),
            ("B.path_gain_db", result_b.path_gain_db),
            ("B.rss_dbm", result_b.rss_dbm),
        ]:
            if arr.shape != expected_shape:
                raise ValueError(
                    f"Spatial mismatch: {name} shape {arr.shape} does not match grid_dimensions {expected_shape}."
                )

    # -------------------------------------------------------------------------
    # Statistical Metric Extraction
    # -------------------------------------------------------------------------
    @staticmethod
    def _calculate_metrics(
        delta_arr: "np.ndarray",
        valid_mask: "np.ndarray",
        total_cells: int,
        equality_tolerance: float = DEFAULT_EQUALITY_TOLERANCE_DB,
    ) -> Dict[str, Any]:
        """Compute statistical metrics strictly over valid (mutually finite) cells."""
        valid_count = int(np.count_nonzero(valid_mask))
        invalid_count = total_cells - valid_count
        valid_percentage = float((valid_count / total_cells) * 100.0) if total_cells > 0 else 0.0

        if valid_count == 0:
            return {
                "total_cells": total_cells,
                "valid_cells": 0,
                "invalid_cells": total_cells,
                "valid_cells_percentage": 0.0,
                "min_difference": None,
                "max_difference": None,
                "mean_difference": None,
                "std_difference": None,
                "b_stronger_cells": 0,
                "b_weaker_cells": 0,
                "equal_cells": 0,
            }

        valid_vals = delta_arr[valid_mask]
        b_stronger = int(np.count_nonzero(valid_vals > equality_tolerance))
        b_weaker = int(np.count_nonzero(valid_vals < -equality_tolerance))
        equal_cells = int(np.count_nonzero(np.abs(valid_vals) <= equality_tolerance))

        return {
            "total_cells": total_cells,
            "valid_cells": valid_count,
            "invalid_cells": invalid_count,
            "valid_cells_percentage": valid_percentage,
            "min_difference": float(np.min(valid_vals)),
            "max_difference": float(np.max(valid_vals)),
            "mean_difference": float(np.mean(valid_vals)),
            "std_difference": float(np.std(valid_vals)),
            "b_stronger_cells": b_stronger,
            "b_weaker_cells": b_weaker,
            "equal_cells": equal_cells,
        }

    # -------------------------------------------------------------------------
    # Visualization: Diverging Difference Heatmaps
    # -------------------------------------------------------------------------
    @classmethod
    def plot_difference_heatmap(
        cls,
        delta_arr: "np.ndarray",
        valid_mask: "np.ndarray",
        x_coordinates: "np.ndarray",
        y_coordinates: "np.ndarray",
        cell_size: Tuple[float, float],
        output_path: str,
        metric_title: str,
        unit_label: str,
        exp_a_id: str,
        exp_b_id: str,
        scene_name: str,
        measurement_height: float,
        cmap_name: str = "coolwarm",
    ) -> str:
        """Render and save a diverging difference heatmap centered at zero.

        Args:
            delta_arr: 2D array of differences with NaNs for invalid cells.
            valid_mask: Boolean mask indicating valid mutually finite cells.
            x_coordinates: 1D or 2D X coordinates.
            y_coordinates: 1D or 2D Y coordinates.
            cell_size: (dx, dy) in meters.
            output_path: Target PNG file path.
            metric_title: Display title for the metric ('Received Power Difference', 'Path Gain Difference').
            unit_label: Physical unit ('dB').
            exp_a_id: Experiment A ID (baseline).
            exp_b_id: Experiment B ID (new/modified).
            scene_name: Sionna RT scene name.
            measurement_height: Measurement plane height in meters.
            cmap_name: Matplotlib diverging colormap name.

        Returns:
            Absolute saved file path.

        Raises:
            RuntimeError: If matplotlib or numpy is not installed.
        """
        if not MATPLOTLIB_AVAILABLE or plt is None:
            raise RuntimeError(
                "Heatmap visualization requires 'matplotlib', but it is not installed."
            )

        if np is None:
            raise RuntimeError("NumPy is required for heatmap visualization.")

        # Create masked array where invalid cells are masked
        masked_data = np.ma.masked_where(~valid_mask, delta_arr)

        fig, ax = plt.subplots(figsize=(9, 7), dpi=150)

        # Configure diverging colormap with light gray for invalid/unreachable cells
        cmap = plt.get_cmap(cmap_name).copy()
        cmap.set_bad(color="#dcdcdc")

        # Determine symmetric color scale centered at 0.0
        valid_vals = delta_arr[valid_mask]
        if len(valid_vals) > 0:
            max_abs = float(np.max(np.abs(valid_vals)))
            if max_abs <= 0.0 or not np.isfinite(max_abs):
                max_abs = 1.0
        else:
            max_abs = 1.0

        vmin = -max_abs
        vmax = max_abs

        # Render: check whether regular separable 1D or full 2D coordinate matrices
        if (
            hasattr(x_coordinates, "ndim")
            and x_coordinates.ndim == 1
            and hasattr(y_coordinates, "ndim")
            and y_coordinates.ndim == 1
        ):
            dx, dy = cell_size
            x_min = float(x_coordinates[0]) - dx / 2.0
            x_max = float(x_coordinates[-1]) + dx / 2.0
            y_min = float(y_coordinates[0]) - dy / 2.0
            y_max = float(y_coordinates[-1]) + dy / 2.0
            extent = [min(x_min, x_max), max(x_min, x_max), min(y_min, y_max), max(y_min, y_max)]
            im = ax.imshow(
                masked_data,
                origin="lower",
                extent=extent,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                aspect="equal",
                interpolation="nearest",
            )
        else:
            # Non-separable coordinate grid
            im = ax.pcolormesh(
                np.asarray(x_coordinates),
                np.asarray(y_coordinates),
                masked_data,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                shading="auto",
            )
            ax.set_aspect("equal")

        # Diverging colorbar with visible 0 reference and B-A label
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(f"Δ {metric_title} [B − A] ({unit_label})", fontsize=11, fontweight="bold")

        ax.set_xlabel("X Position (m)", fontsize=11)
        ax.set_ylabel("Y Position (m)", fontsize=11)
        ax.set_title(
            f"{metric_title} (Exp B − Exp A)\n"
            f"Exp B: {exp_b_id} | Exp A: {exp_a_id}\n"
            f"Scene: {scene_name} | Height: {measurement_height:.1f} m",
            fontsize=11,
            fontweight="bold",
        )
        ax.grid(True, linestyle=":", alpha=0.4, color="gray")

        abs_output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)
        fig.savefig(abs_output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return abs_output_path

    # -------------------------------------------------------------------------
    # Core Comparison Execution
    # -------------------------------------------------------------------------
    def compare_experiments(
        self,
        experiment_a_id: str,
        experiment_b_id: str,
        generate_heatmaps: bool = True,
        coord_tolerance: float = DEFAULT_COORDINATE_TOLERANCE,
        equality_tolerance_db: float = DEFAULT_EQUALITY_TOLERANCE_DB,
    ) -> ComparisonResult:
        """Compare two saved experiments and calculate spatial differences (B - A).

        Args:
            experiment_a_id: Identifier of baseline experiment A.
            experiment_b_id: Identifier of new/modified experiment B.
            generate_heatmaps: Whether to render and save difference heatmaps.
            coord_tolerance: Spatial coordinate alignment tolerance in meters.
            equality_tolerance_db: Threshold in dB to consider differences equal to zero.

        Returns:
            ComparisonResult instance containing difference arrays, validity masks,
            statistical metrics, and optional heatmap paths.

        Raises:
            FileNotFoundError: If either experiment ID does not exist in storage.
            ValueError: If spatial grids do not align or numerical dimensions are invalid.
            RuntimeError: If NumPy is unavailable.
        """
        if np is None:
            raise RuntimeError("NumPy is required for experiment comparison, but is not installed.")

        # 1. Load experiment results via ExperimentStore (read-only)
        result_a = self.experiment_store.load_experiment(experiment_a_id)
        result_b = self.experiment_store.load_experiment(experiment_b_id)

        meta_a = self.experiment_store.get_experiment_details(experiment_a_id)
        meta_b = self.experiment_store.get_experiment_details(experiment_b_id)

        # 2. Strict Spatial Compatibility Verification
        self.validate_spatial_compatibility(result_a, result_b, coord_tolerance=coord_tolerance)

        # 3. Frequency Analysis (Preserved and reported, not rejected)
        freq_a = float(result_a.frequency_hz)
        freq_b = float(result_b.frequency_hz)
        frequency_match = bool(math.isclose(freq_a, freq_b, rel_tol=1e-5))

        # 4. Difference Calculations with Exact -inf Handling
        # B - A convention
        rss_a = np.asarray(result_a.rss_dbm)
        rss_b = np.asarray(result_b.rss_dbm)
        gain_a = np.asarray(result_a.path_gain_db)
        gain_b = np.asarray(result_b.path_gain_db)

        ny, nx = result_a.grid_dimensions
        total_cells = ny * nx

        # Validity mask: cell is valid IF AND ONLY IF both A and B are finite (RF reached in both)
        valid_mask_rss = np.isfinite(rss_a) & np.isfinite(rss_b)
        valid_mask_gain = np.isfinite(gain_a) & np.isfinite(gain_b)
        valid_mask = valid_mask_rss & valid_mask_gain

        # Allocate difference arrays initialized to NaN
        delta_rss_dbm = np.full((ny, nx), np.nan, dtype=np.float64)
        delta_path_gain_db = np.full((ny, nx), np.nan, dtype=np.float64)

        # Compute differences only across mutually valid cells
        delta_rss_dbm[valid_mask] = rss_b[valid_mask] - rss_a[valid_mask]
        delta_path_gain_db[valid_mask] = gain_b[valid_mask] - gain_a[valid_mask]

        # 5. Summary Metrics Extraction
        rss_metrics = self._calculate_metrics(
            delta_rss_dbm, valid_mask, total_cells, equality_tolerance=equality_tolerance_db
        )
        path_gain_metrics = self._calculate_metrics(
            delta_path_gain_db, valid_mask, total_cells, equality_tolerance=equality_tolerance_db
        )

        # 6. Initialize Comparison Result
        comparison = ComparisonResult(
            experiment_a_id=experiment_a_id,
            experiment_b_id=experiment_b_id,
            difference_convention="B - A (Experiment B minus Experiment A)",
            comparison_timestamp=datetime.now(timezone.utc).isoformat(),
            scene_name=result_a.scene_name,
            measurement_height=float(result_a.measurement_height),
            grid_dimensions=result_a.grid_dimensions,
            cell_size=result_a.cell_size,
            region_bounds=result_a.region_bounds,
            metadata_a=meta_a,
            metadata_b=meta_b,
            frequency_a_hz=freq_a,
            frequency_b_hz=freq_b,
            frequency_match=frequency_match,
            delta_rss_dbm=delta_rss_dbm,
            delta_path_gain_db=delta_path_gain_db,
            valid_mask=valid_mask,
            cell_centers=result_a.cell_centers,
            x_coordinates=result_a.x_coordinates,
            y_coordinates=result_a.y_coordinates,
            rss_metrics=rss_metrics,
            path_gain_metrics=path_gain_metrics,
        )

        # 7. Difference Heatmaps Generation (Optional & Matplotlib Dependent)
        if generate_heatmaps:
            if MATPLOTLIB_AVAILABLE and plt is not None:
                os.makedirs(self.output_dir, exist_ok=True)
                clean_a = self._sanitize_for_filename(experiment_a_id)
                clean_b = self._sanitize_for_filename(experiment_b_id)

                rss_out = os.path.join(self.output_dir, f"diff_{clean_a}_vs_{clean_b}_rss_db.png")
                gain_out = os.path.join(self.output_dir, f"diff_{clean_a}_vs_{clean_b}_path_gain_db.png")

                self.plot_difference_heatmap(
                    delta_arr=delta_rss_dbm,
                    valid_mask=valid_mask,
                    x_coordinates=result_a.x_coordinates,
                    y_coordinates=result_a.y_coordinates,
                    cell_size=result_a.cell_size,
                    output_path=rss_out,
                    metric_title="Received Power Difference",
                    unit_label="dB",
                    exp_a_id=experiment_a_id,
                    exp_b_id=experiment_b_id,
                    scene_name=result_a.scene_name,
                    measurement_height=result_a.measurement_height,
                )

                self.plot_difference_heatmap(
                    delta_arr=delta_path_gain_db,
                    valid_mask=valid_mask,
                    x_coordinates=result_a.x_coordinates,
                    y_coordinates=result_a.y_coordinates,
                    cell_size=result_a.cell_size,
                    output_path=gain_out,
                    metric_title="Path Gain Difference",
                    unit_label="dB",
                    exp_a_id=experiment_a_id,
                    exp_b_id=experiment_b_id,
                    scene_name=result_a.scene_name,
                    measurement_height=result_a.measurement_height,
                )

                comparison.heatmap_paths = {
                    "rss_diff_heatmap": rss_out,
                    "path_gain_diff_heatmap": gain_out,
                }
                comparison.heatmaps_available = {
                    "rss_diff_heatmap": True,
                    "path_gain_diff_heatmap": True,
                }
            else:
                comparison.heatmap_paths = {}
                comparison.heatmaps_available = {
                    "rss_diff_heatmap": False,
                    "path_gain_diff_heatmap": False,
                }
        else:
            comparison.heatmap_paths = {}
            comparison.heatmaps_available = {
                "rss_diff_heatmap": False,
                "path_gain_diff_heatmap": False,
            }

        return comparison

