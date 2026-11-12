# Experiment Storage Architecture and File Artifacts Specification

This document details the filesystem-based persistence architecture, serialization schemas, naming conventions, and integrity safeguards implemented in `src/experiment_store.py`.

---

## 1. Storage Overview and Directory Hierarchy

All experiments are stored locally in the `experiments/` directory located at the project root. The storage architecture is entirely file-based, requiring no external database or server dependencies.

### Directory Structure:

```text
experiments/
├── comparisons/                                             # Directory storing spatial difference heatmaps
│   ├── diff_experiment_<idA>_vs_experiment_<idB>_rss_db.png       # Diverging RSS difference heatmap
│   └── diff_experiment_<idA>_vs_experiment_<idB>_path_gain_db.png # Diverging Path Gain difference heatmap
│
├── experiment_20261101_135328_38565204/                     # Single experiment directory
│   ├── metadata.json                                        # Complete simulation metadata and summary metrics
│   ├── radio_map_data.npz                                   # Compressed NumPy arrays (float64, pickle-free)
│   ├── rss_heatmap.png                                      # Received Signal Strength (dBm) heatmap
│   └── path_gain_heatmap.png                                # Path Gain (dB) heatmap
│
└── experiment_20261101_135328_4b634b84/
    ├── metadata.json
    ├── radio_map_data.npz
    ├── rss_heatmap.png
    └── path_gain_heatmap.png
```

---

## 2. Experiment Identification Scheme

Every experiment is assigned a unique identifier following the canonical format:

$$\text{experiment\_}\langle\text{YYYYMMDD}\rangle\text{\_}\langle\text{HHMMSS}\rangle\text{\_}\langle\text{uuid8}\rangle$$

