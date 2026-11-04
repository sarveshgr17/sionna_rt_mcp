"""Radio Map configuration parameters and validation for Sionna RT.

This module defines RadioMapConfig, a dedicated configuration model for 2D spatial
radio map generation using NVIDIA Sionna RT's RadioMapSolver.

Main components:
- RadioMapConfig: Central dataclass encapsulating scene, transmitter, antenna,
  region geometry, measurement plane, and ray-tracing solver parameters.
- ANTENNA_PATTERN_MAPPING: Mapping between user-friendly antenna categories
  ("isotropic", "dipole", "directional") and verified Sionna RT pattern names
  ("iso", "dipole", "tr38901").
- Comprehensive validation for physical plausibility and API constraints.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

# Mapping user-friendly antenna categories to verified Sionna RT pattern names
# Verified against NVIDIA Sionna RT PlanarArray pattern specifications
ANTENNA_PATTERN_MAPPING: Dict[str, str] = {
    "isotropic": "iso",
    "iso": "iso",
    "dipole": "dipole",
    "hw_dipole": "dipole",
    "directional": "tr38901",
    "tr38901": "tr38901",
}

# Supported antenna polarizations in Sionna RT
VALID_POLARIZATIONS: Set[str] = {"V", "H", "VH", "cross"}

# Supported receiver region selection modes
VALID_REGION_MODES: Set[str] = {"auto", "manual"}


@dataclass
class RadioMapConfig:
    """Configuration parameters for 2D spatial Radio Map generation in Sionna RT."""

    # -------------------------------------------------------------------------
    # 1. Scene Parameters
    # -------------------------------------------------------------------------
    scene_name: str = "simple_reflector"
    frequency_hz: float = 3.5e9  # Carrier frequency in Hertz (default: 3.5 GHz)

    # -------------------------------------------------------------------------
    # 2. Transmitter Parameters
    # -------------------------------------------------------------------------
    tx_name: str = "tx"
    tx_position: Tuple[float, float, float] = (0.0, -10.0, 5.0)  # [x, y, z] in meters
    tx_power_dbm: float = 30.0  # Output RF power in dBm (30 dBm = 1.0 Watt)
    tx_orientation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # (yaw, pitch, roll)

    # -------------------------------------------------------------------------
    # 3. Antenna Parameters
    # -------------------------------------------------------------------------
    antenna_type: str = "isotropic"  # "isotropic", "dipole", or "directional"
    polarization: str = "V"  # "V", "H", "VH", "cross"
    num_rows: int = 1  # Array rows (>= 1)
    num_cols: int = 1  # Array columns (>= 1)
    horizontal_spacing: float = 0.5  # Element spacing in wavelengths (lambda)
    vertical_spacing: float = 0.5  # Element spacing in wavelengths (lambda)

    # -------------------------------------------------------------------------
    # 4. Receiver Measurement Region
    # -------------------------------------------------------------------------
    region_mode: str = "auto"  # "auto" (derived from scene) or "manual"

    # AUTO mode parameters
    auto_margin: float = 5.0  # Buffer margin in meters added to scene bounds
    auto_include_tx: bool = True  # Ensure bounding box encloses transmitter

    # MANUAL mode parameters (required if region_mode == "manual")
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None

    # -------------------------------------------------------------------------
    # 5. Receiver Measurement Plane
    # -------------------------------------------------------------------------
    receiver_height: float = 1.5  # Receiver measurement plane height (z) in meters
    cell_size: Union[float, Tuple[float, float]] = 1.0  # Grid resolution (dx, dy) in meters

    # -------------------------------------------------------------------------
    # 6. Ray-Tracing Solver Parameters (Verified against Sionna RT RadioMapSolver)
    # -------------------------------------------------------------------------
    samples_per_tx: int = 1_000_000  # Monte Carlo SBR ray budget per transmitter
    max_depth: int = 3  # Maximum ray bounce depth
    seed: Optional[int] = None  # Random seed for reproducible simulations
    los: bool = True  # Include Line of Sight
    specular_reflection: bool = True  # Include specular reflections
    diffraction: bool = True  # Include edge diffraction
    scattering: bool = False  # Include diffuse scattering

    # -------------------------------------------------------------------------
    # Optional alias parameters for caller convenience
    # -------------------------------------------------------------------------
    scene: Optional[str] = None
    frequency: Optional[float] = None
    power_dbm: Optional[float] = None

    def __post_init__(self) -> None:
        """Handle aliases, normalize types, and execute comprehensive validation."""
        self._normalize_aliases()
        self._validate_all()

    def _normalize_aliases(self) -> None:
        """Resolve aliases and normalize basic container types."""
        if self.scene is not None:
            self.scene_name = str(self.scene)
        else:
            self.scene = self.scene_name

        if self.frequency is not None:
            self.frequency_hz = float(self.frequency)
        else:
            self.frequency = self.frequency_hz

        if self.power_dbm is not None:
            self.tx_power_dbm = float(self.power_dbm)
        else:
            self.power_dbm = self.tx_power_dbm

        # Normalize transmitter position to 3-tuple of floats if valid length
        if isinstance(self.tx_position, (list, tuple)) and len(self.tx_position) == 3:
            try:
                self.tx_position = (
                    float(self.tx_position[0]),
                    float(self.tx_position[1]),
                    float(self.tx_position[2]),
                )
            except (ValueError, TypeError):
                pass

        # Normalize orientation to 3-tuple of floats if valid length
        if isinstance(self.tx_orientation_deg, (list, tuple)) and len(self.tx_orientation_deg) == 3:
            try:
                self.tx_orientation_deg = (
                    float(self.tx_orientation_deg[0]),
                    float(self.tx_orientation_deg[1]),
                    float(self.tx_orientation_deg[2]),
                )
            except (ValueError, TypeError):
                pass

        # Normalize cell_size
        if isinstance(self.cell_size, (int, float)):
            self.cell_size = float(self.cell_size)
        elif isinstance(self.cell_size, (list, tuple)) and len(self.cell_size) == 2:
            self.cell_size = (float(self.cell_size[0]), float(self.cell_size[1]))

        # Normalize string tokens
        if isinstance(self.region_mode, str):
            self.region_mode = self.region_mode.strip().lower()
        if isinstance(self.antenna_type, str):
            self.antenna_type = self.antenna_type.strip().lower()
        if isinstance(self.polarization, str):
            self.polarization = self.polarization.strip()

    def _validate_all(self) -> None:
        """Execute strict physical and numerical validations."""
        self._validate_scene()
        self._validate_transmitter()
        self._validate_antenna()
        self._validate_region()
        self._validate_measurement_plane()
        self._validate_solver()

    def _validate_scene(self) -> None:
        if not isinstance(self.scene_name, str) or not self.scene_name.strip():
            raise ValueError("scene_name must be a non-empty string.")

        if math.isnan(self.frequency_hz) or math.isinf(self.frequency_hz) or self.frequency_hz <= 0:
            raise ValueError(f"frequency_hz must be a positive finite number, got {self.frequency_hz}.")

    def _validate_transmitter(self) -> None:
        if not isinstance(self.tx_name, str) or not self.tx_name.strip():
            raise ValueError("tx_name must be a non-empty string.")

        if not isinstance(self.tx_position, tuple) or len(self.tx_position) != 3:
            raise ValueError("tx_position must contain exactly 3 numeric coordinates (X, Y, Z).")
        for coord in self.tx_position:
            if math.isnan(coord) or math.isinf(coord):
                raise ValueError("tx_position coordinates must be finite numbers.")

        if math.isnan(self.tx_power_dbm) or math.isinf(self.tx_power_dbm):
            raise ValueError("tx_power_dbm must be a finite numeric value.")

        if not isinstance(self.tx_orientation_deg, tuple) or len(self.tx_orientation_deg) != 3:
            raise ValueError("tx_orientation_deg must contain exactly 3 angles (yaw, pitch, roll).")
        for angle in self.tx_orientation_deg:
            if math.isnan(angle) or math.isinf(angle):
                raise ValueError("tx_orientation_deg angles must be finite numbers.")

    def _validate_antenna(self) -> None:
        if self.antenna_type not in ANTENNA_PATTERN_MAPPING:
            valid_types = sorted(list(ANTENNA_PATTERN_MAPPING.keys()))
            raise ValueError(
                f"Invalid antenna_type '{self.antenna_type}'. "
                f"Supported types are: {valid_types}."
            )

        if self.polarization not in VALID_POLARIZATIONS:
            raise ValueError(
                f"Invalid polarization '{self.polarization}'. "
                f"Supported polarizations are: {sorted(list(VALID_POLARIZATIONS))}."
            )

        if not isinstance(self.num_rows, int) or self.num_rows < 1:
            raise ValueError(f"num_rows must be an integer >= 1, got {self.num_rows}.")

        if not isinstance(self.num_cols, int) or self.num_cols < 1:
            raise ValueError(f"num_cols must be an integer >= 1, got {self.num_cols}.")

        if (
            math.isnan(self.horizontal_spacing)
            or math.isinf(self.horizontal_spacing)
            or self.horizontal_spacing <= 0
        ):
            raise ValueError("horizontal_spacing must be a positive finite number.")

        if (
            math.isnan(self.vertical_spacing)
            or math.isinf(self.vertical_spacing)
            or self.vertical_spacing <= 0
        ):
            raise ValueError("vertical_spacing must be a positive finite number.")

    def _validate_region(self) -> None:
        if self.region_mode not in VALID_REGION_MODES:
            raise ValueError(
                f"Invalid region_mode '{self.region_mode}'. Must be one of {sorted(list(VALID_REGION_MODES))}."
            )

        if self.region_mode == "auto":
            if math.isnan(self.auto_margin) or math.isinf(self.auto_margin) or self.auto_margin < 0:
                raise ValueError("auto_margin must be a non-negative finite number.")
        elif self.region_mode == "manual":
            # In manual mode, all 4 bounding coordinates must be provided and valid
            bounds = {"x_min": self.x_min, "x_max": self.x_max, "y_min": self.y_min, "y_max": self.y_max}
            for name, val in bounds.items():
                if val is None:
                    raise ValueError(f"In manual region mode, '{name}' must be specified.")
                if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                    raise ValueError(f"In manual region mode, '{name}' must be a finite number.")

            assert self.x_min is not None and self.x_max is not None
            assert self.y_min is not None and self.y_max is not None

            if self.x_max <= self.x_min:
                raise ValueError(
                    f"x_max ({self.x_max}) must be strictly greater than x_min ({self.x_min})."
                )
            if self.y_max <= self.y_min:
                raise ValueError(
                    f"y_max ({self.y_max}) must be strictly greater than y_min ({self.y_min})."
                )

    def _validate_measurement_plane(self) -> None:
        if math.isnan(self.receiver_height) or math.isinf(self.receiver_height):
            raise ValueError("receiver_height must be a finite number.")

        if isinstance(self.cell_size, float):
            if math.isnan(self.cell_size) or math.isinf(self.cell_size) or self.cell_size <= 0:
                raise ValueError(f"cell_size must be a positive finite number, got {self.cell_size}.")
        elif isinstance(self.cell_size, tuple):
            dx, dy = self.cell_size
            if math.isnan(dx) or math.isinf(dx) or dx <= 0 or math.isnan(dy) or math.isinf(dy) or dy <= 0:
                raise ValueError(f"cell_size dimensions must be positive finite numbers, got {self.cell_size}.")
        else:
            raise ValueError("cell_size must be a positive float or a tuple of two positive floats (dx, dy).")

        # Additional check for manual mode: cell size should not exceed region dimensions
        if self.region_mode == "manual" and self.x_min is not None and self.x_max is not None:
            span_x = self.x_max - self.x_min
            span_y = self.y_max - self.y_min  # type: ignore
            dx, dy = self.cell_size_tuple
            if dx > span_x:
                raise ValueError(f"cell_size dx ({dx}) exceeds region X span ({span_x}).")
            if dy > span_y:
                raise ValueError(f"cell_size dy ({dy}) exceeds region Y span ({span_y}).")

    def _validate_solver(self) -> None:
        if not isinstance(self.samples_per_tx, int) or self.samples_per_tx < 1:
            raise ValueError(f"samples_per_tx must be an integer >= 1, got {self.samples_per_tx}.")

        if not isinstance(self.max_depth, int) or self.max_depth < 0:
            raise ValueError(f"max_depth must be an integer >= 0, got {self.max_depth}.")

        if self.seed is not None:
            if not isinstance(self.seed, int) or self.seed < 0:
                raise ValueError(f"seed must be None or an integer >= 0, got {self.seed}.")

    # -------------------------------------------------------------------------
    # Properties and Derived Geometry Calculations
    # -------------------------------------------------------------------------
    @property
    def antenna_pattern(self) -> str:
        """Resolved Sionna RT antenna pattern identifier (e.g. 'iso', 'dipole', 'tr38901')."""
        return ANTENNA_PATTERN_MAPPING[self.antenna_type]

    @property
    def tx_orientation_rad(self) -> Tuple[float, float, float]:
        """Transmitter orientation (yaw, pitch, roll) converted to radians."""
        return (
            float(math.radians(self.tx_orientation_deg[0])),
            float(math.radians(self.tx_orientation_deg[1])),
            float(math.radians(self.tx_orientation_deg[2])),
        )

    @property
    def cell_size_tuple(self) -> Tuple[float, float]:
        """Return cell resolution as a 2D tuple (dx, dy) in meters."""
        if isinstance(self.cell_size, tuple):
            return self.cell_size
        return (float(self.cell_size), float(self.cell_size))

    def calculate_region_bounds(
        self,
        scene_bbox: Optional[Tuple[Sequence[float], Sequence[float]]] = None,
    ) -> Tuple[float, float, float, float]:
        """Calculate the 2D bounding rectangle (x_min, x_max, y_min, y_max) in meters.

        Args:
            scene_bbox: Optional 3D bounding box ((min_x, min_y, min_z), (max_x, max_y, max_z))
                        from scene geometry. Required if region_mode is 'auto'.

        Returns:
            Tuple of (x_min, x_max, y_min, y_max) defining the evaluation rectangle.
        """
        if self.region_mode == "manual":
            assert self.x_min is not None and self.x_max is not None
            assert self.y_min is not None and self.y_max is not None
            return (float(self.x_min), float(self.x_max), float(self.y_min), float(self.y_max))

        if scene_bbox is None:
            raise ValueError("scene_bbox must be provided when region_mode is 'auto'.")

        min_pt, max_pt = scene_bbox
        x_min = min(float(min_pt[0]), float(max_pt[0]))
        x_max = max(float(min_pt[0]), float(max_pt[0]))
        y_min = min(float(min_pt[1]), float(max_pt[1]))
        y_max = max(float(min_pt[1]), float(max_pt[1]))

        # Include transmitter location if configured
        if self.auto_include_tx and self.tx_position is not None:
            tx_x, tx_y, _ = self.tx_position
            x_min = min(x_min, tx_x)
            x_max = max(x_max, tx_x)
            y_min = min(y_min, tx_y)
            y_max = max(y_max, tx_y)

        # Apply configurable margin
        margin = float(self.auto_margin)
        x_min -= margin
        x_max += margin
        y_min -= margin
        y_max += margin

        # Guard against zero-area / degenerate bounds
        if x_max <= x_min:
            x_min -= 10.0
            x_max += 10.0
        if y_max <= y_min:
            y_min -= 10.0
            y_max += 10.0

        return (x_min, x_max, y_min, y_max)

    def calculate_center_and_size(
        self,
        scene_bbox: Optional[Tuple[Sequence[float], Sequence[float]]] = None,
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float]]:
        """Compute the center [x, y, z] and size [span_x, span_y] for RadioMapSolver.

        Args:
            scene_bbox: Optional 3D bounding box for 'auto' region calculation.

        Returns:
            center: 3-tuple (center_x, center_y, receiver_height) in meters.
            size: 2-tuple (span_x, span_y) in meters.
        """
        x_min, x_max, y_min, y_max = self.calculate_region_bounds(scene_bbox)
        center = (
            float((x_min + x_max) / 2.0),
            float((y_min + y_max) / 2.0),
            float(self.receiver_height),
        )
        size = (
            float(x_max - x_min),
            float(y_max - y_min),
        )
        return center, size

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to a JSON-serializable dictionary."""
        dx, dy = self.cell_size_tuple
        return {
            "scene_name": self.scene_name,
            "frequency_hz": self.frequency_hz,
            "tx_name": self.tx_name,
            "tx_position": list(self.tx_position),
            "tx_power_dbm": self.tx_power_dbm,
            "tx_orientation_deg": list(self.tx_orientation_deg),
            "tx_orientation_rad": list(self.tx_orientation_rad),
            "antenna_type": self.antenna_type,
            "antenna_pattern": self.antenna_pattern,
            "polarization": self.polarization,
            "num_rows": self.num_rows,
            "num_cols": self.num_cols,
            "horizontal_spacing": self.horizontal_spacing,
            "vertical_spacing": self.vertical_spacing,
            "region_mode": self.region_mode,
            "auto_margin": self.auto_margin,
            "auto_include_tx": self.auto_include_tx,
            "x_min": self.x_min,
            "x_max": self.x_max,
            "y_min": self.y_min,
            "y_max": self.y_max,
            "receiver_height": self.receiver_height,
            "cell_size": [dx, dy] if isinstance(self.cell_size, tuple) else self.cell_size,
            "samples_per_tx": self.samples_per_tx,
            "max_depth": self.max_depth,
            "seed": self.seed,
            "los": self.los,
            "specular_reflection": self.specular_reflection,
            "diffraction": self.diffraction,
            "scattering": self.scattering,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RadioMapConfig":
        """Instantiate RadioMapConfig from a dictionary, filtering unknown keys."""
        valid_keys = {
            "scene_name",
            "frequency_hz",
            "tx_name",
            "tx_position",
            "tx_power_dbm",
            "tx_orientation_deg",
            "antenna_type",
            "polarization",
            "num_rows",
            "num_cols",
            "horizontal_spacing",
            "vertical_spacing",
            "region_mode",
            "auto_margin",
            "auto_include_tx",
            "x_min",
            "x_max",
            "y_min",
            "y_max",
            "receiver_height",
            "cell_size",
            "samples_per_tx",
            "max_depth",
            "seed",
            "los",
            "specular_reflection",
            "diffraction",
            "scattering",
            "scene",
            "frequency",
            "power_dbm",
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
