"""Unit and integration tests for the Sionna RT MCP server."""

import asyncio
import json
import sys
from typing import Any, Dict
import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
try:
    from mcp.server.mcpserver.exceptions import ToolError
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp.exceptions import ToolError

from src.mcp_server import create_mcp_server, mcp


def _extract_data(call_result: Any) -> Dict[str, Any]:
    """Helper to extract structured tool result payload from MCP CallToolResult."""
    if call_result.structured_content and "result" in call_result.structured_content:
        return call_result.structured_content["result"]
    if call_result.content and hasattr(call_result.content[0], "text"):
        return json.loads(call_result.content[0].text)
    return call_result.structured_content or {}


def test_mcp_server_initialization_and_tool_registration():
    """Verify that MCP server registers exactly the 4 intended tools."""
    server = create_mcp_server()

    async def _check_tools():
        tools = await server.list_tools()
        tool_names = sorted([t.name for t in tools])
        assert tool_names == [
            "analyze_simulation",
            "check_environment",
            "generate_visualization",
            "list_scenes",
            "run_simulation",
        ]
        assert len(tools) == 5

        # Verify tool descriptions are non-empty and informative for an AI agent
        for tool in tools:
            assert tool.description is not None
            assert len(tool.description.strip()) > 20

    asyncio.run(_check_tools())


def test_check_environment_tool():
    """Verify check_environment returns expected structured fields without leaks."""
    server = create_mcp_server()

    async def _run():
        result = await server.call_tool("check_environment", {})
        structured = _extract_data(result)
        assert isinstance(structured, dict)
        assert "python_version" in structured
        assert "sionna_version" in structured
        assert "mitsuba_version" in structured
        assert "backend" in structured
        assert "is_usable" in structured
        assert structured["is_usable"] is True
        assert structured["backend"] in ("llvm_ad_mono_polarized", "cuda_ad_mono_polarized")

    asyncio.run(_run())


def test_list_scenes_tool():
    """Verify list_scenes returns structured scenes catalog including simple_reflector."""
    server = create_mcp_server()

    async def _run():
        result = await server.call_tool("list_scenes", {})
        structured = _extract_data(result)
        assert isinstance(structured, dict)
        assert "scenes" in structured
        assert "default_scene" in structured
        assert structured["default_scene"] == "simple_reflector"
        scene_names = [s["name"] for s in structured["scenes"]]
        assert "simple_reflector" in scene_names

    asyncio.run(_run())


def test_run_simulation_real_execution():
    """Verify run_simulation executes a real Sionna simulation and returns valid metrics."""
    server = create_mcp_server()

    async def _run():
        params = {
            "scene": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, -10.0, 5.0],
            "rx_position": [0.0, 10.0, 5.0],
            "tx_power_dbm": 30.0,
        }
        result = await server.call_tool("run_simulation", params)
        data = _extract_data(result)
        assert isinstance(data, dict)

        # Core fields verification
        assert data["scene_name"] == "simple_reflector"
        assert data["frequency_hz"] == 3.5e9
        assert data["tx_position"] == [0.0, -10.0, 5.0]
        assert data["rx_position"] == [0.0, 10.0, 5.0]
        assert data["backend"] in ("llvm_ad_mono_polarized", "cuda_ad_mono_polarized")

        # Physical propagation values (~2 paths, ~66.8 dB path loss, ~-36.8 dBm received power)
        assert data["num_paths"] == 2
        assert pytest.approx(data["total_path_loss"], abs=1.0) == 66.80
        assert pytest.approx(data["received_power"], abs=1.0) == -36.80
        assert len(data["path_delays"]) == 2
        assert len(data["path_distances"]) == 2
        assert len(data["path_gains"]) == 2
        assert len(data["interaction_types"]) == 2
        assert pytest.approx(data["path_delays"][0], abs=1.0) == 66.71
        assert pytest.approx(data["path_delays"][1], abs=1.0) == 74.59

    asyncio.run(_run())


