# Sionna RT Minimal Simulation (MCP Foundation - Step 1)

This project establishes the foundation for building a **Model Context Protocol (MCP)** server that enables AI agents to configure, execute, and analyze **NVIDIA Sionna RT** radio wave simulations through natural language.

In accordance with Step 1 of the development plan, this repository intentionally contains **no MCP code, no AI agent logic, no database, and no web UI**. It focuses strictly on a clean, verified, and minimal Python environment that runs genuine Sionna RT ray-tracing simulations.

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
│   ├── __init__.py          # Package initialization
│   ├── config.py            # Centralized simulation configuration dataclass
│   └── simulation.py        # Minimal end-to-end Sionna RT ray-tracing simulation
└── tests/
    └── test_simulation.py   # Automated tests verifying simulation execution and metrics
```

---

## Prerequisites & Backend Support

* **Python**: 3.10 to 3.12 (Python 3.11 recommended).
* **Execution Backends**:
  * **GPU / OptiX (`cuda_ad_mono_polarized`)**: Uses hardware-accelerated NVIDIA RT cores.
  * **CPU / LLVM (`llvm_ad_mono_polarized`)**: Uses JIT-compiled CPU vectorization. The simulation automatically falls back to LLVM if running inside environments where NVIDIA OptiX runtime libraries are not linked (such as standard WSL 2).

---

## Installation

1. **Clone the repository and enter the directory**:
   ```bash
   git clone <repo-url>
   cd Sionna_RT_MCP
   ```

2. **Create and activate a Python 3.11 virtual environment**:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## Environment Verification

Before running simulations, verify that Sionna RT and Mitsuba are correctly initialized:

```bash
python scripts/verify_env.py
```

Expected output:
```text
============================================================
       Sionna RT Environment Verification
============================================================
[✓] Python: Python 3.11.x
[✓] Sionna RT: sionna-rt v2.2.0
    Active Backend: llvm_ad_mono_polarized (CPU LLVM)
[✓] Scene Loading: Loaded built-in scene 'simple_reflector'
============================================================
RESULT: Environment is ready for Sionna RT simulations! ✓
```

---

## Running the Simulation

Execute the minimal ray-tracing simulation:

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

## Understanding the Output

* **Status Markers**:
  * `Scene loaded`: Confirms the 3D Mitsuba geometry is loaded into memory.
  * `Transmitter`: Transmitter added with configured position, antenna array, and power.
  * `Receiver`: Receiver added with configured position and antenna array.
  * `Frequency`: Carrier frequency applied to electromagnetic material properties.
  * `Ray tracing`: Ray shooting and path solving completed.
* **Metrics**:
  * **Total Paths Found**: Number of rays connecting TX to RX above the threshold.
  * **Total Path Loss (dB)**: $-10 \log_{10}\left(\sum_i |a_i|^2\right)$, measuring the attenuation between transmitter and receiver.
  * **Received Power (dBm)**: $P_{\text{TX}} - \text{PathLoss}$.
  * **Delay ($\tau$)**: Time taken for wavefront to travel from TX to RX. Distance is $c \times \tau$ (e.g., $66.71\text{ ns} \approx 20.0\text{ m}$, matching the geometric distance between $(0, -10, 5)$ and $(0, 10, 5)$).
  * **Type**: Physical interaction along the path (`Line of Sight`, `Specular Reflection`, `Diffraction`, etc.).

---

## Configuration

All configuration is located in one obvious place: [`src/config.py`](src/config.py).

```python
from src.config import SimulationConfig

config = SimulationConfig(
    scene_name="simple_reflector",           # Built-in scene name or path to XML
    frequency_hz=3.5e9,                      # 3.5 GHz
    tx_position=(0.0, -10.0, 5.0),           # TX coordinates in meters [x, y, z]
    tx_power_dbm=30.0,                       # Transmit power (30 dBm = 1 Watt)
    rx_position=(0.0, 10.0, 5.0),            # RX coordinates in meters [x, y, z]
    antenna_pattern="iso",                   # Antenna radiation pattern
    antenna_polarization="V",                # Polarization ('V', 'H', etc.)
)
```

---

## Running Automated Tests

Run the test suite using `pytest`:

```bash
pytest
```

The tests verify:
1. Simulation execution and result instantiation.
2. Physical validity of propagation metrics (positive delay, positive path loss, power consistency).
3. Response to modified parameters (e.g., 28 GHz mmWave frequency showing increased path loss).
4. Terminal output formatting compliance.
