# Architecture Specification: Sionna RT + Model Context Protocol (MCP)

This document provides the formal architectural specification for the Sionna RT MCP system, describing component boundaries, layering principles, data flow, and separation of responsibilities.

---

## 1. High-Level Architectural Diagram

```text
       ┌─────────────────────────────────────────────────────────────┐
       │                     Natural Language Task                   │
       │   "Compare propagation at 3.5 GHz and 28 GHz between        │
       │    TX [0, -10, 5] and RX [0, 10, 5]..."                     │
       └──────────────────────────────┬──────────────────────────────┘
                                      │
                                      ▼
       ┌─────────────────────────────────────────────────────────────┐
       │                         AI Agent                            │
       │  • Task understanding & parameter extraction                │
       │  • Tool sequence decision-making & tool chaining            │
       │  • Physical synthesis & explanation generation              │
       └──────────────────────────────┬──────────────────────────────┘
                                      │
                                      ▼
       ┌─────────────────────────────────────────────────────────────┐
       │                        MCP Client                           │
       │  • Dynamic tool discovery via MCP protocol                  │
       │  • Standard input/output (stdio) JSON-RPC communication     │
       │  • Response deserialization & error unwrapping              │
       └──────────────────────────────┬──────────────────────────────┘
                                      │
                                      ▼
       ┌─────────────────────────────────────────────────────────────┐
       │                        MCP Server                           │
       │  • Tool declaration & schema definition (Pydantic)          │
       │  • Input validation & AI-readable ToolError formatting      │
       │  • Stateless interface layer (NO ray tracing or LLM logic)  │
       └──────────────┬──────────────────────────────┬───────────────┘
                      │                              │
         [simulation / analysis]              [visualization]
                      │                              │
                      ▼                              ▼
       ┌──────────────────────────────┐┌─────────────────────────────┐
       │       SimulationEngine       ││          Visualizer         │
       │  • Transceiver placement     ││  • 2D Top-down ray geometry │
       │  • Scene & antenna setup     ││  • Power budget waterfall   │
       │  • Backend initialization    ││  • Channel Impulse Response │
       └──────────────┬───────────────┘│  • Frequency comparison     │
                      │                └─────────────┬───────────────┘
                      ▼                              │
       ┌──────────────────────────────┐              │
       │      NVIDIA Sionna RT        │              │
       │  • Electromagnetic ray solver│              │
       │  • Path finding & reflection │              │
       └──────────────┬───────────────┘              │
                      │                              │
                      ▼                              │
       ┌──────────────────────────────┐              │
       │       SimulationResult       │              │
       │  • Raw delays, gains, paths  │              │
       └──────────────┬───────────────┘              │
                      │                              │
                      ▼                              │
       ┌──────────────────────────────┐              │
       │       ChannelAnalyzer        │              │
       │  • Strongest path            │              │
       │  • RMS delay spread          │              │
       │  • Line of Sight detection   │              │
       │  • Power contributions       │              │
       └──────────────┬───────────────┘              │
                      │                              │
                      ▼                              ▼
       ┌─────────────────────────────────────────────────────────────┐
       │                      SimulationStorage                      │
       │  • Deterministic directory: results/<simulation_id>/        │
       │  • Stored: config.json, metrics.json, *.png plots           │
       └─────────────────────────────────────────────────────────────┘
```

---

## 2. Layer Responsibilities & Separation of Concerns

### A. AI Agent (`scripts/agent_client.py`)
* **Role**: Reasoning, task decomposition, and tool-chaining decision maker.
* **Responsibilities**:
  * Interprets the user's natural-language task (e.g. carrier frequencies, coordinates, scenes).
  * Decides the exact sequence of MCP tool calls needed to achieve the goal:
    `check_environment` $\rightarrow$ `list_scenes` $\rightarrow$ `analyze_simulation` $\rightarrow$ `generate_visualization`.
  * Compares multiple scenario runs (e.g., calculating path loss delta between 3.5 GHz and 28 GHz).
  * Synthesizes raw numbers into a scientifically sound, AI-readable explanation (e.g., explaining Friis free-space path loss scaling and multipath geometric invariance).
* **Boundary Rule**: The agent does **not** contain electromagnetic physics solvers or ray-tracing code; it strictly orchestrates tools through the MCP client.

### B. MCP Client (`scripts/agent_client.py`, `scripts/verify_mcp_client.py`)
* **Role**: Communication adapter for the Model Context Protocol.
* **Responsibilities**:
  * Spawns the MCP server subprocess over `stdio`.
  * Negotiates protocol versions and dynamically discovers available tools.
  * Encapsulates argument serialization and response extraction (`extract_mcp_data`).
  * Catches `ToolError` and process communication faults.