def test_analyze_simulation_real_execution():
    """Verify analyze_simulation executes simulation and returns derived wireless channel analysis."""
    server = create_mcp_server()

    async def _run():
        params = {
            "scene": "simple_reflector",
            "frequency_hz": 3.5e9,
            "tx_position": [0.0, -10.0, 5.0],
            "rx_position": [0.0, 10.0, 5.0],
            "tx_power_dbm": 30.0,
        }
        result = await server.call_tool("analyze_simulation", params)
        data = _extract_data(result)
        assert isinstance(data, dict)

        # Check top-level separation
        assert "simulation" in data
        assert "analysis" in data

        sim = data["simulation"]
        analysis = data["analysis"]

        # Verify simulation payload
        assert sim["num_paths"] == 2
        assert pytest.approx(sim["total_path_loss"], abs=1.0) == 66.80

        # Verify analysis payload
        assert "strongest_path" in analysis
        sp = analysis["strongest_path"]
        assert sp["path_index"] == 1
        assert "Line of Sight" in sp["interaction_type"]
        assert pytest.approx(sp["gain_db"], abs=1.0) == -69.35
        assert pytest.approx(sp["delay_ns"], abs=1.0) == 66.71

        # LOS verification
        assert analysis["los_present"] is True
        assert analysis["los_path_index"] == 1

        # RMS delay spread verification (~3.9 ns for simple_reflector)
        assert pytest.approx(analysis["rms_delay_spread_ns"], abs=0.5) == 3.92
        assert analysis["min_delay_ns"] < analysis["max_delay_ns"]

        # Path contributions verification
        paths = analysis["paths"]
        assert len(paths) == 2
        total_pct = sum(p["power_contribution_percent"] for p in paths)
        assert pytest.approx(total_pct, abs=0.5) == 100.0
        assert paths[0]["power_contribution_percent"] > paths[1]["power_contribution_percent"]

    asyncio.run(_run())


def test_run_simulation_invalid_inputs():
    """Verify that invalid simulation inputs are cleanly rejected with descriptive ToolError messages."""
    server = create_mcp_server()

    async def _run():
        # 1. Negative frequency
        with pytest.raises(ToolError, match="Frequency must be greater than 0 Hz."):
            await server.call_tool("run_simulation", {"frequency_hz": -1.0})

        # 2. Zero frequency
        with pytest.raises(ToolError, match="Frequency must be greater than 0 Hz."):
            await server.call_tool("run_simulation", {"frequency_hz": 0.0})

        # 3. Non-numeric frequency
        with pytest.raises(ToolError, match="(Frequency must be greater than 0 Hz|Input should be a valid number)"):
            await server.call_tool("run_simulation", {"frequency_hz": "invalid_freq"})

        # 4. Invalid position dimension (only 2 coordinates)
        with pytest.raises(ToolError, match="Position must contain exactly 3 numeric coordinates"):
            await server.call_tool("run_simulation", {"tx_position": [0.0, -10.0]})

        # 5. Invalid position dimension (4 coordinates)
        with pytest.raises(ToolError, match="Position must contain exactly 3 numeric coordinates"):
            await server.call_tool("run_simulation", {"rx_position": [0.0, 10.0, 5.0, 1.0]})

        # 6. Non-numeric coordinate values
        with pytest.raises(ToolError, match="(Position must contain exactly 3 numeric coordinates|Input should be a valid number)"):
            await server.call_tool("run_simulation", {"tx_position": ["a", "b", "c"]})

        # 7. Invalid scene name
        with pytest.raises(ToolError, match="Scene 'unknown_scene' is not available"):
            await server.call_tool("run_simulation", {"scene": "unknown_scene"})

        # 8. Empty scene name
        with pytest.raises(ToolError, match="Scene name must be a non-empty string."):
            await server.call_tool("run_simulation", {"scene": "  "})

        # 9. Invalid transmit power
        with pytest.raises(ToolError, match="(Transmitter power must be a numeric value|Input should be a valid number)"):
            await server.call_tool("run_simulation", {"tx_power_dbm": "not_a_number"})

    asyncio.run(_run())


