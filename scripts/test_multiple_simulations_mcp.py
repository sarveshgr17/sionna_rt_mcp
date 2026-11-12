"""Verify that MCP server handles multiple consecutive simulation calls over stdio."""

import asyncio
import json
import sys
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def test_multiple():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["src/mcp_server.py"],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("[1] Session initialized successfully.")

            sim_args = {
                "scene": "simple_reflector",
                "frequency_hz": 3.5e9,
                "tx_position": [0.0, -10.0, 5.0],
                "rx_position": [0.0, 10.0, 5.0],
                "tx_power_dbm": 30.0,
            }

            for i in range(1, 4):
                print(f"[{i+1}] Calling run_simulation iteration {i}...")
                res = await session.call_tool("run_simulation", sim_args)
                data = json.loads(res.content[0].text)
                print(
                    f"     Iteration {i} SUCCESS: {data['num_paths']} paths,"
                    f" loss: {data['total_path_loss']:.2f} dB"
                )

            print("[5] All 3 consecutive simulation calls completed successfully!")
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(test_multiple()))

