# Sionna RT Minimal Simulation (MCP Foundation - Step 2)

This project establishes the foundation for building a **Model Context Protocol (MCP)** server that enables AI agents to configure, execute, and analyze **NVIDIA Sionna RT** radio wave simulations through natural language.

In accordance with Step 2 of the development plan, the simulation logic has been refactored into a reusable, modular **`SimulationEngine`** returning structured **`SimulationResult`** objects. Formatting and CLI execution are strictly decoupled. This repository contains **no MCP code yet, no database, and no web UI**.

---

## What is NVIDIA Sionna RT?

[NVIDIA Sionna RT](https://github.com/NVlabs/sionna-rt) is NVIDIA's open-source, differentiable ray tracer built on top of [Mitsuba 3](https://www.mitsuba-renderer.org/) and [Dr.Jit](https://github.com/mitsuba-renderer/drjit). It simulates 3D electromagnetic propagation between radio transmitters and receivers by tracing rays through geometric scenes. It computes:

* **Channel Impulse Response (CIR)**: Time-domain propagation delays ($\tau$) and complex path amplitudes ($a$).
* **Propagation Phenomena**: Line-of-sight (LOS), specular reflections, diffuse scattering, and diffraction.
* **Angular Metrics**: Angles of Departure (AoD) and Angles of Arrival (AoA).
* **Power Metrics**: Path loss (dB) and received power (dBm).

---

## Project Structure

```
Sionna_RT_MCP/
├── .gitignore               # Git ignore rules for virtualenv, caches, and logs
├── pytest.ini               # Pytest root and PYTHONPATH configuration
├── README.md                # Project documentation
├── requirements.txt         # Core dependencies (sionna-rt, numpy, pytest)
├── scripts/
│   └── verify_env.py        # Environment diagnostic and sanity check script
├── src/
│   ├── __init__.py          # Package initialization & exports
│   ├── config.py            # Centralized simulation configuration dataclass
│   ├── engine.py            # Reusable SimulationEngine executing ray tracing
│   ├── formatter.py         # Standalone terminal output formatter
│   ├── result.py            # Structured SimulationResult dataclass with to_dict()
│   └── simulation.py        # CLI entrypoint and backward-compatible helper
└── tests/
    ├── test_engine.py       # Tests for SimulationEngine, structured result, and JSON dict
    └── test_simulation.py   # Tests for simulation physical validity and backward compatibility
```

---

## Prerequisites & Backend Support

* **Python**: 3.10 to 3.12 (Python 3.11 recommended).
* **Execution Backends**:
  * **GPU / OptiX (`cuda_ad_mono_polarized`)**: Uses hardware-accelerated NVIDIA RT cores.
  * **CPU / LLVM (`llvm_ad_mono_polarized`)**: Uses JIT-compiled CPU vectorization. The simulation automatically falls back to LLVM if running inside environments where NVIDIA OptiX runtime libraries are not linked (such as standard WSL 2).

---

## Programmatic Usage

Call the simulation engine programmatically:

```python
from src.config import SimulationConfig
from src.engine import SimulationEngine
from src.formatter import format_result

# 1. Configure simulation
config = SimulationConfig(
    scene="simple_reflector",
    frequency=3.5e9,
    tx_position=[0, -10, 5],
    rx_position=[0, 10, 5],
    tx_power_dbm=30,
)

# 2. Run simulation engine
engine = SimulationEngine(config)
result = engine.run()

# 3. Access structured properties
print("Backend used:    ", result.backend)
print("Paths found:     ", result.number_of_paths)
print("Total path loss: ", result.total_path_loss, "dB")
print("Received power:  ", result.received_power, "dBm")
print("Path delays (ns):", result.path_delays)
print("Path distances:  ", result.path_distances)

# 4. Convert to JSON dictionary (for future MCP tools)
data_dict = result.to_dict()

# 5. Format for terminal display (handled separately)
print(format_result(result))
```

---

## Running the Simulation via CLI

Execute the simulation directly from the terminal:

```bash
python src/simulation.py
```

### Sample Output

```text
Scene loaded: ✓
Transmitter: ✓
Receiver: ✓
Frequency: 3.5 GHz ✓
Ray tracing: ✓

Propagation Results:
  Backend:               llvm_ad_mono_polarized
  Total Paths Found:     2
  Total Path Loss:       66.80 dB
  Received Power:        -36.80 dBm (from 30.0 dBm TX)
  Delay Range:           66.71 ns to 74.59 ns

  Individual Path Breakdown:
    Path #1: Delay =  66.71 ns (20.00 m) | Path Gain =  -69.35 dB | Type = Line of Sight (LOS)
    Path #2: Delay =  74.59 ns (22.36 m) | Path Gain =  -70.32 dB | Type = Specular Reflection
```

---

## Running Automated Tests

Run the test suite using `pytest`:

```bash
pytest
```

The tests verify:
1. `SimulationEngine` runs and produces a structured `SimulationResult`.
2. All core metrics (frequency, TX/RX positions, paths, delays, distances, gains, path loss, received power, backend) are present and accurate.
3. Structured results cleanly serialize to JSON dictionaries via `to_dict()`.
4. Standalone terminal formatter produces expected output without engine coupling.
5. Physical validity of propagation metrics (positive delay, positive path loss, power consistency).
6. Parameter responsiveness (e.g., 28 GHz mmWave frequency showing increased path loss).
