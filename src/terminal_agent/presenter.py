"""Terminal presentation and formatting for Sionna RT CLI.

Formats simulation summaries, multi-path metrics, radio-map coverage heatmaps,
and experiment comparison deltas into clean, human-readable terminal output.
"""

from typing import Any, Dict, List, Optional


def format_welcome_banner(server_url: str, backend: str, tool_count: int) -> str:
    """Renders the startup terminal banner."""
    lines = [
        "=" * 72,
        "                    SIONNA RT RADIO PLANNER CLI",
        "=" * 72,
        f"  Connected:    {server_url}",
        f"  Backend:      {backend}",
        f"  Tools:        {tool_count} tools discovered",
        "-" * 72,
        "  Type natural-language instructions (e.g. 'Generate a radio map at 3.5 GHz')",
        "  Available commands: /help, /tools, /context, /reset, /exit",
        "=" * 72,
    ]
    return "\n".join(lines)


def format_understanding_acknowledgment(operation: str, details: Dict[str, Any]) -> str:
    """Formats an acknowledgment showing what parameters were parsed from the user prompt."""
    lines = [
        "Assistant: I understood your request.\n",
        f"  Operation:      {operation}",
    ]
    for key, val in details.items():
        if key == "frequency_hz":
            ghz = val / 1e9
            lines.append(f"  Frequency:      {ghz:.3g} GHz ({val:.0f} Hz)")
        elif key == "tx_position":
            lines.append(f"  Transmitter:    [{val[0]}, {val[1]}, {val[2]}] m")
        elif key == "rx_position":
            lines.append(f"  Receiver:       [{val[0]}, {val[1]}, {val[2]}] m")
        elif key == "antenna_type":
            lines.append(f"  Antenna:        {val}")
        elif key == "tx_antenna_type" and val:
            lines.append(f"  TX Antenna:     {val}")
        elif key == "rx_antenna_type" and val:
            lines.append(f"  RX Antenna:     {val}")
        elif key == "polarization":
            lines.append(f"  Polarization:   {val}")
        elif key == "cell_size":
            lines.append(f"  Cell size:      {val} metres")
        elif key == "samples_per_tx":
            lines.append(f"  Samples per TX: {val:,} rays")
        elif key == "tx_power_dbm":
            lines.append(f"  TX Power:       {val} dBm")
        elif key == "receiver_height":
            lines.append(f"  RX Height:      {val} m")
        elif key == "scene_name" or key == "scene":
            lines.append(f"  Scene:          {val}")
        elif key == "max_depth":
            lines.append(f"  Max Depth:      {val} bounces")

    lines.append("\n  Starting simulation via MCP server...")
    return "\n".join(lines)


def format_radio_map_result(res: Dict[str, Any]) -> str:
    """Formats the numerical output and artifact paths of `generate_radio_map`."""
    cov = res.get("coverage_percentage", 0.0)
    mean_rss = res.get("mean_rss_dbm")
    min_rss = res.get("min_rss_dbm")
    max_rss = res.get("max_rss_dbm")
    grid = res.get("grid_dimensions", [])
    cells = res.get("total_cells", 0)

    lines = [
        "MCP: Simulation completed successfully.\n",
        f"  Experiment ID:       {res.get('experiment_id', 'unknown')}",
        f"  Scene:               {res.get('scene_name', 'unknown')}",
        f"  Coverage:            {cov:.2f}%",
        f"  Mean RSS:            {f'{mean_rss:.2f} dBm' if mean_rss is not None else 'N/A'}",
        f"  Minimum RSS:         {f'{min_rss:.2f} dBm' if min_rss is not None else 'N/A'}",
        f"  Maximum RSS:         {f'{max_rss:.2f} dBm' if max_rss is not None else 'N/A'}",
        f"  Grid Dimensions:     {grid[0]} x {grid[1]} ({cells:,} cells)" if len(grid) == 2 else "",
        f"  Measurement Height:  {res.get('measurement_height', 1.5)} m",
    ]

    # Heatmaps and artifact paths
    artifacts = res.get("artifact_paths", {})
    lines.append("\n  Generated Files:")
    if "rss_heatmap" in artifacts:
        lines.append(f"    RSS Heatmap:       {artifacts['rss_heatmap']}")
    if "path_gain_heatmap" in artifacts:
        lines.append(f"    Path Gain Heatmap: {artifacts['path_gain_heatmap']}")
    if "metadata_json" in artifacts:
        lines.append(f"    Metadata JSON:     {artifacts['metadata_json']}")
    if "radio_map_data_npz" in artifacts:
        lines.append(f"    Raw NPZ Data:      {artifacts['radio_map_data_npz']}")

    return "\n".join(l for l in lines if l)