### C. MCP Server (`src/mcp_server.py`)
* **Role**: Standardized tool interface exposing simulator capabilities.
* **Responsibilities**:
  * Defines clean, self-documenting tool schemas with explicit units (Hz, dBm, meters).
  * Validates all incoming arguments strictly using Pydantic fields.
  * Converts runtime exceptions into concise, AI-readable `ToolError` strings without leaking raw Python stack traces into tool response frames.
* **Boundary Rule**: The MCP server is a **thin interface layer**. It contains **no LLM** and **no ray-tracing logic**. It simply delegates to `SimulationEngine`, `ChannelAnalyzer`, `SimulationStorage`, and `Visualizer`.

### D. SimulationEngine (`src/engine.py`)
* **Role**: Encapsulation of NVIDIA Sionna RT scene lifecycle.
* **Responsibilities**:
  * Ensures a valid Mitsuba 3 computational backend is selected (`ensure_mitsuba_variant()`), probing GPU OptiX and falling back to CPU LLVM (`llvm_ad_mono_polarized`).
  * Configures the carrier frequency, antenna arrays, and transceiver locations.
  * Solves propagation paths using Sionna RT's `PathSolver`.
  * Extracts path delays, distances, interaction types, and power gains into an immutable `SimulationResult`.

### E. ChannelAnalyzer (`src/analyzer.py`)
* **Role**: Domain-specific wireless channel processing.
* **Responsibilities**:
  * Derives physical channel metrics from the raw `SimulationResult`.
  * Identifies the strongest path and extracts its delay, gain, and interaction type.
  * Calculates the RMS delay spread ($\sigma_\tau = \sqrt{\overline{\tau^2} - (\overline{\tau})^2}$) weighted by linear path power.
  * Identifies Line of Sight (LOS) presence.
  * Computes percentage power contributions for all multipath components.

### F. SimulationStorage (`src/storage.py`)
* **Role**: Artifact persistence and reproducibility.
* **Responsibilities**:
  * Allocates unique timestamped simulation directories (`results/sim_YYYYMMDD_HHMMSS_<hex>/`).
  * Persists `config.json` (inputs) and `metrics.json` (simulation outputs + channel analysis).
  * Guarantees that historical simulations are never overwritten.
  * Enables retrieval of any prior run by its `simulation_id`.

### G. Visualizer (`src/visualizer.py`)
* **Role**: Publication-quality headless plot generation.
* **Responsibilities**:
  * Renders 2D top-down geometric ray paths showing direct LOS and specular reflections.
  * Generates power budget waterfall bar charts (TX power vs total path loss vs RX power).
  * Plots discrete Channel Impulse Response (CIR) stem graphs.
  * Produces side-by-side scenario comparisons (e.g. 3.5 GHz vs 28 GHz).
  * Gracefully handles edge cases such as empty propagation paths.

---

## 3. Data Flow Specification

1. **User Task**: `"Compare propagation at 3.5 GHz and 28 GHz between TX [0, -10, 5] and RX [0, 10, 5]."`
2. **AI Agent Parser**:
   ```python
   {
       "scene": "simple_reflector",
       "frequencies_hz": [3.5e9, 28.0e9],
       "tx_position": [0.0, -10.0, 5.0],
       "rx_position": [0.0, 10.0, 5.0],
       "tx_power_dbm": 30.0,
       "is_comparison": True
   }
   ```
3. **Execution Chain**:
   - `check_environment()` $\rightarrow$ confirms backend readiness.
   - `list_scenes()` $\rightarrow$ confirms `simple_reflector` is supported.
   - `analyze_simulation(3.5 GHz)` $\rightarrow$ runs ray tracing; outputs `sim_20261025_141541_edd722`.
   - `analyze_simulation(28.0 GHz)` $\rightarrow$ runs ray tracing; outputs `sim_20261025_141541_caa9aa`.
   - `generate_visualization(sim_1, plot_type="comparison", comparison_id=sim_2)` $\rightarrow$ saves `comparison.png`.
   - `generate_visualization(sim_1, plot_type="all")` $\rightarrow$ saves `propagation_paths.png`, `received_power.png`, `cir.png`.
4. **Report Synthesis**:
   Agent evaluates results against Friis' equation $\Delta PL = 20 \log_{10}(28.0/3.5) \approx 18.06\text{ dB}$ and presents structured table + scientific explanation.
