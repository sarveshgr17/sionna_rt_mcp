"""Terminal output formatting and 2D spatial heatmap visualization for RadioMapResult.

This module provides RadioMapFormatter with:
1. Generation of publication-quality Received-Power (dBm) and Path-Gain (dB) heatmaps.
2. Accurate spatial Cartesian mapping using actual cell-center coordinates.
3. Transparent masking of zero-power / unreachable cells without inventing noise floors.
4. Clean terminal text summary formatting.
"""

import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import numpy as np
except (ImportError, ModuleNotFoundError):
    np = None

# Matplotlib availability detection
try:
    import matplotlib
    # Set non-interactive Agg backend to avoid GUI window popups in server/script environments
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    MATPLOTLIB_AVAILABLE = False
    plt = None  # type: ignore
    mcolors = None  # type: ignore

# Ensure repository root and src directory are on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_dir = os.path.abspath(os.path.dirname(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    from src.radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from radio_map_result import RadioMapResult


def _compute_plot_extent(result: RadioMapResult) -> Optional[List[float]]:
    """Compute [x_min, x_max, y_min, y_max] extent for imshow if grid is 1D separable."""
    if (
        hasattr(result.x_coordinates, "ndim")
        and result.x_coordinates.ndim == 1
        and hasattr(result.y_coordinates, "ndim")
        and result.y_coordinates.ndim == 1
    ):
        dx, dy = result.cell_size
        x_min = float(result.x_coordinates[0]) - dx / 2.0
        x_max = float(result.x_coordinates[-1]) + dx / 2.0
        y_min = float(result.y_coordinates[0]) - dy / 2.0
        y_max = float(result.y_coordinates[-1]) + dy / 2.0
        return [min(x_min, x_max), max(x_min, x_max), min(y_min, y_max), max(y_min, y_max)]
    return None


