"""Configuration parameters for the Sionna RT simulation.

Central place for all simulation parameters:
- Scene selection
- Carrier frequency
- Transmitter position and power
- Receiver position
- Antenna array configurations
"""

from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class SimulationConfig:
    """Simulation configuration parameters."""

    # Scene name (must match built-in scene in sionna.rt.scene or XML path)
    scene_name: str = "simple_reflector"

    # Carrier frequency in Hertz (default: 3.5 GHz)
    frequency_hz: float = 3.5e9

    # Transmitter configuration
    tx_name: str = "tx"
    tx_position: Tuple[float, float, float] = (0.0, -10.0, 5.0)  # [x, y, z] in meters
    tx_power_dbm: float = 30.0  # Transmit power in dBm (1 Watt = 30 dBm)

    # Receiver configuration
    rx_name: str = "rx"
    rx_position: Tuple[float, float, float] = (0.0, 10.0, 5.0)  # [x, y, z] in meters

    # Antenna array configuration
    antenna_pattern: str = "iso"  # Isotropic antenna pattern
    antenna_polarization: str = "V"  # Vertical polarization
    num_rows: int = 1
    num_cols: int = 1
    vertical_spacing: float = 0.5  # In wavelengths
    horizontal_spacing: float = 0.5  # In wavelengths
