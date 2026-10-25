"""Reusable simulation engine wrapping NVIDIA Sionna RT."""

import math
import os
import sys
from typing import Any, List, Optional, Tuple

import numpy as np

try:
    from src.config import SimulationConfig
    from src.result import SimulationResult
except ImportError:
    from config import SimulationConfig
    from result import SimulationResult

# Speed of light in vacuum (m/s)
SPEED_OF_LIGHT = 299792458.0

# Human-readable mapping for Sionna RT interaction types
INTERACTION_TYPE_MAP = {
    0: "Line of Sight (LOS)",
    1: "Specular Reflection",
    2: "Diffuse Scattering",
    4: "Refraction",
    8: "Diffraction",
}


def ensure_mitsuba_variant() -> str:
    """Initialize a supported Mitsuba variant for Sionna RT.

    Probes for CUDA/OptiX support first; if OptiX is unavailable (e.g. in standard
    WSL or CPU-only setups), falls back gracefully to LLVM CPU.
    """
    import mitsuba as mi

    # Silence stderr during the OptiX probe to suppress missing symbol warnings in WSL
    stderr_fd = sys.stderr.fileno()
    saved_stderr = os.dup(stderr_fd)
    devnull = os.open(os.devnull, os.O_WRONLY)

    try:
        os.dup2(devnull, stderr_fd)
        # If variant is already set, verify it can actually instantiate a scene
        if mi.variant() is not None:
            try:
                mi.load_dict({"type": "scene"})
                return mi.variant()
            except Exception:
                pass

        try:
            mi.set_variant("cuda_ad_mono_polarized")
            mi.load_dict({"type": "scene"})
            return "cuda_ad_mono_polarized"
        except Exception:
            mi.set_variant("llvm_ad_mono_polarized")
            return "llvm_ad_mono_polarized"
    finally:
        os.dup2(saved_stderr, stderr_fd)
        os.close(saved_stderr)
        os.close(devnull)


