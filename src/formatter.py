"""Terminal output formatting for Sionna RT simulation results."""

import math
from typing import Any, Optional

try:
    from src.result import SimulationResult
except ImportError:
    from result import SimulationResult


def sanitize_floats(obj: Any) -> Any:
    """Recursively convert float('inf'), float('-inf'), and NaN to None for JSON compliance."""
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_floats(item) for item in obj]
    return obj


def format_result(result: SimulationResult) -> str:
    """Format the simulation result for clear terminal display."""
    freq_ghz = result.frequency_hz / 1e9

    path_loss_str = (
        f"{result.path_loss_db:.2f} dB"
        if not math.isinf(result.path_loss_db)
        else "Infinity (No Path)"
    )
    rx_power_str = (
        f"{result.rx_power_dbm:.2f} dBm"
        if not math.isinf(result.rx_power_dbm)
        else "-Infinity dBm (No Signal)"
    )

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
        f"  Antennas:              TX: {getattr(result, 'tx_antenna_pattern', result.antenna_pattern)} | RX: {getattr(result, 'rx_antenna_pattern', result.antenna_pattern)} ({getattr(result, 'antenna_polarization', 'V')})",
        f"  Total Paths Found:     {result.num_paths}",
        f"  Total Path Loss:       {path_loss_str}",
        f"  Received Power:        {rx_power_str} (from {result.tx_power_dbm:.1f} dBm TX)",
        f"  Delay Range:           {result.min_delay_ns:.2f} ns to {result.max_delay_ns:.2f} ns",
        "",
        "  Individual Path Breakdown:",
    ]

    for i in range(result.num_paths):
        delay = result.delays_ns[i]
        gain = result.path_gains_db[i]
        dist_m = result.path_distances_m[i] if i < len(result.path_distances_m) else 0.0
        itype = (
            result.interaction_types[i]
            if i < len(result.interaction_types)
            else "Unknown"
        )
        lines.append(
            f"    Path #{i + 1}: Delay = {delay:6.2f} ns ({dist_m:5.2f} m) | "
            f"Path Gain = {gain:7.2f} dB | Type = {itype}"
        )

    lines.append("")
    return "\n".join(lines)


# Backwards-compatible alias for Step 1 naming
format_results = format_result
