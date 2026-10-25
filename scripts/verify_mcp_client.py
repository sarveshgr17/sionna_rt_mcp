"""Manual verification script simulating an MCP AI client over stdio transport.

Sequence:
1. Start MCP server subprocess over stdio.
2. Discover available tools.
3. Call 'check_environment' and print structured response.
4. Call 'list_scenes' and print available scenes.
5. Call 'run_simulation' with canonical parameters.
6. Verify physical metrics match expected Sionna RT values.
"""

import asyncio
import json
import sys
from typing import Any, Dict

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def extract_data(call_result: Any) -> Dict[str, Any]:
    if call_result.structured_content and "result" in call_result.structured_content:
        return call_result.structured_content["result"]
    if call_result.content and hasattr(call_result.content[0], "text"):
        return json.loads(call_result.content[0].text)
    return call_result.structured_content or {}


async def main() -> int:
    print("=" * 65)
    print("       Sionna RT MCP Server - End-to-End Client Verification")
    print("=" * 65)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["src/mcp_server.py"],
    )

    print("[1] Connecting to MCP server via stdio transport...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_res = await session.initialize()
            print(f"[✓] Initialized connection: Protocol version {init_res.protocol_version}")

            # 2. Discover tools
            print("\n[2] Discovering available MCP tools...")
            tools_response = await session.list_tools()
            tools = tools_response.tools
            print(f"[✓] Discovered {len(tools)} tools:")
            for t in tools:
                print(f"    - {t.name}: {t.description[:75]}...")

            # 3. Call check_environment
            print("\n[3] Calling 'check_environment' tool...")
            env_result = await session.call_tool("check_environment", {})
            env_data = extract_data(env_result)
            print(f"[✓] Response from check_environment:")
            print(json.dumps(env_data, indent=4))
            assert env_data.get("is_usable") is True, "Environment is not usable"

            # 4. Call list_scenes
            print("\n[4] Calling 'list_scenes' tool...")
            scenes_result = await session.call_tool("list_scenes", {})
            scenes_data = extract_data(scenes_result)
            print(f"[✓] Response from list_scenes:")
            print(json.dumps(scenes_data, indent=4))

            # 5. Call run_simulation
            print("\n[5] Calling 'run_simulation' tool with canonical parameters:")
            sim_args = {
                "scene": "simple_reflector",
                "frequency_hz": 3.5e9,
                "tx_position": [0.0, -10.0, 5.0],
                "rx_position": [0.0, 10.0, 5.0],
                "tx_power_dbm": 30.0,
            }
            print(f"    Input arguments: {json.dumps(sim_args)}")

            sim_result = await session.call_tool("run_simulation", sim_args)
            sim_data = extract_data(sim_result)
            print(f"[✓] Response from run_simulation:")
            print(json.dumps(sim_data, indent=4))

            # 6. Verify physical values
            print("\n[6] Verifying physical plausibility against Sionna RT:")
            num_paths = sim_data.get("number_of_paths", sim_data.get("num_paths"))
            path_loss = sim_data.get("total_path_loss")
            rx_power = sim_data.get("received_power")
            delays = sim_data.get("path_delays")

            print(f"    - Total paths:    {num_paths} (expected: 2)")
            print(f"    - Path loss:      {path_loss:.2f} dB (expected: ~66.8 dB)")
            print(f"    - Received power: {rx_power:.2f} dBm (expected: ~-36.8 dBm)")
            print(f"    - Delays:         {[round(d, 2) for d in delays]} ns (expected: [~66.71, ~74.59] ns)")

            assert num_paths == 2, f"Expected 2 paths, got {num_paths}"
            assert 65.0 < path_loss < 69.0, f"Path loss {path_loss} outside expected ~66.8 dB range"
            assert -39.0 < rx_power < -35.0, f"RX power {rx_power} outside expected ~-36.8 dBm range"
            assert len(delays) == 2, f"Expected 2 delays, got {len(delays)}"

            print("\n" + "=" * 65)
            print("RESULT: All 6 client verification steps passed successfully! ✓")
            print("=" * 65)
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