class SimulationEngine:
    """Simulation engine that executes Sionna RT ray-tracing simulations.

    Responsible strictly for:
    - Initializing the Mitsuba backend variant
    - Loading the 3D scene geometry
    - Configuring carrier frequency and antenna arrays
    - Placing transmitter and receiver nodes
    - Executing path solving via ray tracing
    - Extracting structured physical metrics into a SimulationResult
    """

    def __init__(self, config: Optional[SimulationConfig] = None) -> None:
        """Initialize the engine with an optional configuration."""
        self.config: SimulationConfig = config if config is not None else SimulationConfig()
        self._backend: Optional[str] = None

    @property
    def backend(self) -> str:
        """Get the active Mitsuba backend variant, initializing it if necessary."""
        if self._backend is None:
            self._backend = ensure_mitsuba_variant()
        return self._backend

    def run(self, config: Optional[SimulationConfig] = None) -> SimulationResult:
        """Execute the ray-tracing simulation and return a structured result.

        Args:
            config: Optional config to override the engine's default configuration.

        Returns:
            SimulationResult containing all extracted propagation metrics.
        """
        active_config = config if config is not None else self.config

        # 1. Initialize backend
        backend_variant = self.backend

        # Import Sionna RT modules after backend variant is established
        import mitsuba as mi
        import sionna.rt as rt
        from sionna.rt import PathSolver, PlanarArray, Receiver, Transmitter, load_scene

        # 2. Load scene geometry
        scene_source = getattr(rt.scene, active_config.scene_name, None)
        if scene_source is not None:
            scene = load_scene(scene_source)
        else:
            scene = load_scene(active_config.scene_name)

        # 3. Configure carrier frequency
        scene.frequency = active_config.frequency_hz

        # 4. Configure antenna arrays
        scene.tx_array = PlanarArray(
            num_rows=active_config.num_rows,
            num_cols=active_config.num_cols,
            vertical_spacing=active_config.vertical_spacing,
            horizontal_spacing=active_config.horizontal_spacing,
            pattern=active_config.antenna_pattern,
            polarization=active_config.antenna_polarization,
        )
        scene.rx_array = PlanarArray(
            num_rows=active_config.num_rows,
            num_cols=active_config.num_cols,
            vertical_spacing=active_config.vertical_spacing,
            horizontal_spacing=active_config.horizontal_spacing,
            pattern=active_config.antenna_pattern,
            polarization=active_config.antenna_polarization,
        )

        # 5. Create and place transmitter and receiver
        tx = Transmitter(
            name=active_config.tx_name,
            position=mi.Point3f(*active_config.tx_position),
            power_dbm=active_config.tx_power_dbm,
        )
        rx = Receiver(
            name=active_config.rx_name,
            position=mi.Point3f(*active_config.rx_position),
        )

        scene.add(tx)
        scene.add(rx)
        tx.look_at(rx)

        # 6. Run ray-tracing path solver
        solver = PathSolver()
        paths = solver(scene)

        # 7. Extract propagation metrics
        return self._extract_results(paths, active_config, backend_variant)

    def _extract_results(
        self, paths: Any, config: SimulationConfig, backend: str
    ) -> SimulationResult:
        """Extract and compute propagation metrics from solved paths."""
        # paths.a shape: [2, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths] (real & imag)
        a_raw = np.array(paths.a)
        tau_raw = np.array(paths.tau)  # shape: [num_rx, num_tx, num_paths]

        # Combine real and imaginary parts to compute complex path amplitude: a[0] + 1j * a[1]
        # Squeeze down to the path dimension for single TX/RX antenna setup
        if a_raw.ndim >= 6:
            a_complex = a_raw[0, 0, 0, 0, 0, :] + 1j * a_raw[1, 0, 0, 0, 0, :]
        else:
            a_complex = np.array([0.0])

        # Flatten delays for the single (rx, tx) pair
        delays_s = np.squeeze(tau_raw)
        if delays_s.ndim == 0:
            delays_s = np.array([float(delays_s)])

        delays_ns = [float(d) for d in (delays_s * 1e9).tolist()]
        num_paths = len(delays_ns)

        # Per-path propagation distances in meters
        path_distances_m = [float((d * 1e-9) * SPEED_OF_LIGHT) for d in delays_ns]

        # Per-path linear power gain and dB
        path_gains_linear = np.abs(a_complex) ** 2
        path_gains_db = [
            float(10.0 * math.log10(g)) if g > 0 else -150.0 for g in path_gains_linear
        ]

        # Total path gain & loss
        total_gain_linear = float(np.sum(path_gains_linear))
        if total_gain_linear > 0:
            path_loss_db = float(-10.0 * math.log10(total_gain_linear))
        else:
            path_loss_db = float("inf")

        # Received power in dBm = TX power (dBm) - Path Loss (dB)
        rx_power_dbm = float(config.tx_power_dbm - path_loss_db)

        # Extract interaction types if available
        interaction_types: List[str] = []
        if paths.interactions is not None:
            interactions_raw = np.array(paths.interactions)
            # Shape is [max_depth, num_rx, num_tx, num_paths]
            if interactions_raw.ndim >= 4:
                for p in range(num_paths):
                    path_int_codes = interactions_raw[:, 0, 0, p]
                    non_zero = [c for c in path_int_codes if c != 0]
                    if not non_zero:
                        interaction_types.append(INTERACTION_TYPE_MAP.get(0, "Line of Sight"))
                    else:
                        names = [INTERACTION_TYPE_MAP.get(int(c), f"Type {c}") for c in non_zero]
                        interaction_types.append(", ".join(names))
            else:
                interaction_types = ["Unknown"] * num_paths
        else:
            interaction_types = ["N/A"] * num_paths

        min_delay_ns = float(np.min(delays_ns)) if num_paths > 0 else 0.0
        max_delay_ns = float(np.max(delays_ns)) if num_paths > 0 else 0.0

        return SimulationResult(
            scene_name=config.scene_name,
            frequency_hz=config.frequency_hz,
            tx_position=config.tx_position,
            tx_power_dbm=config.tx_power_dbm,
            rx_position=config.rx_position,
            backend_variant=backend,
            num_paths=num_paths,
            path_loss_db=path_loss_db,
            rx_power_dbm=rx_power_dbm,
            min_delay_ns=min_delay_ns,
            max_delay_ns=max_delay_ns,
            delays_ns=delays_ns,
            path_distances_m=path_distances_m,
            path_gains_db=path_gains_db,
            interaction_types=interaction_types,
        )