def format_simulation_result(res: Dict[str, Any]) -> str:
    """Formats point-to-point propagation simulation metrics."""
    scene = res.get("scene_name") or res.get("scene", "unknown")
    loss = res.get("total_path_loss_db") if "total_path_loss_db" in res else res.get("total_path_loss", 0.0)
    power = res.get("received_power_dbm") if "received_power_dbm" in res else res.get("received_power", 0.0)
    freq = res.get("frequency_hz") or res.get("frequency")
    freq_str = f" ({freq/1e9:.2f} GHz)" if isinstance(freq, (int, float)) else ""

    lines = [
        "MCP: Point-to-point simulation completed.\n",
        f"  Scene:           {scene}",
        f"  Frequency:       {freq:,.0f} Hz{freq_str}" if isinstance(freq, (int, float)) else "",
        f"  Paths Resolved:  {res.get('num_paths', 0)}",
        f"  Total Path Loss: {loss:.2f} dB",
        f"  Received Power:  {power:.2f} dBm",
    ]

    min_delay = res.get("min_delay_ns")
    max_delay = res.get("max_delay_ns")
    if min_delay is not None and max_delay is not None:
        lines.append(f"  Delay Range:     {min_delay:.2f} ns to {max_delay:.2f} ns")

    # Antenna details if present
    tx_ant = res.get("tx_antenna_pattern") or res.get("antenna_pattern")
    rx_ant = res.get("rx_antenna_pattern") or res.get("antenna_pattern")
    pol = res.get("antenna_polarization")
    if tx_ant or rx_ant:
        lines.append(f"  Antennas:        TX: {tx_ant} | RX: {rx_ant} ({pol or 'V'})")

    delays = res.get("path_delays", [])
    distances = res.get("path_distances", [])
    gains = res.get("path_gains", [])
    interactions = res.get("interaction_types", [])

    if delays:
        lines.append("\n  Multipath Components:")
        lines.append("  #   Delay (ns)   Distance (m)   Gain (dB)   Interaction")
        lines.append("  " + "-" * 56)
        for i in range(len(delays)):
            d_ns = delays[i] if i < len(delays) else 0.0
            dist_m = distances[i] if i < len(distances) else 0.0
            g_db = gains[i] if i < len(gains) else 0.0
            inter = interactions[i] if i < len(interactions) else "Unknown"
            lines.append(f"  {i+1:<3} {d_ns:>10.2f}   {dist_m:>12.2f}   {g_db:>9.2f}   {inter}")

    return "\n".join(l for l in lines if l)


def format_comparison_result(res: Dict[str, Any]) -> str:
    """Formats experiment comparison metrics and diverging difference heatmaps."""
    lines = [
        "MCP: Experiment comparison completed.\n",
        f"  Baseline (A):    {res.get('experiment_a_id')}",
        f"  Modified (B):    {res.get('experiment_b_id')}",
        f"  Convention:      {res.get('difference_convention', 'Difference = B - A')}",
        f"  Scene:           {res.get('scene_name')}",
    ]

    rss_diff = res.get("rss_difference_metrics", {})
    gain_diff = res.get("path_gain_difference_metrics", {})

    mean_d_rss = rss_diff.get("mean_difference") if rss_diff else res.get("mean_delta_rss_dbm")
    min_d_rss = rss_diff.get("min_difference") if rss_diff else res.get("min_delta_rss_dbm")
    max_d_rss = rss_diff.get("max_difference") if rss_diff else res.get("max_delta_rss_dbm")
    mean_d_gain = gain_diff.get("mean_difference") if gain_diff else res.get("mean_delta_path_gain_db")

    lines.append("\n  Delta Metrics (B - A):")
    if mean_d_rss is not None:
        lines.append(f"    Mean Delta RSS:       {mean_d_rss:+.2f} dBm")
    if min_d_rss is not None:
        lines.append(f"    Min Delta RSS:        {min_d_rss:+.2f} dBm")
    if max_d_rss is not None:
        lines.append(f"    Max Delta RSS:        {max_d_rss:+.2f} dBm")
    if mean_d_gain is not None:
        lines.append(f"    Mean Delta Path Gain: {mean_d_gain:+.2f} dB")

    b_stronger = rss_diff.get("b_stronger_cells")
    b_weaker = rss_diff.get("b_weaker_cells")
    if b_stronger is not None and b_weaker is not None:
        lines.append(f"    Cells B > A (stronger): {b_stronger:,}")
        lines.append(f"    Cells B < A (weaker):   {b_weaker:,}")

    artifacts = res.get("artifacts") or res.get("heatmaps") or res.get("artifact_paths", {})
    if artifacts:
        lines.append("\n  Generated Difference Artifacts:")
        for k, path in artifacts.items():
            lines.append(f"    {k}: {path}")

    return "\n".join(lines)


