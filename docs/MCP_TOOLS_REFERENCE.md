# Model Context Protocol (MCP) Tools Reference

This document provides a comprehensive, rigorous API specification for all seven tools exposed by the `sionna_rt_mcp` server.

> [!NOTE]
> All seven tools are accessible identically across both **Streamable HTTP transport** (`http://127.0.0.1:8000/mcp`, started via `python server.py`) and standard **Stdio transport** (`python server.py --transport stdio` or `python src/mcp_server.py`). Tool schemas, arguments, physical calculations, and return structures are 100% identical across transports.

---

## Tool Summary Index

| # | Tool Name | Subsystem | Purpose | Primary Module Dependency |
| :-: | :--- | :--- | :--- | :--- |
| **1** | `check_environment` | Diagnostic | Verify environment, software versions, and active backend | `src/engine.py` |
| **2** | `list_scenes` | Geometry | Catalog 3D propagation scenes available for simulation | `sionna.rt.scene` |
| **3** | `run_simulation` | Point-to-Point | Execute single TX-RX ray tracing and extract propagation metrics | `src/engine.py`, `src/config.py` |
| **4** | `generate_radio_map` | Coverage | Compute 2D spatial coverage map, render heatmaps, and persist | `src/radio_map_engine.py`, `src/experiment_store.py` |
| **5** | `list_experiments` | Storage | Retrieve lightweight metadata summaries of stored experiments | `src/experiment_store.py` |
| **6** | `get_experiment_details` | Storage | Retrieve comprehensive metadata and artifact paths for an experiment | `src/experiment_store.py` |
| **7** | `compare_experiments` | Spatial Analysis | Compute spatial differences ($B - A$) and render difference heatmaps | `src/experiment_comparator.py` |

---

## 1. `check_environment`

### Purpose
Probe whether Python, Sionna RT, and Mitsuba are properly installed and operational, identifying the active Mitsuba computational backend (e.g. CPU LLVM fallback or GPU OptiX). Call this tool before running simulations if environment availability is uncertain.

### Parameters
*None.* This tool takes no input arguments.

### Return Schema (`dict`)
- `python_version` (`str`): CPython runtime version (e.g., `"3.10.10"`).
- `sionna_version` (`str`): Installed version of `sionna-rt` (e.g., `"2.2.0"`).
- `mitsuba_version` (`str`): Installed version of `mitsuba` (e.g., `"3.9.1"`).
- `backend` (`str`): Active Mitsuba backend variant (e.g., `"llvm_ad_mono_polarized"`).
- `is_usable` (`bool`): `true` if the simulation engine is operational; `false` otherwise.

### Sample Response
```json
{
  "python_version": "3.10.10",
  "sionna_version": "2.2.0",
  "mitsuba_version": "3.9.1",
  "backend": "llvm_ad_mono_polarized",
  "is_usable": true
}
```

### Errors Raised
- No exceptions are raised; failure to initialize the engine logs an error and sets `is_usable: false` and `backend: "unavailable"`.

---

## 2. `list_scenes`

### Purpose
Enumerate all 3D geometric propagation environments available to the simulation engine. Clients use this tool to discover valid `scene` or `scene_name` strings before running simulations.

### Parameters
*None.* This tool takes no input arguments.

### Return Schema (`dict`)
- `scenes` (`list[dict]`): Catalog of scene descriptors, each containing:
  - `name` (`str`): Unique scene identifier (e.g., `"simple_reflector"`).
  - `description` (`str`): Technical description of the physical environment and expected propagation mechanisms.
  - `is_default` (`bool`): Whether this is the default scene.
- `default_scene` (`str`): Name of the canonical default scene (`"simple_reflector"`).
- `count` (`int`): Total count of registered scenes.

### Sample Response
```json
{
  "scenes": [
    {
      "name": "simple_reflector",
      "description": "Canonical two-path propagation scene containing a planar reflector. Produces a direct Line of Sight (LOS) ray and a single Specular Reflection ray.",
      "is_default": true
    }
  ],
  "default_scene": "simple_reflector",
  "count": 1
}
```

---

## 3. `run_simulation`

### Purpose
Execute an NVIDIA Sionna RT ray-tracing simulation between a point transmitter and a point receiver node in 3D space, resolving multipath components and extracting physical propagation metrics.

### Input Parameters