def test_generate_visualization_invalid_inputs():
    """Verify that generate_visualization robustly handles unknown IDs and invalid plot types."""
    server = create_mcp_server()

    async def _run():
        # 1. Non-existent simulation ID
        with pytest.raises(ToolError, match="not found in storage"):
            await server.call_tool("generate_visualization", {"simulation_id": "sim_non_existent_123"})

        # 2. Empty simulation ID
        with pytest.raises(ToolError, match="not found in storage"):
            await server.call_tool("generate_visualization", {"simulation_id": ""})

        # 3. Missing comparison_simulation_id when plot_type='comparison'
        # First create a valid simulation
        valid_res = await server.call_tool("run_simulation", {})
        data = _extract_data(valid_res)
        sim_id = data["simulation_id"]

        with pytest.raises(ToolError, match="comparison_simulation_id is required"):
            await server.call_tool(
                "generate_visualization",
                {"simulation_id": sim_id, "plot_type": "comparison"},
            )

        # 4. Non-existent comparison_simulation_id
        with pytest.raises(ToolError, match="Comparison simulation ID '.*' not found in storage"):
            await server.call_tool(
                "generate_visualization",
                {
                    "simulation_id": sim_id,
                    "plot_type": "comparison",
                    "comparison_simulation_id": "sim_non_existent_comp",
                },
            )

        # 5. Unsupported plot type
        with pytest.raises(ToolError, match="Unsupported plot type 'unsupported_plot'"):
            await server.call_tool(
                "generate_visualization",
                {"simulation_id": sim_id, "plot_type": "unsupported_plot"},
            )

    asyncio.run(_run())


def test_mcp_stdio_client_integration():
    """Verify end-to-end communication over stdio transport using an MCP ClientSession."""
    async def _run_stdio():
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["src/mcp_server.py"],
        )
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await session.initialize()
                assert init_result is not None

                # 1. Discover tools
                tool_list = await session.list_tools()
                names = [t.name for t in tool_list.tools]
                assert "check_environment" in names
                assert "list_scenes" in names
                assert "run_simulation" in names
                assert "analyze_simulation" in names
                assert "generate_visualization" in names

                # 2. Call check_environment
                env_res = await session.call_tool("check_environment", {})
                assert not env_res.is_error
                env_data = _extract_data(env_res)
                assert env_data["is_usable"] is True
                assert env_data["backend"] in ("llvm_ad_mono_polarized", "cuda_ad_mono_polarized")

                # 3. Call list_scenes
                scenes_res = await session.call_tool("list_scenes", {})
                assert not scenes_res.is_error
                scenes_data = _extract_data(scenes_res)
                assert scenes_data["default_scene"] == "simple_reflector"

                # 4. Call analyze_simulation
                sim_params = {
                    "scene": "simple_reflector",
                    "frequency_hz": 3.5e9,
                    "tx_position": [0.0, -10.0, 5.0],
                    "rx_position": [0.0, 10.0, 5.0],
                    "tx_power_dbm": 30.0,
                }
                analysis_res = await session.call_tool("analyze_simulation", sim_params)
                assert not analysis_res.is_error
                analysis_data = _extract_data(analysis_res)
                assert "simulation_id" in analysis_data
                assert "simulation" in analysis_data
                assert "analysis" in analysis_data
                assert analysis_data["analysis"]["los_present"] is True

                # 5. Call generate_visualization
                sim_id = analysis_data["simulation_id"]
                viz_res = await session.call_tool("generate_visualization", {"simulation_id": sim_id, "plot_type": "all"})
                assert not viz_res.is_error
                viz_data = _extract_data(viz_res)
                assert viz_data["simulation_id"] == sim_id
                assert len(viz_data["generated_plots"]) == 3

                # 6. Call run_simulation with invalid input and verify is_error flag
                bad_res = await session.call_tool("run_simulation", {"frequency_hz": -50.0})
                assert bad_res.is_error
                assert "Frequency must be greater than 0 Hz." in bad_res.content[0].text

                # 7. Call generate_visualization with unknown simulation ID and verify error
                bad_viz = await session.call_tool("generate_visualization", {"simulation_id": "sim_non_existent"})
                assert bad_viz.is_error
                assert "not found in storage" in bad_viz.content[0].text

    asyncio.run(_run_stdio())
