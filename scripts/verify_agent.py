"""Verification script for Sionna RT MCP Agent and Visualization workflow (Step 5)."""

import asyncio
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.agent_client import (
    SionnaMCPAgent,
    format_channel_report,
    format_comparison_report,
    parse_natural_language_task,
)


async def main() -> int:
    print("========================================================")
    print("       Sionna RT MCP Agent & Visualization Verification")
    print("========================================================")

    # 1. Starting MCP server
    print("\n[1] Starting MCP server...")
    agent = SionnaMCPAgent()
    await agent.connect()
    print("[✓] Connected")

    try:
        # 2. Discovering tools
        print("\n[2] Discovering tools...")
        tools = await agent.discover_tools()
        assert len(tools) == 5, f"Expected 5 tools, got {len(tools)}"
        names = [t.name for t in tools]
        assert "check_environment" in names
        assert "list_scenes" in names
        assert "run_simulation" in names
        assert "analyze_simulation" in names
        assert "generate_visualization" in names
        print(f"[✓] 5 tools discovered: {', '.join(sorted(names))}")

        # 3. Checking environment
        print("\n[3] Checking environment...")
        env_data = await agent.call_tool("check_environment", {})
        assert env_data.get("is_usable") is True, "Environment is not usable"
        print(f"[✓] Environment usable (Backend: {env_data.get('backend')})")

        # 4. Discovering scene
        print("\n[4] Discovering scene...")
        scenes_data = await agent.call_tool("list_scenes", {})
        scenes = [s["name"] for s in scenes_data.get("scenes", [])]
        assert "simple_reflector" in scenes, "'simple_reflector' scene not available"
        print("[✓] simple_reflector available")

        # 5. Running channel analysis & visualization (3.5 GHz)
        print("\n[5] Running 3.5 GHz channel analysis & visualization...")
        sim_params = {
            "scene": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, -10.0, 5.0],
            "rx_position": [0.0, 10.0, 5.0],
            "tx_power_dbm": 30.0,
        }
        analysis_data_1 = await agent.call_tool("analyze_simulation", sim_params)
        assert "simulation_id" in analysis_data_1
        assert "simulation" in analysis_data_1
        assert "analysis" in analysis_data_1
        sim_id_1 = analysis_data_1["simulation_id"]
        print(f"[✓] 3.5 GHz analysis completed (ID: {sim_id_1})")

        # Generate plots for 3.5 GHz
        viz_res_1 = await agent.call_tool(
            "generate_visualization",
            {"simulation_id": sim_id_1, "plot_type": "all"},
        )
        plots_1 = viz_res_1.get("generated_plots", [])
        assert len(plots_1) == 3
        for p in plots_1:
            assert os.path.isfile(p["file_path"]), f"Missing plot file: {p['file_path']}"
            assert os.path.getsize(p["file_path"]) > 1000
        print(f"[✓] Generated {len(plots_1)} plots for 3.5 GHz on disk")

        # 6. Interpreting results
        print("\n[6] Interpreting results...")
        analysis = analysis_data_1["analysis"]
        sp = analysis.get("strongest_path")
        assert sp is not None and sp.get("path_index") == 1
        print("[✓] Strongest path identified (LOS Path #1)")

        los_present = analysis.get("los_present")
        assert los_present is True
        print("[✓] LOS status identified (Present)")

        rms_ds = analysis.get("rms_delay_spread_ns")
        assert 3.5 <= rms_ds <= 4.3
        print(f"[✓] RMS delay spread calculated (~{rms_ds:.2f} ns)")

        # Verify formatted report generation
        report = format_channel_report(analysis_data_1, viz_plots=plots_1)
        assert "Wireless Channel Analysis" in report
        assert "Frequency: 3.5 GHz" in report
        assert "Path Loss: ~66.8 dB" in report
        assert "Generated Visualizations:" in report

        # 7. Testing comparison workflow (3.5 GHz vs 28 GHz)
        print("\n[7] Running multi-frequency comparison workflow (3.5 GHz vs 28 GHz)...")
        task_query = (
            "Compare propagation at 3.5 GHz and 28 GHz between TX [0, -10, 5] and RX [0, 10, 5]. "
            "Show the propagation paths and explain the difference."
        )
        parsed = parse_natural_language_task(task_query)
        assert parsed["is_comparison"] is True
        assert len(parsed["frequencies_hz"]) == 2

        comp_report = await agent.run_task(task_query)
        assert "Wireless Channel Comparison Analysis" in comp_report
        assert "Total Path Loss" in comp_report
        assert "+18.0" in comp_report or "+18.1" in comp_report
        assert "Free-Space Path Loss Scaling (Friis Equation)" in comp_report
        assert "comparison.png" in comp_report
        print("[✓] End-to-end comparison task executed successfully")

        # 8. Running NLOS (blockage) demonstration
        print("\n[8] Running NLOS blockage demonstration (TX [0, -10, 5] to RX [0, 10, -5])...")
        nlos_params = {
            "scene": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, -10.0, 5.0],
            "rx_position": [0.0, 10.0, -5.0],
            "tx_power_dbm": 30.0,
        }
        nlos_data = await agent.call_tool("analyze_simulation", nlos_params)
        nlos_analysis = nlos_data.get("analysis", {})
        assert nlos_analysis.get("los_present") is False, "Expected LOS to be blocked (NLOS)"
        nlos_report = format_channel_report(nlos_data)
        assert "LOS: Absent" in nlos_report
        print(f"[✓] NLOS blockage confirmed: los_present={nlos_analysis.get('los_present')}")

        print("\n========================================================")
        print("RESULT: End-to-end agent workflow PASSED ✓")
        print("========================================================")
        return 0
    finally:
        await agent.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