class RadioMapFormatter:
    """Formatter providing heatmap rendering and terminal summaries for RadioMapResult."""

    @staticmethod
    def is_visualization_available() -> bool:
        """Check whether matplotlib is installed and available for heatmap rendering."""
        return MATPLOTLIB_AVAILABLE

    @classmethod
    def plot_received_power_heatmap(
        cls,
        result: RadioMapResult,
        output_path: str,
        show_tx: bool = True,
        cmap_name: str = "viridis",
    ) -> str:
        """Render and save a Received Signal Strength (RSS in dBm) heatmap.

        Args:
            result: RadioMapResult containing spatial matrices and metadata.
            output_path: Destination PNG file path.
            show_tx: Whether to mark the transmitter coordinate with a star.
            cmap_name: Matplotlib colormap name.

        Returns:
            The saved absolute output path.

        Raises:
            RuntimeError: If matplotlib is not installed.
            ValueError: If numerical data is invalid.
        """
        if not MATPLOTLIB_AVAILABLE or plt is None:
            raise RuntimeError(
                "Heatmap visualization requires 'matplotlib', but it is not installed in the current environment."
            )

        if np is None:
            raise RuntimeError("NumPy is required for heatmap rendering.")

        # Create masked array where non-finite cells (-inf or NaN) are masked
        data = np.asarray(result.rss_dbm)
        masked_data = np.ma.masked_where(~np.isfinite(data), data)

        fig, ax = plt.subplots(figsize=(9, 7), dpi=150)

        # Colormap configuration with lightgray for unreachable / zero-power cells
        cmap = plt.get_cmap(cmap_name).copy()
        cmap.set_bad(color="#dcdcdc")  # Neutral light gray for unreached cells

        extent = _compute_plot_extent(result)
        if extent is not None:
            im = ax.imshow(
                masked_data,
                origin="lower",
                extent=extent,
                cmap=cmap,
                aspect="equal",
                interpolation="nearest",
            )
        else:
            # Fallback to pcolormesh for arbitrary non-separable coordinate grids
            x_coords = np.asarray(result.x_coordinates)
            y_coords = np.asarray(result.y_coordinates)
            im = ax.pcolormesh(
                x_coords,
                y_coords,
                masked_data,
                cmap=cmap,
                shading="auto",
            )
            ax.set_aspect("equal")

        # Colorbar with units
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Received Power (dBm)", fontsize=11, fontweight="bold")

        # Transmitter marker
        if show_tx and result.tx_position is not None:
            tx_x, tx_y, _ = result.tx_position
            ax.plot(
                tx_x,
                tx_y,
                marker="*",
                markersize=13,
                color="red",
                markeredgecolor="black",
                label=f"TX ({tx_x:.1f}, {tx_y:.1f})m",
                zorder=5,
            )
            ax.legend(loc="upper right", framealpha=0.85)

        # Labels and title
        freq_ghz = result.frequency_hz / 1e9
        ax.set_xlabel("X Position (m)", fontsize=11)
        ax.set_ylabel("Y Position (m)", fontsize=11)
        ax.set_title(
            f"Received Power (dBm)\nScene: {result.scene_name} | Freq: {freq_ghz:.2f} GHz | Height: {result.measurement_height:.1f} m",
            fontsize=12,
            fontweight="bold",
        )
        ax.grid(True, linestyle=":", alpha=0.4, color="gray")

        # Save to file
        abs_output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)
        fig.savefig(abs_output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return abs_output_path

    @classmethod
    def plot_path_gain_heatmap(
        cls,
        result: RadioMapResult,
        output_path: str,
        show_tx: bool = True,
        cmap_name: str = "plasma",
    ) -> str:
        """Render and save a Path Gain (dB) heatmap.

        Args:
            result: RadioMapResult containing spatial matrices and metadata.
            output_path: Destination PNG file path.
            show_tx: Whether to mark the transmitter coordinate with a star.
            cmap_name: Matplotlib colormap name.

        Returns:
            The saved absolute output path.

        Raises:
            RuntimeError: If matplotlib is not installed.
            ValueError: If numerical data is invalid.
        """
        if not MATPLOTLIB_AVAILABLE or plt is None:
            raise RuntimeError(
                "Heatmap visualization requires 'matplotlib', but it is not installed in the current environment."
            )

        if np is None:
            raise RuntimeError("NumPy is required for heatmap rendering.")

        data = np.asarray(result.path_gain_db)
        masked_data = np.ma.masked_where(~np.isfinite(data), data)

        fig, ax = plt.subplots(figsize=(9, 7), dpi=150)

        cmap = plt.get_cmap(cmap_name).copy()
        cmap.set_bad(color="#dcdcdc")

        extent = _compute_plot_extent(result)
        if extent is not None:
            im = ax.imshow(
                masked_data,
                origin="lower",
                extent=extent,
                cmap=cmap,
                aspect="equal",
                interpolation="nearest",
            )
        else:
            x_coords = np.asarray(result.x_coordinates)
            y_coords = np.asarray(result.y_coordinates)
            im = ax.pcolormesh(
                x_coords,
                y_coords,
                masked_data,
                cmap=cmap,
                shading="auto",
            )
            ax.set_aspect("equal")

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Path Gain (dB)", fontsize=11, fontweight="bold")

        if show_tx and result.tx_position is not None:
            tx_x, tx_y, _ = result.tx_position
            ax.plot(
                tx_x,
                tx_y,
                marker="*",
                markersize=13,
                color="red",
                markeredgecolor="black",
                label=f"TX ({tx_x:.1f}, {tx_y:.1f})m",
                zorder=5,
            )
            ax.legend(loc="upper right", framealpha=0.85)

        freq_ghz = result.frequency_hz / 1e9
        ax.set_xlabel("X Position (m)", fontsize=11)
        ax.set_ylabel("Y Position (m)", fontsize=11)
        ax.set_title(
            f"Path Gain (dB)\nScene: {result.scene_name} | Freq: {freq_ghz:.2f} GHz | Height: {result.measurement_height:.1f} m",
            fontsize=12,
            fontweight="bold",
        )
        ax.grid(True, linestyle=":", alpha=0.4, color="gray")

        abs_output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)
        fig.savefig(abs_output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return abs_output_path

    @classmethod
    def generate_heatmaps(
        cls,
        result: RadioMapResult,
        output_dir: str,
        prefix: str = "radio_map",
        show_tx: bool = True,
    ) -> Dict[str, str]:
        """Generate both Received-Power and Path-Gain heatmaps and return their file paths.

        Args:
            result: RadioMapResult to visualize.
            output_dir: Directory where PNG images will be saved.
            prefix: Filename prefix.
            show_tx: Whether to include transmitter indicator.

        Returns:
            Dictionary mapping 'rss_heatmap' and 'path_gain_heatmap' to absolute file paths.
        """
        abs_output_dir = os.path.abspath(output_dir)
        os.makedirs(abs_output_dir, exist_ok=True)

        rss_path = os.path.join(abs_output_dir, f"{prefix}_rss_dbm.png")
        gain_path = os.path.join(abs_output_dir, f"{prefix}_path_gain_db.png")

        cls.plot_received_power_heatmap(result, rss_path, show_tx=show_tx)
        cls.plot_path_gain_heatmap(result, gain_path, show_tx=show_tx)

        return {
            "rss_heatmap": rss_path,
            "path_gain_heatmap": gain_path,
        }

    @staticmethod
    def format_summary(result: RadioMapResult) -> str:
        """Format a clear, structured terminal summary of the radio map results."""
        freq_ghz = result.frequency_hz / 1e9
        ny, nx = result.grid_dimensions
        dx, dy = result.cell_size
        x_min, x_max, y_min, y_max = result.region_bounds

        min_rss_str = f"{result.min_rss_dbm:.2f} dBm" if result.min_rss_dbm is not None else "N/A"
        mean_rss_str = f"{result.mean_rss_dbm:.2f} dBm" if result.mean_rss_dbm is not None else "N/A"
        max_rss_str = f"{result.max_rss_dbm:.2f} dBm" if result.max_rss_dbm is not None else "N/A"

        lines = [
            "=" * 65,
            "               Sionna RT Radio Map Simulation Summary",
            "=" * 65,
            f"Scene:                  {result.scene_name}",
            f"Carrier Frequency:      {freq_ghz:.2f} GHz",
            f"Backend Variant:        {result.backend_variant}",
            f"Simulation Timestamp:   {result.simulation_timestamp}",
            "",
            "Transmitter Configuration:",
            f"  Position (X, Y, Z):   {result.tx_position} m",
            f"  Output Power:         {result.tx_power_dbm:.1f} dBm",
            f"  Orientation (Y, P, R):{result.tx_orientation_deg} deg",
            f"  Antenna Model:        {result.antenna_type} (pattern: '{result.antenna_pattern}', pol: '{result.polarization}')",
            "",
            "Receiver Measurement Grid:",
            f"  Grid Dimensions:      {ny} rows x {nx} cols ({result.num_cells} total cells)",
            f"  Cell Resolution:      dx = {dx:.2f} m, dy = {dy:.2f} m",
            f"  Measurement Height:   {result.measurement_height:.2f} m",
            f"  Bounding Region:      X in [{x_min:.1f}, {x_max:.1f}] m, Y in [{y_min:.1f}, {y_max:.1f}] m",
            "",
            "Spatial Coverage & Power Metrics:",
            f"  Reached Cells:        {result.valid_cells_count} / {result.num_cells} ({result.coverage_percentage:.1f}%)",
            f"  Unreached Cells:      {result.zero_power_cells_count} (zero RF power)",
            f"  Coverage (>= -100dBm):{result.coverage_above_threshold(-100.0):.1f}%",
            f"  Coverage (>= -90dBm): {result.coverage_above_threshold(-90.0):.1f}%",
            f"  Min Received Power:   {min_rss_str}",
            f"  Mean Received Power:  {mean_rss_str}",
            f"  Max Received Power:   {max_rss_str}",
            "=" * 65,
        ]
        return "\n".join(lines)