| Parameter | Type | Required? | Default | Constraints & Description |
| :--- | :---: | :---: | :---: | :--- |
| `scene` | `str` | Optional | `"simple_reflector"` | Geometric scene identifier. Must match a supported scene. |
| `frequency_hz` | `float` | Optional | `3.5e9` | Carrier frequency in **Hertz (Hz)** (e.g., `3.5e9` for 3.5 GHz). Must be $> 0.0$ Hz. |
| `tx_position` | `list[float]` | Optional | `[0.0, -10.0, 5.0]` | Transmitter Cartesian coordinates $[x, y, z]$ in meters (exactly 3 elements). |
| `rx_position` | `list[float]` | Optional | `[0.0, 10.0, 5.0]` | Receiver Cartesian coordinates $[x, y, z]$ in meters (exactly 3 elements). |
| `tx_power_dbm` | `float` | Optional | `30.0` | Transmit RF power in dBm ($30.0 \text{ dBm} = 1.0 \text{ W}$). |

### Return Schema (`dict`)
- `scene_name` (`str`): Simulated scene name.
- `frequency_hz` (`float`): Carrier frequency in Hz.
- `tx_position` (`list[float]`): $[x, y, z]$ in meters.
- `rx_position` (`list[float]`): $[x, y, z]$ in meters.
- `tx_power_dbm` (`float`): Transmit power in dBm.
- `backend` (`str`): Active computational backend.
- `num_paths` (`int`): Number of discrete propagation paths resolved.
- `total_path_loss_db` (`float`): Total channel path loss in dB.
- `received_power_dbm` (`float`): Total received power in dBm.
- `min_delay_ns` (`float`): Minimum path arrival delay in nanoseconds.
- `max_delay_ns` (`float`): Maximum path arrival delay in nanoseconds.
- `delays_ns` (`list[float]`): Per-path propagation delays in nanoseconds.
- `path_distances_m` (`list[float]`): Per-path geometric travel distances in meters.
- `path_gains_db` (`list[float]`): Per-path power gains in dB.
- `interaction_types` (`list[str]`): Physical mechanisms per path (e.g., `["Line of Sight (LOS)", "Specular Reflection"]`).

### Possible Errors
- `ToolError`: If `frequency_hz <= 0`, `tx_position` or `rx_position` are not 3-element numeric lists, or the scene is unknown.

---

## 4. `generate_radio_map`

### Purpose
Generate a 2D spatial radio coverage map over a horizontal evaluation plane using Sionna RT's `RadioMapSolver`. Extracts numerical field matrices (linear and dB received power and path gain), renders high-resolution heatmaps, and automatically persists the experiment to disk via `ExperimentStore`.

### Input Parameters

| Parameter | Type | Required? | Default | Description & Constraints |
| :--- | :---: | :---: | :---: | :--- |
| `scene_name` | `str` | Optional | `"simple_reflector"` | Geometric scene identifier. |
| `frequency_hz` | `float` | Optional | `3.5e9` | Carrier frequency in Hertz ($> 0.0$ Hz). |
| `tx_name` | `str` | Optional | `"tx"` | Label for the transmitter node. |
| `tx_position` | `list[float]` | Optional | `[0.0, -10.0, 5.0]` | Transmitter 3D position $[x, y, z]$ in meters. |
| `tx_power_dbm` | `float` | Optional | `30.0` | Output RF power in dBm. |
| `tx_orientation_deg`| `list[float]` | Optional | `[0.0, 0.0, 0.0]` | Transmitter $[yaw, pitch, roll]$ in degrees. |
| `antenna_type` | `str` | Optional | `"isotropic"` | Pattern type: `"isotropic"`, `"dipole"`, or `"directional"`. |
| `polarization` | `str` | Optional | `"V"` | Polarization: `"V"`, `"H"`, `"VH"`, or `"cross"`. |
| `num_rows` | `int` | Optional | `1` | Antenna array rows ($\ge 1$). |
| `num_cols` | `int` | Optional | `1` | Antenna array columns ($\ge 1$). |
| `horizontal_spacing`| `float` | Optional | `0.5` | Element spacing in wavelengths ($\lambda$). |
| `vertical_spacing` | `float` | Optional | `0.5` | Element spacing in wavelengths ($\lambda$). |
| `region_mode` | `str` | Optional | `"auto"` | Bounding box mode: `"auto"` or `"manual"`. |
| `auto_margin` | `float` | Optional | `5.0` | Buffer margin in meters added to scene bounds. |
| `auto_include_tx` | `bool` | Optional | `True` | Expand auto bounds to enclose transmitter. |
| `x_min`, `x_max` | `float` | Conditional | `None` | Bounds in meters (required if `region_mode="manual"`). |
| `y_min`, `y_max` | `float` | Conditional | `None` | Bounds in meters (required if `region_mode="manual"`). |
| `receiver_height` | `float` | Optional | `1.5` | Evaluation plane height ($z$) in meters. |
| `cell_size` | `float` or `list` | Optional | `1.0` | Grid resolution in meters: scalar ($1.0$) or $[dx, dy]$. |
| `samples_per_tx` | `int` | Optional | `1_000_000` | Monte Carlo ray budget per transmitter. |
| `max_depth` | `int` | Optional | `3` | Maximum ray bounce depth. |
| `seed` | `int` | Optional | `None` | Random seed for deterministic reproducibility. |
| `los` | `bool` | Optional | `True` | Enable Line of Sight rays. |
| `specular_reflection`| `bool`| Optional | `True` | Enable specular reflections. |
| `diffraction` | `bool` | Optional | `True` | Enable edge diffraction. |
| `scattering` | `bool` | Optional | `False` | Enable diffuse scattering. |
| `experiment_name` | `str` | Optional | `None` | Optional human-readable experiment label. |

