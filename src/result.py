"""Structured result data models for Sionna RT simulation."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class SimulationResult:
    """Container for extracted propagation results."""

    scene_name: str
    frequency_hz: float
    tx_position: Tuple[float, float, float]
    tx_power_dbm: float
    rx_position: Tuple[float, float, float]
    backend_variant: str
    num_paths: int
    path_loss_db: float
    rx_power_dbm: float
    min_delay_ns: float
    max_delay_ns: float
    delays_ns: List[float] = field(default_factory=list)
    path_distances_m: List[float] = field(default_factory=list)
    path_gains_db: List[float] = field(default_factory=list)
    interaction_types: List[str] = field(default_factory=list)

    # Core property accessors matching conceptual API
    @property
    def frequency(self) -> float:
        """Carrier frequency in Hz."""
        return self.frequency_hz

    @property
    def backend(self) -> str:
        """Backend variant used for simulation."""
        return self.backend_variant

    @property
    def number_of_paths(self) -> int:
        """Number of propagation paths found."""
        return self.num_paths

    @property
    def path_delays(self) -> List[float]:
        """Path delays in nanoseconds."""
        return self.delays_ns

    @property
    def path_distances(self) -> List[float]:
        """Path propagation distances in meters."""
        return self.path_distances_m

    @property
    def path_gains(self) -> List[float]:
        """Path gains in dB."""
        return self.path_gains_db

    @property
    def total_path_loss(self) -> float:
        """Total path loss in dB."""
        return self.path_loss_db

    @property
    def received_power(self) -> float:
        """Received power in dBm."""
        return self.rx_power_dbm

    def to_dict(self) -> Dict[str, Any]:
        """Convert simulation result to a JSON-serializable dictionary."""
        return {
            "scene_name": self.scene_name,
            "frequency_hz": float(self.frequency_hz),
            "tx_position": [float(x) for x in self.tx_position],
            "tx_power_dbm": float(self.tx_power_dbm),
            "rx_position": [float(x) for x in self.rx_position],
            "backend": self.backend_variant,
            "backend_variant": self.backend_variant,
            "num_paths": int(self.num_paths),
            "total_path_loss_db": float(self.path_loss_db),
            "received_power_dbm": float(self.rx_power_dbm),
            "min_delay_ns": float(self.min_delay_ns),
            "max_delay_ns": float(self.max_delay_ns),
            "delays_ns": [float(d) for d in self.delays_ns],
            "path_distances_m": [float(d) for d in self.path_distances_m],
            "path_gains_db": [float(g) for g in self.path_gains_db],
            "interaction_types": list(self.interaction_types),
            # Additional canonical aliases matching core query fields
            "frequency": float(self.frequency_hz),
            "number_of_paths": int(self.num_paths),
            "path_delays": [float(d) for d in self.delays_ns],
            "path_distances": [float(d) for d in self.path_distances_m],
            "path_gains": [float(g) for g in self.path_gains_db],
            "total_path_loss": float(self.path_loss_db),
            "received_power": float(self.rx_power_dbm),
        }
