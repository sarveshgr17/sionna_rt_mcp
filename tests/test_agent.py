"""Tests for the MCP agent client and workflow (Step 5)."""

import asyncio
import pytest

from scripts.agent_client import (
    SionnaMCPAgent,
    format_channel_report,
    parse_natural_language_task,
)


def test_parse_natural_language_task():
    """Verify natural language task parser correctly extracts simulation parameters."""
    task_text = (
        "Analyze a 3.5 GHz wireless link between TX [0, -10, 5] and RX [0, 10, 5]. "
        "Tell me the path loss, strongest path, whether LOS exists, and RMS delay spread."
    )
    params = parse_natural_language_task(task_text)

    assert params["frequency_hz"] == 3.5e9
    assert params["tx_position"] == [0.0, -10.0, 5.0]
    assert params["rx_position"] == [0.0, 10.0, 5.0]
    assert params["tx_power_dbm"] == 30.0
    assert params["scene"] == "simple_reflector"


def test_mcp_client_connection_and_tool_discovery():
    """Verify MCP client connection and dynamic tool discovery."""
    async def _test():
        async with SionnaMCPAgent() as agent:
            tools = await agent.discover_tools()
            tool_names = [t.name for t in tools]
            assert "check_environment" in tool_names
            assert "list_scenes" in tool_names
            assert "run_simulation" in tool_names
            assert "analyze_simulation" in tool_names
            assert "generate_visualization" in tool_names

    asyncio.run(_test())


def test_successful_tool_chaining_and_report_generation():
    """Verify end-to-end tool chaining and human-readable report synthesis."""
    task_text = (
        "Analyze a 3.5 GHz wireless link between TX [0, -10, 5] and RX [0, 10, 5]. "
        "Tell me the path loss, strongest path, whether LOS exists, and RMS delay spread."
    )

    async def _test():
        async with SionnaMCPAgent() as agent:
            report = await agent.run_task(task_text)
            assert isinstance(report, str)
            assert "Wireless Channel Analysis" in report
            assert "Frequency: 3.5 GHz" in report
            assert "TX → RX distance: 20.0 m" in report
            assert "Path Loss: ~66.8 dB" in report
            assert "Received Power: ~-36.8 dBm" in report
            assert "Strongest Path:" in report
            assert "LOS: Present" in report
            assert "RMS Delay Spread: ~3.91 ns" in report
            assert "Path Contributions:" in report

    asyncio.run(_test())


def test_extraction_of_simulation_and_analysis_values():
    """Verify correct extraction of structured simulation and analysis values."""
    sim_params = {
        "scene": "simple_reflector",
        "frequency_hz": 3.5e9,
        "tx_position": [0.0, -10.0, 5.0],
        "rx_position": [0.0, 10.0, 5.0],
        "tx_power_dbm": 30.0,
    }

    async def _test():
        async with SionnaMCPAgent() as agent:
            data = await agent.call_tool("analyze_simulation", sim_params)
            assert "simulation" in data
            assert "analysis" in data

            sim = data["simulation"]
            analysis = data["analysis"]

            # Simulation assertions
            assert sim["num_paths"] == 2
            assert pytest.approx(sim["total_path_loss"], abs=1.0) == 66.80
            assert pytest.approx(sim["received_power"], abs=1.0) == -36.80

            # Analysis assertions
            assert analysis["strongest_path"]["path_index"] == 1
            assert analysis["los_present"] is True
            assert pytest.approx(analysis["rms_delay_spread_ns"], abs=0.5) == 3.91
            assert len(analysis["paths"]) == 2

    asyncio.run(_test())


def test_agent_error_handling_invalid_input():
    """Verify that tool execution errors from invalid parameters are raised cleanly."""
    bad_params = {
        "scene": "simple_reflector",
        "frequency_hz": -50.0,  # Invalid frequency
        "tx_position": [0.0, -10.0, 5.0],
        "rx_position": [0.0, 10.0, 5.0],
    }

    async def _test():
        async with SionnaMCPAgent() as agent:
            with pytest.raises(RuntimeError, match="Frequency must be greater than 0 Hz."):
                await agent.call_tool("analyze_simulation", bad_params)

    asyncio.run(_test())


def test_agent_error_handling_unknown_scene():
    """Verify that agent rejects tasks requesting an unsupported scene."""
    bad_task = {
        "scene": "non_existent_scene",
        "frequency_hz": 3.5e9,
    }

    async def _test():
        async with SionnaMCPAgent() as agent:
            with pytest.raises(ValueError, match="not available"):
                await agent.run_task(bad_task)

    asyncio.run(_test())


def test_parse_comparison_task():
    """Verify parser extracts multiple frequencies and comparison intent."""
    task_text = (
        "Compare propagation at 3.5 GHz and 28 GHz between TX [0, -10, 5] and RX [0, 10, 5]. "
        "Show the propagation paths and explain the difference."
    )
    params = parse_natural_language_task(task_text)

    assert params["is_comparison"] is True
    assert params["frequencies_hz"] == [3.5e9, 28.0e9]
    assert params["tx_position"] == [0.0, -10.0, 5.0]
    assert params["rx_position"] == [0.0, 10.0, 5.0]
    assert params["tx_power_dbm"] == 30.0
    assert params["scene"] == "simple_reflector"
    assert params["visualize"] is True


def test_comparison_workflow_and_friis_scaling():
    """Verify complete comparison workflow producing Friis delta and visualizations."""
    task_text = (
        "Compare propagation at 3.5 GHz and 28 GHz between TX [0, -10, 5] and RX [0, 10, 5]. "
        "Show the propagation paths and explain the difference."
    )

    async def _test():
        async with SionnaMCPAgent() as agent:
            report = await agent.run_task(task_text)
            assert isinstance(report, str)
            assert "Wireless Channel Comparison Analysis" in report
            assert "3.5 GHz vs 28.0 GHz" in report
            assert "Total Path Loss" in report
            assert "Received Power" in report
            assert "+18.0" in report or "+18.1" in report
            assert "Free-Space Path Loss Scaling (Friis Equation)" in report
            assert "Invariance of Multipath Geometry and Delay Spread" in report
            assert "comparison.png" in report
            assert "propagation_paths.png" in report

    asyncio.run(_test())