### Return Schema (`dict`)
- `status` (`str`): `"success"`.
- `experiment_id` (`str`): Unique generated identifier (e.g., `"experiment_20261101_135328_38565204"`).
- `scene_name` (`str`): Evaluated scene.
- `grid_dimensions` (`list[int]`): $[Ny, Nx]$ grid dimensions.
- `total_cells` (`int`): Total evaluation cells ($Ny \times Nx$).
- `valid_cells` (`int`): Cells receiving finite RF power ($> 0.0$ W).
- `zero_power_cells` (`int`): Unreachable cells receiving $0.0$ W.
- `coverage_percentage` (`float`): Percentage of cells reached ($0.0$ to $100.0\%$).
- `min_rss_dbm` (`float`): Minimum finite RSS across the grid.
- `mean_rss_dbm` (`float`): Mean finite RSS across the grid.
- `max_rss_dbm` (`float`): Maximum finite RSS across the grid.
- `artifact_paths` (`dict`):
  - `rss_heatmap` (`str`): Absolute path to saved RSS PNG heatmap.
  - `path_gain_heatmap` (`str`): Absolute path to saved Path Gain PNG heatmap.
  - `metadata_json` (`str`): Absolute path to `metadata.json`.
  - `radio_map_data_npz` (`str`): Absolute path to `radio_map_data.npz`.

### Possible Errors
- `ToolError`: If parameters fail validation (`frequency_hz <= 0`, manual bounds missing when `region_mode="manual"`, invalid antenna type or polarization).
- `ToolError`: If ray-tracing execution fails.

---

## 5. `list_experiments`

### Purpose
Retrieve lightweight summary records for all previously persisted radio-map simulation experiments. This tool reads metadata without loading large NPZ numerical matrices into memory.

### Parameters
*None.* This tool takes no input arguments.

### Return Schema (`dict`)
- `status` (`str`): `"success"`.
- `count` (`int`): Total number of stored experiments.
- `experiments` (`list[dict]`): List of lightweight summaries containing:
  - `experiment_id` (`str`): Unique ID.
  - `experiment_name` (`str` or `null`): User-specified label.
  - `created_at` (`str`): ISO 8601 UTC creation timestamp.
  - `scene_name` (`str`): Scene identifier.
  - `frequency_hz` (`float`): Carrier frequency in Hz.
  - `measurement_height` (`float`): Height in meters.
  - `grid_dimensions` (`list[int]`): $[Ny, Nx]$.
  - `coverage_percentage` (`float`): Coverage percentage.
  - `mean_rss_dbm` (`float`): Mean received power.
  - `heatmaps_available` (`dict`): Boolean flags for RSS and Path Gain heatmaps.

### Sample Response
```json
{
  "status": "success",
  "count": 2,
  "experiments": [
    {
      "experiment_id": "experiment_20261101_135328_38565204",
      "experiment_name": "validation_run_30dbm",
      "created_at": "2026-11-01T13:53:28.159443+00:00",
      "scene_name": "simple_reflector",
      "frequency_hz": 3500000000.0,
      "measurement_height": 1.5,
      "grid_dimensions": [5, 3],
      "coverage_percentage": 100.0,
      "mean_rss_dbm": -32.09,
      "heatmaps_available": {
        "rss_heatmap": true,
        "path_gain_heatmap": true
      }
    }
  ]
}
```

