"""Minimal NVIDIA Sionna RT ray-tracing simulation.

Executes a minimal Sionna RT simulation:
1. Verifies / sets backend variant (CUDA OptiX or LLVM CPU fallback).
2. Loads a simple Sionna RT scene.
3. Creates one transmitter.
4. Creates one receiver.
5. Configures a carrier frequency.
6. Runs a basic ray-tracing simulation using PathSolver.
7. Extracts propagation information (paths, delays, path loss, received power).
8. Reports a concise result to the terminal.
"""

import math
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

# Ensure config can be imported both directly and as package
try:
    from src.config import SimulationConfig
except ImportError:
    from config import SimulationConfig


def ensure_mitsuba_variant() -> str:
    """Initialize a supported Mitsuba variant for Sionna RT.

    Probes for CUDA/OptiX support first; if OptiX is unavailable (e.g. in standard
    WSL or CPU-only setups), falls back gracefully to LLVM CPU.
    """
    import mitsuba as mi

    if mi.variant() is not None:
        return mi.variant()

    # Silence stderr during the OptiX probe to suppress missing symbol warnings in WSL
    stderr_fd = sys.stderr.fileno()
    saved_stderr = os.dup(stderr_fd)
    devnull = os.open(os.devnull, os.O_WRONLY)

    try:
        os.dup2(devnull, stderr_fd)
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
    path_gains_db: List[float] = field(default_factory=list)
    interaction_types: List[str] = field(default_factory=list)


def run_simulation(config: Optional[SimulationConfig] = None) -> SimulationResult:
    """Run a minimal Sionna RT simulation with the provided configuration."""
    if config is None:
        config = SimulationConfig()

    # 1. Initialize Mitsuba backend
    variant = ensure_mitsuba_variant()

    # Import Sionna RT modules after variant selection
    import mitsuba as mi
    import sionna.rt as rt
    from sionna.rt import PathSolver, PlanarArray, Receiver, Transmitter, load_scene

    # 2. Load scene
    scene_source = getattr(rt.scene, config.scene_name, None)
    if scene_source is not None:
        scene = load_scene(scene_source)
    else:
        # Fall back to file path if not a built-in scene attribute
        scene = load_scene(config.scene_name)

    # 3. Configure carrier frequency
    scene.frequency = config.frequency_hz

    # 4. Configure antenna arrays for TX and RX
    scene.tx_array = PlanarArray(
        num_rows=config.num_rows,
        num_cols=config.num_cols,
        vertical_spacing=config.vertical_spacing,
        horizontal_spacing=config.horizontal_spacing,
        pattern=config.antenna_pattern,
        polarization=config.antenna_polarization,
    )
    scene.rx_array = PlanarArray(
        num_rows=config.num_rows,
        num_cols=config.num_cols,
        vertical_spacing=config.vertical_spacing,
        horizontal_spacing=config.horizontal_spacing,
        pattern=config.antenna_pattern,
        polarization=config.antenna_polarization,
    )

    # 5. Create transmitter and receiver
    tx = Transmitter(
        name=config.tx_name,
        position=mi.Point3f(*config.tx_position),
        power_dbm=config.tx_power_dbm,
    )
    rx = Receiver(
        name=config.rx_name,
        position=mi.Point3f(*config.rx_position),
    )

    scene.add(tx)
    scene.add(rx)
    tx.look_at(rx)

    # 6. Run ray-tracing simulation
    solver = PathSolver()
    paths = solver(scene)

    # 7. Extract propagation information
    # paths.a has shape [2, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths] (real & imag)
    a_raw = np.array(paths.a)
    tau_raw = np.array(paths.tau)  # shape [num_rx, num_tx, num_paths]

    # Combine real and imaginary parts to compute complex path amplitude: a[0] + 1j * a[1]
    # Squeeze down to the path dimension for single TX/RX antenna setup
    if a_raw.ndim >= 6:
        # a_raw[0] is real part, a_raw[1] is imaginary part
        a_complex = a_raw[0, 0, 0, 0, 0, :] + 1j * a_raw[1, 0, 0, 0, 0, :]
    else:
        a_complex = np.array([0.0])

    # Flatten delays for the single (rx, tx) pair
    delays_s = np.squeeze(tau_raw)
    if delays_s.ndim == 0:
        delays_s = np.array([float(delays_s)])

    delays_ns = (delays_s * 1e9).tolist()
    num_paths = len(delays_ns)

    # Per-path linear power gain and in dB
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
    rx_power_dbm = config.tx_power_dbm - path_loss_db

    # Extract interaction types if available
    interaction_types = []
    if paths.interactions is not None:
        interactions_raw = np.array(paths.interactions)
        # Shape is [max_depth, num_rx, num_tx, num_paths]
        # For each path, examine the interaction types along the path
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
        backend_variant=variant,
        num_paths=num_paths,
        path_loss_db=path_loss_db,
        rx_power_dbm=rx_power_dbm,
        min_delay_ns=min_delay_ns,
        max_delay_ns=max_delay_ns,
        delays_ns=delays_ns,
        path_gains_db=path_gains_db,
        interaction_types=interaction_types,
    )


def format_results(result: SimulationResult) -> str:
    """Format the simulation result for clear terminal display."""
    freq_ghz = result.frequency_hz / 1e9

    lines = [
        "",
        "Scene loaded: ✓",
        "Transmitter: ✓",
        "Receiver: ✓",
        f"Frequency: {freq_ghz:.1f} GHz ✓",
        "Ray tracing: ✓",
        "",
        "Propagation Results:",
        f"  Backend:               {result.backend_variant}",
        f"  Total Paths Found:     {result.num_paths}",
        f"  Total Path Loss:       {result.path_loss_db:.2f} dB",
        f"  Received Power:        {result.rx_power_dbm:.2f} dBm (from {result.tx_power_dbm:.1f} dBm TX)",
        f"  Delay Range:           {result.min_delay_ns:.2f} ns to {result.max_delay_ns:.2f} ns",
        "",
        "  Individual Path Breakdown:",
    ]

    for i in range(result.num_paths):
        delay = result.delays_ns[i]
        gain = result.path_gains_db[i]
        itype = (
            result.interaction_types[i]
            if i < len(result.interaction_types)
            else "Unknown"
        )
        dist_m = (delay * 1e-9) * SPEED_OF_LIGHT
        lines.append(
            f"    Path #{i + 1}: Delay = {delay:6.2f} ns ({dist_m:5.2f} m) | "
            f"Path Gain = {gain:7.2f} dB | Type = {itype}"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    """Main execution function."""
    config = SimulationConfig()
    result = run_simulation(config)
    print(format_results(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
