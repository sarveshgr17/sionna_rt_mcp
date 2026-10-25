# Sionna RT Model Context Protocol (MCP) Server

An end-to-end bridge connecting **LLM AI agents** to **NVIDIA Sionna RT** through the **Model Context Protocol (MCP)**. This enables AI systems to autonomously discover propagation tools, configure radio frequency (RF) simulations, execute 3D ray tracing, derive physical wireless channel metrics, generate publication-quality visualizations, and interpret multi-frequency propagation phenomena.

---

## 1. Project Purpose & Problem Solved

Modern AI assistants excel at natural language reasoning and high-level problem solving, but lack direct access to physical radio-frequency propagation engines. Conversely, RF simulation frameworks like NVIDIA Sionna RT provide state-of-the-art ray tracing, but require specialized Python scripts and Mitsuba rendering pipelines.

**This project solves that interface barrier by providing:**
1. A **standardized Model Context Protocol (MCP) server** exposing deterministic radio ray-tracing capabilities over standard input/output (`stdio` JSON-RPC).
2. A **simulation engine** abstracting Mitsuba 3 backend selection (GPU NVIDIA OptiX or CPU LLVM JIT fallback).
3. A **wireless channel analysis layer** calculating derived RF metrics (strongest path, Line of Sight detection, RMS delay spread, power contribution breakdown).
4. A **visualization layer** generating top-down 2D ray trajectories, power waterfall budgets, Channel Impulse Response (CIR) stem plots, and comparative visualizations.
5. An **autonomous AI agent client** that dynamically chains tools to answer complex multi-frequency tasks (e.g., comparing 3.5 GHz mid-band vs 28.0 GHz millimeter-wave propagation).

---

## 2. System Architecture

The project adheres to a strict, layered architecture with clean separation of concerns:

```text
Natural-Language Task (e.g. "Compare 3.5 GHz and 28 GHz between TX and RX")
       │
       ▼
AI Agent Client (`scripts/agent_client.py`)
       │  • Task parsing (regex parameter extraction)
       │  • Tool discovery & multi-step execution planning
       │  • stdio JSON-RPC transport
       ▼
MCP Server (`src/mcp_server.py`)
       │  • Strict Pydantic input validation & schema enforcement
       │  • Standardized ToolError generation
       │  • Clean routing to backend components
       ▼
SimulationEngine (`src/engine.py`)
       │  • Mitsuba backend variant management (CUDA OptiX or CPU LLVM)
       │  • Transceiver placement & antenna array setup
       │  • Path solving & ray extraction
       ▼
NVIDIA Sionna RT (`sionna.rt`) & Mitsuba 3 (`mitsuba`)
       │  • 3D electromagnetic ray tracing
       ▼
SimulationResult (`src/result.py`)
       │  • Immutable container for raw propagation data
       ▼
ChannelAnalyzer (`src/analyzer.py`)
       │  • RMS delay spread calculation
       │  • Strongest path identification
       │  • Line-of-Sight (LOS) vs Non-Line-of-Sight (NLOS) detection
       │  • Path percentage power contributions
       ▼
SimulationStorage (`src/storage.py`) & Visualizer (`src/visualizer.py`)
       │  • Unique timestamped storage (`results/<simulation_id>/`)
       │  • 2D propagation paths, power budget, CIR, and comparison plots
       ▼
AI-Readable Response & Human Explanation
```

---

## 3. Environment Requirements & Installation

### Requirements
* **Operating System**: Linux (Ubuntu 20.04/22.04 LTS or WSL2 on Windows)
* **Python**: Python 3.10 or 3.11 (tested on 3.11.15)
* **Hardware/Accelerators**:
  * **GPU (Recommended)**: NVIDIA GPU with CUDA and OptiX support (`libnvoptix.so.1`)
  * **CPU (Fully Supported Fallback)**: Multi-core x86_64 CPU running LLVM JIT (`llvm_ad_mono_polarized`)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd Sionna_RT_MCP
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Verify environment health**:
   ```bash
   python scripts/verify_env.py
   ```

---

## 4. MCP Tools Catalog

The MCP server exposes 5 deterministic tools over `stdio`:

### 1. `check_environment`
* **Purpose**: Inspect simulator availability, Mitsuba/Sionna versions, and computational backend.
* **Input Schema**: None `{}`.
* **Returns**:
  ```json
  {
    "python_version": "3.11.15",
    "sionna_version": "2.2.0",
    "mitsuba_version": "3.9.1",
    "backend": "llvm_ad_mono_polarized",
    "is_usable": true
  }
  ```

### 2. `list_scenes`
* **Purpose**: Discover 3D geometric propagation environments available to the simulation engine.
* **Input Schema**: None `{}`.
* **Returns**: Catalog of scenes including name, description, and default status (`simple_reflector`).