---

## 6. `get_experiment_details`

### Purpose
Retrieve complete configuration metadata, antenna specifications, summary metrics, and absolute artifact paths for a specific saved experiment.

### Input Parameters

| Parameter | Type | Required? | Constraints & Description |
| :--- | :---: | :---: | :--- |
| `experiment_id` | `str` | **Required** | Unique identifier (e.g. `"experiment_20261101_135328_38565204"`). |

### Return Schema (`dict`)
- `status` (`str`): `"success"`.
- `experiment_id` (`str`): Experiment identifier.
- `experiment_name` (`str` or `null`): Label.
- `scene_name` (`str`): Scene name.
- `frequency_hz` (`float`): Frequency in Hz.
- `tx_position` (`list[float]`): $[x, y, z]$ coordinates.
- `tx_power_dbm` (`float`): Transmit power.
- `tx_orientation_deg` (`list[float]`): $[yaw, pitch, roll]$.
- `antenna_type` (`str`), `polarization` (`str`): Antenna settings.
- `measurement_height` (`float`): Plane height.
- `region_bounds` (`list[float]`): $[x_{\min}, x_{\max}, y_{\min}, y_{\max}]$.
- `cell_size` (`list[float]`): $[dx, dy]$.
- `grid_dimensions` (`list[int]`): $[Ny, Nx]$.
- `solver_parameters` (`dict`): Ray tracing parameters.
- `summary_metrics` (`dict`): Min, mean, max RSS, cell counts, coverage %.
- `artifact_paths` (`dict`): Absolute paths to PNGs, NPZ, and JSON.

### Possible Errors
- `ToolError`: If `experiment_id` is empty, contains path traversal characters, or the experiment does not exist (`FileNotFoundError`).

---

## 7. `compare_experiments`

### Purpose
Compare two saved radio-map simulation experiments across identical spatial geometries, evaluating received power difference and path-gain difference. Renders publication-quality centered diverging difference heatmaps.

### Comparison Convention
All differences strictly adhere to the **$B - A$ (Experiment B minus Experiment A)** convention:
$$\Delta \text{RSS}_{\text{dBm}} = \text{RSS}_B - \text{RSS}_A$$
$$\Delta \text{PathGain}_{\text{dB}} = \text{PathGain}_B - \text{PathGain}_A$$
- **Positive ($> 0$ dB):** Experiment B is stronger / has higher gain.
- **Negative ($< 0$ dB):** Experiment B is weaker / has lower gain.
- **Zero ($== 0$ dB):** Both experiments are physically identical.

### Input Parameters

| Parameter | Type | Required? | Default | Description |
| :--- | :---: | :---: | :---: | :--- |
| `experiment_id_a` | `str` | **Required** | — | Identifier of baseline/reference Experiment A. |
| `experiment_id_b` | `str` | **Required** | — | Identifier of modified Experiment B. |
| `generate_heatmaps` | `bool` | Optional | `True` | Whether to render difference PNG heatmaps. |

### Return Schema (`dict`)
- `status` (`str`): `"success"`.
- `difference_convention` (`str`): `"B - A (Experiment B minus Experiment A)"`.
- `experiment_a_id`, `experiment_b_id` (`str`): Compared IDs.
- `scene_name` (`str`): Scene name.
- `grid_dimensions` (`list[int]`): $[Ny, Nx]$.
- `total_cells` (`int`): Total cells evaluated.
- `valid_cells` (`int`): Cells where both A and B have finite power.
- `invalid_cells` (`int`): Cells unreached in either A or B (excluded from statistics).
- `rss_difference` (`dict`):
  - `mean_db` (`float`): Mean difference $\mu_\Delta$.
  - `min_db` (`float`): Minimum difference.
  - `max_db` (`float`): Maximum difference.
  - `std_db` (`float`): Standard deviation $\sigma_\Delta$.
- `path_gain_difference` (`dict`):
  - `mean_db` (`float`): Mean path gain difference.
  - `min_db`, `max_db`, `std_db` (`float`): Range and variance.
- `artifact_paths` (`dict`):
  - `rss_difference_heatmap` (`str` or `null`): Path to RSS difference PNG.
  - `path_gain_difference_heatmap` (`str` or `null`): Path to Path Gain difference PNG.

### Possible Errors
- `ToolError`: If either experiment ID is missing or not found on disk.
- `ToolError`: If experiments are spatially incompatible (different scenes, heights, grid dimensions, cell sizes, or misaligned coordinates).