def format_experiment_details(res: Dict[str, Any]) -> str:
    """Formats detailed experiment metadata."""
    cov = res.get("coverage_metrics", {}).get("coverage_percentage", 0.0)
    lines = [
        f"Experiment Details: {res.get('experiment_id')}\n",
        f"  Timestamp:       {res.get('simulation_timestamp')}",
        f"  Scene:           {res.get('scene_name')}",
        f"  Frequency:       {res.get('frequency_hz', 0) / 1e9:.3g} GHz",
        f"  Transmitter:     {res.get('tx_position')}",
        f"  TX Power:        {res.get('tx_power_dbm')} dBm",
        f"  Grid Cell Size:  {res.get('cell_size')} m",
        f"  Coverage:        {cov:.2f}%",
    ]

    artifacts = res.get("artifact_paths", {})
    if artifacts:
        lines.append("\n  Saved Artifacts:")
        for k, p in artifacts.items():
            lines.append(f"    {k}: {p}")

    return "\n".join(lines)


def format_experiments_list(res: Dict[str, Any]) -> str:
    """Formats the list of saved experiments."""
    exps = res.get("experiments", [])
    if not exps:
        return "No saved experiments found in storage."

    lines = [
        f"Stored Experiments ({len(exps)} total):\n",
        f"{'Experiment ID':<36} {'Scene':<18} {'Freq (GHz)':<12} {'Coverage':<10} {'Created':<20}",
        "-" * 100,
    ]
    for e in exps:
        eid = e.get("experiment_id", "")
        sc = e.get("scene_name", "")
        freq = f"{e.get('frequency_hz', 0) / 1e9:.2f}"
        cov = f"{e.get('coverage_percentage', 0.0):.1f}%"
        ts = e.get("simulation_timestamp", "")[:19]
        lines.append(f"{eid:<36} {sc:<18} {freq:<12} {cov:<10} {ts:<20}")

    return "\n".join(lines)


def format_scenes_list(res: Dict[str, Any]) -> str:
    """Formats available scenes."""
    scenes = res.get("scenes", [])
    default_sc = res.get("default_scene", "simple_reflector")
    lines = [
        f"Available 3D Scenes ({len(scenes)} total, default: '{default_sc}'):\n",
    ]
    for s in scenes:
        def_tag = " (DEFAULT)" if s.get("is_default") or s.get("name") == default_sc else ""
        lines.append(f"  • {s.get('name')}{def_tag}")
        lines.append(f"    {s.get('description', '')}\n")
    return "\n".join(lines)


def format_environment_status(res: Dict[str, Any]) -> str:
    """Formats environment check status."""
    status_str = "READY (Usable)" if res.get("is_usable") else "NOT USABLE"
    lines = [
        "Sionna RT Environment Status:\n",
        f"  Status:           {status_str}",
        f"  Computational Backend: {res.get('backend')}",
        f"  Python Version:   {res.get('python_version')}",
        f"  Sionna Version:   {res.get('sionna_version')}",
        f"  Mitsuba Version:  {res.get('mitsuba_version')}",
    ]
    return "\n".join(lines)


def format_help() -> str:
    """Renders the CLI help text."""
    return """
SIONNA RT RADIO PLANNER — COMMAND REFERENCE
========================================================================
You can type natural English instructions or use local CLI commands:

Natural Language Examples:
  • "Check whether Sionna is working"
  • "Show available scenes"
  • "Generate a radio map for simple_reflector at 3.5 GHz. Place transmitter at [0,-10,5]. Use 5 metre cell size and 10000 rays."
  • "Now generate the same map at 5 GHz." (uses context from previous run)
  • "Run a point-to-point simulation from [0, -10, 5] to [0, 10, 5] at 3.5 GHz."
  • "Show my previous experiments."
  • "Give me details of experiment ID experiment_..."
  • "Compare experiment_A with experiment_B."

Local CLI Controls:
  /help      Show this command guide
  /tools     List all 7 MCP tools discovered from the server
  /context   Display active session parameters and last experiment
  /reset     Clear conversation session context and start fresh
  /exit      Exit the terminal interface (or type 'exit' / 'quit')
========================================================================
""".strip()