- **Timestamp Component:** UTC timestamp formatted as `YYYYMMDD_HHMMSS` ensures chronological sorting on filesystem directories.
- **UUID Component:** 8 hexadecimal characters generated from `uuid.uuid4().hex[:8]` guarantees uniqueness even under concurrent generation.
- **Example:** `experiment_20261101_135328_38565204`
- **Validation:** Strict regex validation `^[a-zA-Z0-9_\-]+$` rejects any path traversal characters (`..`, `/`, `\`).

---

## 3. Detailed Artifact Specifications

### 3.1 `metadata.json`

The `metadata.json` file records all input configurations, runtime environment attributes, array shapes, and statistical summary metrics. It enables lightweight inspection without loading numerical arrays.

#### JSON Schema Structure:

```json
{
  "schema_version": "1.0",
  "experiment_id": "experiment_20261101_135328_38565204",
  "experiment_name": "validation_run_30dbm",
  "created_at": "2026-11-01T13:53:28.159443+00:00",
  "simulation_timestamp": "2026-11-01T13:53:27.736018+00:00",
  "scene_name": "simple_reflector",
  "frequency_hz": 3500000000.0,
  "tx_position": [0.0, -10.0, 5.0],
  "tx_power_dbm": 30.0,
  "tx_orientation_deg": [0.0, 0.0, 0.0],
  "antenna_type": "isotropic",
  "antenna_pattern": "iso",
  "polarization": "V",
  "measurement_height": 1.5,
  "region_bounds": [-5.5, 5.5, -15.0, 5.5],
  "cell_size": [5.0, 5.0],
  "grid_dimensions": [5, 3],
  "solver_parameters": {
    "samples_per_tx": 10000,
    "max_depth": 3,
    "seed": null,
    "los": true,
    "specular_reflection": true,
    "diffraction": true,
    "scattering": false
  },
  "backend_variant": "llvm_ad_mono_polarized",
  "total_cells": 15,
  "valid_cells": 15,
  "zero_power_cells": 0,
  "coverage_percentage": 100.0,
  "min_rss_dbm": -37.9167,
  "mean_rss_dbm": -32.0853,
  "max_rss_dbm": -25.3994,
  "artifact_paths": {
    "rss_heatmap": "C:\\...\\experiments\\experiment_...\\rss_heatmap.png",
    "path_gain_heatmap": "C:\\...\\experiments\\experiment_...\\path_gain_heatmap.png",
    "metadata_json": "C:\\...\\experiments\\experiment_...\\metadata.json",
    "radio_map_data_npz": "C:\\...\\experiments\\experiment_...\\radio_map_data.npz"
  },
  "heatmaps_available": {
    "rss_heatmap": true,
    "path_gain_heatmap": true
  }
}
```

---

### 3.2 `radio_map_data.npz`

The `radio_map_data.npz` file stores complete, uncompressed or compressed raw numerical tensors.

#### Saved Arrays:

| Array Key | Data Type | Dimensions | Description | Handling of Zero-Power Cells |
| :--- | :---: | :---: | :--- | :--- |
| `path_gain_linear` | `float64` | `[Ny, Nx]` | Linear power transfer gain ($G_{\text{lin}} \ge 0.0$) | Exactly `0.0` |
| `path_gain_db` | `float64` | `[Ny, Nx]` | Logarithmic path gain ($10 \log_{10}(G)$) | Exactly `-inf` ($-\infty$) |
| `rss_watts` | `float64` | `[Ny, Nx]` | Received RF power in Watts ($P_W \ge 0.0$) | Exactly `0.0` |
| `rss_dbm` | `float64` | `[Ny, Nx]` | Received Signal Strength ($10 \log_{10}(P) + 30$) | Exactly `-inf` ($-\infty$) |
| `cell_centers` | `float64` | `[Ny, Nx, 3]` | 3D Cartesian coordinates $[x, y, z]$ per cell center | Actual spatial coordinate $(x, y, z)$ |
| `x_coordinates` | `float64` | `[Nx]` or `[Ny, Nx]` | X-axis coordinate vector or 2D coordinate mesh | Real float coordinate |
| `y_coordinates` | `float64` | `[Ny]` or `[Ny, Nx]` | Y-axis coordinate vector or 2D coordinate mesh | Real float coordinate |

#### Pickling Prohibition:
All arrays are cast to `np.float64` before writing. Deserialization strictly uses `np.load(npz_path, allow_pickle=False)`. This guarantees safety and prevents arbitrary code execution.

---

### 3.3 Visual Heatmap Artifacts (`*.png`)

1. **`rss_heatmap.png`:**
   - 2D spatial distribution of Received Signal Strength in dBm.
   - Rendered using the `viridis` colormap.
   - Transmitter location marked with a red star marker ($\star$).
   - Unreachable cells (zero power) are masked with a neutral light gray (`#dcdcdc`).
   - Resolution: 150 DPI (typically 65–85 KB).

2. **`path_gain_heatmap.png`:**
   - 2D spatial distribution of logarithmic Path Gain in dB.
   - Rendered using the `plasma` colormap.
   - Shows intrinsic channel propagation attenuation independent of transmitter power.

3. **Comparison Difference Heatmaps:**
   - Saved under `experiments/comparisons/`.
   - Naming: `diff_<idA>_vs_<idB>_rss_db.png` and `diff_<idA>_vs_<idB>_path_gain_db.png`.
   - Centered diverging colormap (`PuOr` / `RdBu_r`) where $0.0$ dB is neutral.
   - Positive regions ($> 0$ dB, Experiment B stronger) and negative regions ($< 0$ dB, Experiment B weaker) are clearly distinguished.
   - Invalid cells (unreached in either A or B) are rendered in neutral gray.

---

## 4. Integrity, Atomic Writes, and Safety Safeguards

### 4.1 Atomic Writes via Staging Directories
To prevent corrupted or half-written experiments caused by process crashes or disk interruptions:
1. All files (`metadata.json`, `radio_map_data.npz`, heatmaps) are written to a temporary staging folder:
   `experiments/.tmp_XXXXXX/`
2. Once all files are written and verified, the staging directory is renamed atomically to its final destination `experiments/experiment_<id>/`.
3. If an error occurs during writing, the staging folder is deleted, leaving no orphaned or broken directories.

### 4.2 Path Traversal Prevention
Any user-supplied or client-supplied `experiment_id` is sanitized using:
```python
if not re.match(r"^[a-zA-Z0-9_\-]+$", exp_id):
    raise ValueError(f"Invalid experiment_id '{exp_id}': contains illegal characters.")
```
Attempts to access `../` or absolute paths are immediately rejected.

### 4.3 Missing or Corrupted File Resilience
- If an experiment folder has a missing or malformed `metadata.json`, `ExperimentStore.list_experiments()` logs a warning and skips the entry without crashing.
- Direct queries (`get_experiment_details`) on corrupted experiments raise informative `ValueError` exceptions with exact diagnostics.

