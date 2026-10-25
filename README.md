# Sionna RT Model Context Protocol (MCP) Server - Step 3

This project provides a **Model Context Protocol (MCP)** server that enables AI clients (such as Claude Desktop, Cursor, or custom MCP agents) to configure, execute, and analyze **NVIDIA Sionna RT** radio wave simulations through structured tools.

---

## Architecture

The system follows a strict layered architecture:

```text
AI / MCP Client (Claude Desktop, Cursor, etc.)
      │  (stdio JSON-RPC transport)
      ▼
MCP Server (`src/mcp_server.py`)
      │  (validation & tool routing)
      ▼
SimulationEngine (`src/engine.py`)
      │  (scene loading, transceivers, path solving)
      ▼
NVIDIA Sionna RT & Mitsuba 3
      │  (GPU OptiX or CPU LLVM ray tracing)
      ▼
SimulationResult (`src/result.py`)
      │  (propagation metrics & JSON serialization)
      ▼
MCP Response (structured content & text)
```

The MCP server acts as an interface layer only. It contains **no ray-tracing logic**, which remains encapsulated in `SimulationEngine`.

---

## Project Structure

```
Sionna_RT_MCP/
├── .gitignore               # Git ignore rules for virtualenv, caches, and logs
├── pytest.ini               # Pytest root and PYTHONPATH configuration
├── README.md                # Project documentation
├── requirements.txt         # Core dependencies (sionna-rt, numpy, pytest, mcp)
├── scripts/
│   ├── verify_env.py        # Environment diagnostic and sanity check script
│   └── verify_mcp_client.py # Automated end-to-end MCP client verification script
├── src/
│   ├── __init__.py          # Package initialization & public exports
│   ├── config.py            # Centralized simulation configuration dataclass
│   ├── engine.py            # Reusable SimulationEngine executing ray tracing
│   ├── formatter.py         # Standalone terminal output formatter
│   ├── mcp_server.py        # Model Context Protocol (MCP) server over stdio
│   ├── result.py            # Structured SimulationResult dataclass with to_dict()
│   └── simulation.py        # CLI entrypoint and backward-compatible helper
└── tests/
    ├── test_engine.py       # Tests for SimulationEngine, structured result, and JSON dict
    ├── test_mcp.py          # Unit & integration tests for MCP server tools and stdio client
    └── test_simulation.py   # Tests for simulation physical validity and backward compatibility
```

---

## MCP Tools Implemented

The server registers exactly three focused tools:

### 1. `check_environment`
* **Purpose**: Verify whether Python, Sionna RT, and Mitsuba are installed and operational, identifying the active computational backend.
* **Inputs**: None.
* **Returns**: Structured dictionary with `python_version`, `sionna_version`, `mitsuba_version`, `backend`, and `is_usable`.

### 2. `list_scenes`
* **Purpose**: Discover 3D geometric propagation environments available to the simulation engine.
* **Inputs**: None.
* **Returns**: Catalog of scenes, including the canonical `simple_reflector` scene.

### 3. `run_simulation`
* **Purpose**: Execute an NVIDIA Sionna RT ray-tracing simulation and return physical propagation metrics.
* **Inputs**:
  * `scene` (str, default `"simple_reflector"`): Geometric scene identifier.
  * `frequency_hz` (float, default `3.5e9`): Radio carrier frequency in **Hertz** (Hz, NOT GHz; e.g. `3500000000.0` for 3.5 GHz). Must be > 0.
  * `tx_position` (list of 3 floats, default `[0.0, -10.0, 5.0]`): 3D coordinates [x, y, z] in meters.
  * `rx_position` (list of 3 floats, default `[0.0, 10.0, 5.0]`): 3D coordinates [x, y, z] in meters.
  * `tx_power_dbm` (float, default `30.0`): Transmitter power in dBm (30 dBm = 1 Watt).
* **Returns**: Structured propagation results:
  * `num_paths`: Total paths resolved (e.g. 2 for simple_reflector).
  * `total_path_loss`: Attenuation in dB (e.g. ~66.8 dB).
  * `received_power`: Received power in dBm (e.g. ~-36.8 dBm).
  * `path_delays`: Nanosecond delay per path (e.g. [66.71, 74.59] ns).
  * `path_distances`: Propagation distance per path in meters.
  * `path_gains`: Linear gain per path in dB.
  * `interaction_types`: Physical propagation mechanism (Line of Sight, Specular Reflection, etc.).

---

## Connecting MCP Clients

The server runs locally over standard input/output (`stdio`).

### Starting the Server Standalone

```bash
.venv/bin/python src/mcp_server.py
```

All diagnostic and error logs are directed strictly to `stderr`, keeping `stdout` completely clean for JSON-RPC MCP messages.

### Claude Desktop Configuration

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sionna_rt": {
      "command": "/home/sarvesh/Developer/Projects/Sionna_RT_MCP/.venv/bin/python",
      "args": [
        "/home/sarvesh/Developer/Projects/Sionna_RT_MCP/src/mcp_server.py"
      ]
    }
  }
}
```

---

## Verification & Automated Testing

### 1. Run Automated Test Suite

```bash
pytest -v
```

All 12 automated unit and integration tests verify:
* MCP server startup and tool registration (exactly 3 tools).
* `check_environment` and `list_scenes` structured outputs.
* `run_simulation` real ray-tracing execution and physical validity.
* Clean error handling on invalid frequency, position, or scene without tracebacks.
* End-to-end `stdio_client` and `ClientSession` communication.

### 2. Run End-to-End MCP Client Verification Script

```bash
python scripts/verify_mcp_client.py
```

This script launches the MCP server in a subprocess over stdio, performs tool discovery, queries the environment, lists scenes, runs a full simulation, and asserts physical propagation accuracy against Sionna RT.
