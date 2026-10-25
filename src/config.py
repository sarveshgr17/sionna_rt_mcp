"""Configuration parameters for the Sionna RT simulation.

Central place for all simulation parameters:
- Scene selection
- Carrier frequency
- Transmitter position and power
- Receiver position
- Antenna array configurations
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple


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

    # Optional alias parameters for caller convenience
    scene: Optional[str] = None
    frequency: Optional[float] = None

    def __post_init__(self) -> None:
        """Handle alias parameters and normalize types."""
        if self.scene is not None:
            self.scene_name = str(self.scene)
        else:
            self.scene = self.scene_name

        if self.frequency is not None:
            self.frequency_hz = float(self.frequency)
        else:
            self.frequency = self.frequency_hz

        if self.tx_position is not None:
            self.tx_position = (
                float(self.tx_position[0]),
                float(self.tx_position[1]),
                float(self.tx_position[2]),
            )

        if self.rx_position is not None:
            self.rx_position = (
                float(self.rx_position[0]),
                float(self.rx_position[1]),
                float(self.rx_position[2]),
            )

        self.tx_power_dbm = float(self.tx_power_dbm)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to a dictionary."""
        return {
            "scene_name": self.scene_name,
            "frequency_hz": self.frequency_hz,
            "tx_name": self.tx_name,
            "tx_position": list(self.tx_position),
            "tx_power_dbm": self.tx_power_dbm,
            "rx_name": self.rx_name,
            "rx_position": list(self.rx_position),
            "antenna_pattern": self.antenna_pattern,
            "antenna_polarization": self.antenna_polarization,
            "num_rows": self.num_rows,
            "num_cols": self.num_cols,
            "vertical_spacing": self.vertical_spacing,
            "horizontal_spacing": self.horizontal_spacing,
        }