### 3. `run_simulation`
* **Purpose**: Execute raw 3D electromagnetic ray tracing and return physical propagation metrics.
* **Inputs**:
  * `scene` (string, default: `"simple_reflector"`)
  * `frequency_hz` (float, in Hertz, > 0, default: `3.5e9`)
  * `tx_position` (list of 3 floats `[x, y, z]` in meters, default: `[0.0, -10.0, 5.0]`)
  * `rx_position` (list of 3 floats `[x, y, z]` in meters, default: `[0.0, 10.0, 5.0]`)
  * `tx_power_dbm` (float, in dBm, default: `30.0`)
* **Returns**: `simulation_id`, `num_paths`, `total_path_loss_db`, `received_power_dbm`, `delays_ns`, `path_distances_m`, `path_gains_db`, `interaction_types`.

### 4. `analyze_simulation`
* **Purpose**: Execute ray tracing AND perform physical wireless channel analysis.
* **Inputs**: Same as `run_simulation`.
* **Returns**: Composite dictionary containing `simulation_id`, `simulation` dictionary, and `analysis` dictionary:
  * `strongest_path`: Index, interaction type, gain (dB), delay (ns), distance (m).
  * `los_present`: Boolean indicating whether direct Line of Sight exists.
  * `los_path_index`: 1-based path index of the LOS ray (or `null`).
  * `rms_delay_spread_ns`: RMS delay spread in nanoseconds.
  * `paths`: List of all paths with individual percentage power contribution (`power_contribution_percent`).

### 5. `generate_visualization`
* **Purpose**: Render publication-quality plots from completed simulations.
* **Inputs**:
  * `simulation_id` (string, required): Existing simulation identifier.
  * `plot_type` (string, default: `"all"`): One of `"all"`, `"propagation_paths"`, `"received_power"`, `"cir"`, or `"comparison"`.
  * `comparison_simulation_id` (string, optional): Required if `plot_type="comparison"`.
* **Returns**: List of generated image file paths on disk.

---

## 5. Simulation Storage & Reproducibility

Every simulation executed through `run_simulation` or `analyze_simulation` is stored under a unique timestamped identifier (`sim_YYYYMMDD_HHMMSS_<hex>`):

```text
results/<simulation_id>/
├── config.json              # Transceiver geometry and simulation configuration
├── metrics.json             # Simulation outputs and derived channel analysis
├── propagation_paths.png    # 2D top-down ray tracing geometry and multipath trajectories
├── received_power.png       # Link power budget and attenuation waterfall bar chart
├── cir.png                  # Discrete Channel Impulse Response (CIR) stem plot
└── comparison.png           # Dual-panel comparative visualization (Power/loss delta + CIR overlay)
```

Historical runs are never overwritten. A stored simulation can be inspected or re-visualized at any time using its `simulation_id`.

---

## 6. How to Run & Verify

### 1. Basic Standalone Simulation
```bash
python src/simulation.py
```

### 2. Connect via MCP AI Clients (Claude Desktop / Cursor)
Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "sionna_rt": {
      "command": "/absolute/path/to/Sionna_RT_MCP/.venv/bin/python",
      "args": [
        "/absolute/path/to/Sionna_RT_MCP/src/mcp_server.py"
      ]
    }
  }
}
```

### 3. Run Automated Verification Scripts
```bash
# Verify environment runtime
python scripts/verify_env.py

# Verify MCP client JSON-RPC tool calls
python scripts/verify_mcp_client.py

# Verify AI agent tool chaining & visualization
python scripts/verify_agent.py
```

### 4. Run Complete Automated Pytest Suite (37 Tests)
```bash
pytest -v
```

### 5. End-to-End Natural-Language Demonstration
```bash
python scripts/agent_client.py "Compare propagation at 3.5 GHz and 28 GHz between TX [0, -10, 5] and RX [0, 10, 5]. Show the propagation paths and explain the difference."
```

---

## 7. Known Limitations

1. **Deterministic Parsing**: The AI client agent in `scripts/agent_client.py` uses deterministic regular expressions expecting bracketed coordinates (`[x, y, z]`) and explicit frequency units (`GHz`, `MHz`, `Hz`). Unstructured or colloquial language (e.g. "move the transmitter 10 meters north") is not supported.
2. **Scene Catalog**: Ray tracing currently targets the canonical `simple_reflector` scene. Arbitrary polygonal meshes or complex city maps require importing additional OBJ/XML scene models.
3. **CPU Execution on WSL**: When NVIDIA OptiX drivers (`libnvoptix.so.1`) are absent in container or WSL environments, Mitsuba automatically defaults to the CPU LLVM JIT backend (`llvm_ad_mono_polarized`). While physically accurate, execution is CPU-bound rather than hardware-accelerated.
4. **Antenna Array Patterns**: Transceivers currently default to isotropic radiation patterns with vertical polarization (`iso`, `V`).
