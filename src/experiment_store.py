"""Filesystem Experiment Storage for Radio Map Simulations.

This module provides the ExperimentStore class, responsible for persisting,
listing, retrieving, and deleting radio map simulation experiments.

Storage architecture:
    <storage_root>/
        experiment_<unique_id>/
            metadata.json          # Simulation configuration, summary metrics, and artifacts
            radio_map_data.npz     # Compressed numerical arrays (linear/dB RSS, path gain, coords)
            rss_heatmap.png        # Received-Power heatmap visualization (optional)
            path_gain_heatmap.png  # Path-Gain heatmap visualization (optional)

Safeguards:
- Strict experiment ID validation preventing path traversal or injection.
- Atomic writes via temporary staging directories (.tmp_*) to prevent partial state corruption.
- Exact preservation of IEEE 754 -inf values (zero RF power/gain) without artificial noise floors.
- Pickle-free deserialization using allow_pickle=False.
- Graceful handling of missing or corrupted files.
"""

from datetime import datetime, timezone
import json
import os
import re
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

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
    from src.radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from radio_map_result import RadioMapResult


DEFAULT_EXPERIMENTS_DIR = os.path.abspath(
    os.path.join(_repo_root, "experiments")
)

SCHEMA_VERSION = "1.0"


class ExperimentStore:
    """Manages filesystem-based storage of radio-map simulation experiments."""

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        """Initialize the experiment store with a configurable storage root.

        Args:
            storage_dir: Base directory for storing experiments. Defaults to
                         the repository's 'experiments/' directory.
        """
        if storage_dir is None:
            self.storage_dir = DEFAULT_EXPERIMENTS_DIR
        else:
            self.storage_dir = os.path.abspath(storage_dir)

    # -------------------------------------------------------------------------
    # Internal Validation & Resolution Helpers
    # -------------------------------------------------------------------------
    def _validate_experiment_id(self, experiment_id: Any) -> str:
        """Validate experiment ID format and enforce strict path traversal safeguards.

        Args:
            experiment_id: Identifier to validate.

        Returns:
            The validated and cleaned experiment ID string.

        Raises:
            ValueError: If experiment_id is not a valid non-empty string or
                        attempts path traversal.
        """
        if not isinstance(experiment_id, str):
            raise ValueError(
                f"Experiment ID must be a string, got {type(experiment_id).__name__}."
            )

        cleaned_id = experiment_id.strip()
        if not cleaned_id:
            raise ValueError("Experiment ID cannot be empty or whitespace.")

        # Disallow explicit traversal sequences, null bytes, or path separators
        if (
            ".." in cleaned_id
            or "/" in cleaned_id
            or "\\" in cleaned_id
            or "\0" in cleaned_id
        ):
            raise ValueError(
                f"Invalid experiment ID or path traversal sequence detected: {experiment_id!r}"
            )

        # Enforce whitelisted character set: alphanumeric, underscores, hyphens, and dots
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", cleaned_id) or cleaned_id in (".", ".."):
            raise ValueError(
                f"Experiment ID contains invalid characters or pattern: {experiment_id!r}"
            )

        # Enforce strict path containment within storage_dir
        target_path = os.path.abspath(os.path.join(self.storage_dir, cleaned_id))
        real_storage = os.path.realpath(self.storage_dir)
        real_target = os.path.realpath(target_path)
        try:
            common = os.path.commonpath([real_storage, real_target])
        except ValueError:
            # Different drive letters on Windows
            raise ValueError(f"Path traversal detected: {experiment_id!r}")

        if common != real_storage or real_target == real_storage:
            raise ValueError(f"Path traversal detected: {experiment_id!r}")

        return cleaned_id

    def _resolve_experiment_dir(self, experiment_id: str) -> Optional[str]:
        """Resolve the experiment directory on disk, checking direct and prefixed variants.

        Args:
            experiment_id: Validated experiment identifier.

        Returns:
            Absolute directory path if found, or None if the directory does not exist.
        """
        # 1. Exact match
        direct_path = os.path.join(self.storage_dir, experiment_id)
        if os.path.isdir(direct_path):
            return direct_path

        # 2. Match with 'experiment_' prefix added
        if not experiment_id.startswith("experiment_"):
            prefixed_path = os.path.join(self.storage_dir, f"experiment_{experiment_id}")
            if os.path.isdir(prefixed_path):
                return prefixed_path

        # 3. Match with 'experiment_' prefix stripped
        if experiment_id.startswith("experiment_"):
            stripped_id = experiment_id[len("experiment_") :]
            stripped_path = os.path.join(self.storage_dir, stripped_id)
            if os.path.isdir(stripped_path):
                return stripped_path

        return None

    @staticmethod
    def _generate_experiment_id() -> str:
        """Generate a timestamped, unique experiment identifier."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"experiment_{timestamp}_{short_uuid}"

    # -------------------------------------------------------------------------
    # Public Storage Operations
    # -------------------------------------------------------------------------
    def save_experiment(
        self,
        result: RadioMapResult,
        heatmap_paths: Optional[Dict[str, str]] = None,
        experiment_name: Optional[str] = None,
        experiment_id: Optional[str] = None,
    ) -> str:
        """Save a radio-map simulation result, metadata, and optional heatmaps atomically.

        Args:
            result: Completed RadioMapResult instance containing numerical matrices and metadata.
            heatmap_paths: Optional dictionary mapping heatmap types ('rss_heatmap', 'path_gain_heatmap')
                           to filesystem image paths.
            experiment_name: Optional human-readable label for the experiment.
            experiment_id: Optional custom unique identifier. If omitted, a unique ID is generated.

        Returns:
            The experiment ID of the saved experiment.

        Raises:
            ValueError: If inputs or custom experiment_id are invalid.
            RuntimeError: If NumPy is unavailable.
            FileExistsError: If an experiment with the target ID already exists.
            OSError: If writing files or directory creation fails.
        """
        if not isinstance(result, RadioMapResult):
            raise ValueError(
                f"Expected result to be a RadioMapResult instance, got {type(result).__name__}."
            )

        if np is None:
            raise RuntimeError(
                "NumPy is required to save numerical experiment data, but is not installed."
            )

        # Determine and validate experiment ID
        if experiment_id is not None:
            exp_id = self._validate_experiment_id(experiment_id)
        else:
            exp_id = self._generate_experiment_id()

        os.makedirs(self.storage_dir, exist_ok=True)
        final_dir = os.path.join(self.storage_dir, exp_id)
        if os.path.exists(final_dir):
            raise FileExistsError(
                f"Experiment directory already exists: '{final_dir}'."
            )

        # Stage files in a temporary staging directory to ensure atomic writes
        temp_dir = tempfile.mkdtemp(prefix=".tmp_", dir=self.storage_dir)

        try:
            # 1. Compress and store numerical arrays into NPZ
            npz_path = os.path.join(temp_dir, "radio_map_data.npz")
            arrays_to_save = {
                "path_gain_linear": np.asarray(result.path_gain_linear),
                "path_gain_db": np.asarray(result.path_gain_db),
                "rss_watts": np.asarray(result.rss_watts),
                "rss_dbm": np.asarray(result.rss_dbm),
                "cell_centers": np.asarray(result.cell_centers),
                "x_coordinates": np.asarray(result.x_coordinates),
                "y_coordinates": np.asarray(result.y_coordinates),
            }
            np.savez_compressed(npz_path, **arrays_to_save)

            # 2. Copy optional heatmaps into staging directory
            has_rss_heatmap = False
            has_gain_heatmap = False

            if heatmap_paths and isinstance(heatmap_paths, dict):
                rss_source = heatmap_paths.get("rss_heatmap") or heatmap_paths.get("rss")
                if rss_source and os.path.isfile(rss_source):
                    shutil.copy2(rss_source, os.path.join(temp_dir, "rss_heatmap.png"))
                    has_rss_heatmap = True

                gain_source = heatmap_paths.get("path_gain_heatmap") or heatmap_paths.get("path_gain")
                if gain_source and os.path.isfile(gain_source):
                    shutil.copy2(gain_source, os.path.join(temp_dir, "path_gain_heatmap.png"))
                    has_gain_heatmap = True

            # 3. Construct and serialize metadata JSON
            metadata: Dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "experiment_id": exp_id,
                "experiment_name": experiment_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "simulation_timestamp": str(result.simulation_timestamp),
                "scene_name": str(result.scene_name),
                "frequency_hz": float(result.frequency_hz),
                "tx_position": list(result.tx_position),
                "tx_power_dbm": float(result.tx_power_dbm),
                "tx_orientation_deg": list(result.tx_orientation_deg),
                "antenna_type": str(result.antenna_type),
                "antenna_pattern": str(result.antenna_pattern),
                "polarization": str(result.polarization),
                "measurement_height": float(result.measurement_height),
                "region_bounds": list(result.region_bounds),
                "cell_size": list(result.cell_size),
                "grid_dimensions": list(result.grid_dimensions),
                "solver_parameters": dict(result.solver_parameters),
                "backend_variant": str(result.backend_variant),
                "total_cells": result.num_cells,
                "valid_cells": result.valid_cells_count,
                "zero_power_cells": result.zero_power_cells_count,
                "coverage_percentage": float(result.coverage_percentage),
                "min_rss_dbm": result.min_rss_dbm,
                "mean_rss_dbm": result.mean_rss_dbm,
                "max_rss_dbm": result.max_rss_dbm,
                "summary_metrics": {
                    "total_cells": result.num_cells,
                    "valid_cells": result.valid_cells_count,
                    "zero_power_cells": result.zero_power_cells_count,
                    "coverage_percentage": float(result.coverage_percentage),
                    "min_rss_dbm": result.min_rss_dbm,
                    "mean_rss_dbm": result.mean_rss_dbm,
                    "max_rss_dbm": result.max_rss_dbm,
                },
                "array_shapes": {
                    name: list(arr.shape) for name, arr in arrays_to_save.items()
                },
                "array_names": list(arrays_to_save.keys()),
                "heatmaps": {
                    "rss_heatmap": {
                        "filename": "rss_heatmap.png",
                        "available": has_rss_heatmap,
                    },
                    "path_gain_heatmap": {
                        "filename": "path_gain_heatmap.png",
                        "available": has_gain_heatmap,
                    },
                },
            }

            metadata_path = os.path.join(temp_dir, "metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # 4. Atomic directory move to final destination
            os.replace(temp_dir, final_dir)

        except Exception:
            # Clean up temporary staging directory on any failure
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        return exp_id

    def list_experiments(self) -> List[Dict[str, Any]]:
        """List all stored experiments with lightweight summary metadata.

        Numerical array data is not loaded.

        Returns:
            List of experiment summaries ordered by creation/simulation timestamp descending.
        """
        if not os.path.isdir(self.storage_dir):
            return []

        experiments: List[Dict[str, Any]] = []

        try:
            entries = sorted(os.listdir(self.storage_dir))
        except OSError:
            return []

        for entry in entries:
            # Skip hidden staging or system directories
            if entry.startswith("."):
                continue

            exp_dir = os.path.join(self.storage_dir, entry)
            if not os.path.isdir(exp_dir):
                continue

            metadata_path = os.path.join(exp_dir, "metadata.json")
            if not os.path.isfile(metadata_path):
                continue

            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                # Corrupted JSON: skip to prevent one malformed file from breaking list view
                continue

            rss_file = os.path.join(exp_dir, "rss_heatmap.png")
            gain_file = os.path.join(exp_dir, "path_gain_heatmap.png")

            exp_id = meta.get("experiment_id", entry)
            summary = {
                "experiment_id": exp_id,
                "experiment_name": meta.get("experiment_name"),
                "scene_name": meta.get("scene_name"),
                "frequency_hz": meta.get("frequency_hz"),
                "tx_position": meta.get("tx_position"),
                "tx_power_dbm": meta.get("tx_power_dbm"),
                "measurement_height": meta.get("measurement_height"),
                "grid_dimensions": meta.get("grid_dimensions"),
                "cell_size": meta.get("cell_size"),
                "simulation_timestamp": meta.get("simulation_timestamp"),
                "created_at": meta.get("created_at"),
                "coverage_percentage": meta.get("coverage_percentage"),
                "heatmaps_available": {
                    "rss_heatmap": os.path.isfile(rss_file),
                    "path_gain_heatmap": os.path.isfile(gain_file),
                },
            }
            experiments.append(summary)

        # Sort descending: newest experiments first
        experiments.sort(
            key=lambda x: str(x.get("created_at") or x.get("simulation_timestamp") or ""),
            reverse=True,
        )
        return experiments

    def get_experiment_details(self, experiment_id: str) -> Dict[str, Any]:
        """Retrieve detailed metadata and artifact file paths for an experiment without loading arrays.

        Args:
            experiment_id: Unique identifier of the experiment.

        Returns:
            Dictionary containing metadata, artifact paths, and heatmap status.

        Raises:
            ValueError: If experiment_id is invalid, path traversal occurs, or metadata is corrupted.
            FileNotFoundError: If the experiment directory or metadata.json does not exist.
        """
        valid_id = self._validate_experiment_id(experiment_id)
        exp_dir = self._resolve_experiment_dir(valid_id)
        if exp_dir is None or not os.path.isdir(exp_dir):
            raise FileNotFoundError(
                f"Experiment '{experiment_id}' does not exist in '{self.storage_dir}'."
            )

        metadata_path = os.path.join(exp_dir, "metadata.json")
        if not os.path.isfile(metadata_path):
            raise FileNotFoundError(
                f"Metadata file 'metadata.json' not found for experiment '{experiment_id}'."
            )

        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Corrupted or invalid metadata JSON in experiment '{experiment_id}': {exc}"
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"Failed to read metadata for experiment '{experiment_id}': {exc}"
            ) from exc

        npz_path = os.path.join(exp_dir, "radio_map_data.npz")
        rss_path = os.path.join(exp_dir, "rss_heatmap.png")
        gain_path = os.path.join(exp_dir, "path_gain_heatmap.png")

        has_rss = os.path.isfile(rss_path)
        has_gain = os.path.isfile(gain_path)
        has_npz = os.path.isfile(npz_path)

        details = dict(metadata)
        details["experiment_dir"] = exp_dir
        details["artifact_paths"] = {
            "metadata": metadata_path,
            "radio_map_data": npz_path if has_npz else None,
            "rss_heatmap": rss_path if has_rss else None,
            "path_gain_heatmap": gain_path if has_gain else None,
        }
        details["heatmaps_available"] = {
            "rss_heatmap": has_rss,
            "path_gain_heatmap": has_gain,
        }
        details["radio_map_data_exists"] = has_npz

        return details

    def load_experiment(self, experiment_id: str) -> RadioMapResult:
        """Load an experiment from disk and reconstruct a complete RadioMapResult object.

        Numerical data is loaded using allow_pickle=False to ensure integrity and security.

        Args:
            experiment_id: Unique identifier of the experiment.

        Returns:
            Reconstructed and validated RadioMapResult instance.

        Raises:
            ValueError: If experiment_id is invalid, path traversal occurs, JSON/NPZ is corrupted,
                        or required arrays are missing.
            FileNotFoundError: If the experiment, metadata.json, or radio_map_data.npz is missing.
            RuntimeError: If NumPy is not installed.
        """
        if np is None:
            raise RuntimeError(
                "NumPy is required to load experiment data, but is not installed."
            )

        valid_id = self._validate_experiment_id(experiment_id)
        exp_dir = self._resolve_experiment_dir(valid_id)
        if exp_dir is None or not os.path.isdir(exp_dir):
            raise FileNotFoundError(
                f"Experiment '{experiment_id}' does not exist in '{self.storage_dir}'."
            )

        metadata_path = os.path.join(exp_dir, "metadata.json")
        if not os.path.isfile(metadata_path):
            raise FileNotFoundError(
                f"Metadata file 'metadata.json' not found for experiment '{experiment_id}'."
            )

        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Corrupted or invalid metadata JSON in experiment '{experiment_id}': {exc}"
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"Failed to read metadata for experiment '{experiment_id}': {exc}"
            ) from exc

        npz_path = os.path.join(exp_dir, "radio_map_data.npz")
        if not os.path.isfile(npz_path):
            raise FileNotFoundError(
                f"Numerical data file 'radio_map_data.npz' not found for experiment '{experiment_id}'."
            )

        required_arrays = [
            "path_gain_linear",
            "path_gain_db",
            "rss_watts",
            "rss_dbm",
            "cell_centers",
            "x_coordinates",
            "y_coordinates",
        ]

        try:
            with np.load(npz_path, allow_pickle=False) as npz:
                for arr_name in required_arrays:
                    if arr_name not in npz:
                        raise ValueError(
                            f"Missing required array '{arr_name}' in numerical data for experiment '{experiment_id}'."
                        )
                arrays = {k: np.array(npz[k], copy=True) for k in required_arrays}
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("Missing required array"):
                raise
            raise ValueError(
                f"Corrupted or invalid NPZ numerical data in experiment '{experiment_id}': {exc}"
            ) from exc

        # Reconstruct RadioMapResult
        try:
            result = RadioMapResult(
                scene_name=str(metadata["scene_name"]),
                frequency_hz=float(metadata["frequency_hz"]),
                tx_position=tuple(metadata["tx_position"]),
                tx_power_dbm=float(metadata["tx_power_dbm"]),
                tx_orientation_deg=tuple(metadata["tx_orientation_deg"]),
                antenna_type=str(metadata["antenna_type"]),
                antenna_pattern=str(metadata["antenna_pattern"]),
                polarization=str(metadata["polarization"]),
                measurement_height=float(metadata["measurement_height"]),
                region_bounds=tuple(metadata["region_bounds"]),
                cell_size=tuple(metadata["cell_size"]),
                grid_dimensions=tuple(metadata["grid_dimensions"]),
                solver_parameters=dict(metadata.get("solver_parameters", {})),
                simulation_timestamp=str(metadata.get("simulation_timestamp", "")),
                backend_variant=str(metadata.get("backend_variant", "unknown")),
                path_gain_linear=arrays["path_gain_linear"],
                path_gain_db=arrays["path_gain_db"],
                rss_watts=arrays["rss_watts"],
                rss_dbm=arrays["rss_dbm"],
                cell_centers=arrays["cell_centers"],
                x_coordinates=arrays["x_coordinates"],
                y_coordinates=arrays["y_coordinates"],
            )
        except Exception as exc:
            raise ValueError(
                f"Failed to reconstruct RadioMapResult from experiment '{experiment_id}': {exc}"
            ) from exc

        return result

    def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment directory and all its files from disk.

        Args:
            experiment_id: Unique identifier of the experiment.

        Returns:
            True if the experiment was deleted, False if it did not exist.

        Raises:
            ValueError: If experiment_id is invalid or attempts path traversal.
        """
        valid_id = self._validate_experiment_id(experiment_id)
        exp_dir = self._resolve_experiment_dir(valid_id)
        if exp_dir is None or not os.path.isdir(exp_dir):
            return False

        # Additional containment security check
        real_storage = os.path.realpath(self.storage_dir)
        real_exp = os.path.realpath(exp_dir)
        try:
            common = os.path.commonpath([real_storage, real_exp])
        except ValueError:
            raise ValueError(f"Path traversal detected during deletion: {experiment_id!r}")

        if common != real_storage or real_storage == real_exp:
            raise ValueError(f"Path traversal detected during deletion: {experiment_id!r}")

        shutil.rmtree(exp_dir)
        return True
