"""Configuration parameters for the Sionna RT simulation.

Central place for all simulation parameters:
- Scene selection
- Carrier frequency
- Transmitter position and power
- Receiver position
- Antenna array configurations (isotropic, dipole, directional)
- Polarization and element spacings
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

# Mapping user-friendly antenna categories to verified Sionna RT pattern names
# Verified against NVIDIA Sionna RT PlanarArray pattern specifications
ANTENNA_PATTERN_MAPPING: Dict[str, str] = {
    "isotropic": "iso",
    "iso": "iso",
    "omni": "iso",
    "omnidirectional": "iso",
    "dipole": "dipole",
    "hw_dipole": "dipole",
    "directional": "tr38901",
    "tr38901": "tr38901",
}

VALID_POLARIZATIONS: Set[str] = {"V", "H", "VH", "cross"}


@dataclass
class SimulationConfig:
    """Simulation configuration parameters for point-to-point propagation."""

    # Scene name (must match built-in scene in sionna.rt.scene or XML path)
    scene_name: str = "simple_reflector"

    # Carrier frequency in Hertz (default: 3.5 GHz)
    frequency_hz: float = 3.5e9

    # Transmitter configuration
    tx_name: str = "tx"
    tx_position: Tuple[float, float, float] = (0.0, -10.0, 5.0)  # [x, y, z] in meters
    tx_power_dbm: float = 30.0  # Transmit power in dBm (1 Watt = 30 dBm)
    tx_orientation_deg: Optional[Tuple[float, float, float]] = None  # (yaw, pitch, roll)

    # Receiver configuration
    rx_name: str = "rx"
    rx_position: Tuple[float, float, float] = (0.0, 10.0, 5.0)  # [x, y, z] in meters
    rx_orientation_deg: Optional[Tuple[float, float, float]] = None  # (yaw, pitch, roll)

    # Antenna array configuration
    antenna_pattern: str = "iso"  # Base antenna pattern ("iso", "dipole", "tr38901")
    antenna_polarization: str = "V"  # Polarization ("V", "H", "VH", "cross")
    num_rows: int = 1
    num_cols: int = 1
    vertical_spacing: float = 0.5  # In wavelengths
    horizontal_spacing: float = 0.5  # In wavelengths

    # Extended antenna parameters
    antenna_type: Optional[str] = None
    tx_antenna_type: Optional[str] = None
    rx_antenna_type: Optional[str] = None
    tx_antenna_pattern: Optional[str] = None
    rx_antenna_pattern: Optional[str] = None
    polarization: Optional[str] = None

    # Optional alias parameters for caller convenience
    scene: Optional[str] = None
    frequency: Optional[float] = None

    def __post_init__(self) -> None:
        """Handle alias parameters, resolve antenna patterns, and normalize types."""
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

        # Polarization alias
        if self.polarization is not None:
            pol_clean = str(self.polarization).strip()
            if pol_clean in VALID_POLARIZATIONS:
                self.antenna_polarization = pol_clean
            elif pol_clean.upper() in VALID_POLARIZATIONS:
                self.antenna_polarization = pol_clean.upper()
            else:
                valid_list = ", ".join(sorted(VALID_POLARIZATIONS))
                raise ValueError(
                    f"Unsupported antenna polarization '{self.polarization}'. Supported values: {valid_list}."
                )

        # Resolve base antenna pattern
        if self.antenna_type is not None:
            norm_type = str(self.antenna_type).strip().lower()
            if norm_type in ANTENNA_PATTERN_MAPPING:
                self.antenna_pattern = ANTENNA_PATTERN_MAPPING[norm_type]
            else:
                valid_antennas = ", ".join(sorted({"isotropic", "dipole", "directional"}))
                raise ValueError(
                    f"Unsupported antenna type '{self.antenna_type}'. Supported antenna types: {valid_antennas}."
                )
        else:
            norm_pattern = str(self.antenna_pattern).strip().lower()
            if norm_pattern in ANTENNA_PATTERN_MAPPING:
                self.antenna_pattern = ANTENNA_PATTERN_MAPPING[norm_pattern]
            else:
                valid_antennas = ", ".join(sorted({"isotropic", "dipole", "directional"}))
                raise ValueError(
                    f"Unsupported antenna pattern '{self.antenna_pattern}'. Supported antenna types: {valid_antennas}."
                )

        # Resolve TX antenna pattern
        if self.tx_antenna_type is not None:
            norm_tx = str(self.tx_antenna_type).strip().lower()
            if norm_tx in ANTENNA_PATTERN_MAPPING:
                self.tx_antenna_pattern = ANTENNA_PATTERN_MAPPING[norm_tx]
            else:
                valid_antennas = ", ".join(sorted({"isotropic", "dipole", "directional"}))
                raise ValueError(
                    f"Unsupported TX antenna type '{self.tx_antenna_type}'. Supported antenna types: {valid_antennas}."
                )
        elif self.tx_antenna_pattern is not None:
            norm_tx_pat = str(self.tx_antenna_pattern).strip().lower()
            if norm_tx_pat in ANTENNA_PATTERN_MAPPING:
                self.tx_antenna_pattern = ANTENNA_PATTERN_MAPPING[norm_tx_pat]
            else:
                valid_antennas = ", ".join(sorted({"isotropic", "dipole", "directional"}))
                raise ValueError(
                    f"Unsupported TX antenna pattern '{self.tx_antenna_pattern}'. Supported antenna types: {valid_antennas}."
                )
        else:
            self.tx_antenna_pattern = self.antenna_pattern

        # Resolve RX antenna pattern
        if self.rx_antenna_type is not None:
            norm_rx = str(self.rx_antenna_type).strip().lower()
            if norm_rx in ANTENNA_PATTERN_MAPPING:
                self.rx_antenna_pattern = ANTENNA_PATTERN_MAPPING[norm_rx]
            else:
                valid_antennas = ", ".join(sorted({"isotropic", "dipole", "directional"}))
                raise ValueError(
                    f"Unsupported RX antenna type '{self.rx_antenna_type}'. Supported antenna types: {valid_antennas}."
                )
        elif self.rx_antenna_pattern is not None:
            norm_rx_pat = str(self.rx_antenna_pattern).strip().lower()
            if norm_rx_pat in ANTENNA_PATTERN_MAPPING:
                self.rx_antenna_pattern = ANTENNA_PATTERN_MAPPING[norm_rx_pat]
            else:
                valid_antennas = ", ".join(sorted({"isotropic", "dipole", "directional"}))
                raise ValueError(
                    f"Unsupported RX antenna pattern '{self.rx_antenna_pattern}'. Supported antenna types: {valid_antennas}."
                )
        else:
            self.rx_antenna_pattern = self.antenna_pattern

        # Normalize orientations if provided
        if self.tx_orientation_deg is not None:
            self.tx_orientation_deg = (
                float(self.tx_orientation_deg[0]),
                float(self.tx_orientation_deg[1]),
                float(self.tx_orientation_deg[2]),
            )
        if self.rx_orientation_deg is not None:
            self.rx_orientation_deg = (
                float(self.rx_orientation_deg[0]),
                float(self.rx_orientation_deg[1]),
                float(self.rx_orientation_deg[2]),
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to a dictionary."""
        return {
            "scene_name": self.scene_name,
            "frequency_hz": self.frequency_hz,
            "tx_name": self.tx_name,
            "tx_position": list(self.tx_position),
            "tx_power_dbm": self.tx_power_dbm,
            "tx_orientation_deg": list(self.tx_orientation_deg) if self.tx_orientation_deg is not None else None,
            "rx_name": self.rx_name,
            "rx_position": list(self.rx_position),
            "rx_orientation_deg": list(self.rx_orientation_deg) if self.rx_orientation_deg is not None else None,
            "antenna_pattern": self.antenna_pattern,
            "antenna_polarization": self.antenna_polarization,
            "num_rows": self.num_rows,
            "num_cols": self.num_cols,
            "vertical_spacing": self.vertical_spacing,
            "horizontal_spacing": self.horizontal_spacing,
            "tx_antenna_pattern": self.tx_antenna_pattern,
            "rx_antenna_pattern": self.rx_antenna_pattern,
        }
