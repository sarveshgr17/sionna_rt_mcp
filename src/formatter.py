"""Terminal output formatting for Sionna RT simulation results."""

from typing import Optional

try:
    from src.result import SimulationResult
except ImportError:
    from result import SimulationResult


def format_result(result: SimulationResult) -> str:
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
