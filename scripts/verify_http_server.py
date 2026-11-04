"""End-to-end verification script for Sionna RT MCP Server over Streamable HTTP.

Connects to the running HTTP server on http://127.0.0.1:8000/mcp (or starts it in a
background process if not already running), discovers all 7 registered tools, executes
tool calls over HTTP, and verifies physical simulation outputs.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from typing import Any, Dict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure repository root is on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if the given host:port is currently listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


async def main() -> int:
    print("=" * 72)
    print("      Sionna RT MCP Server — Streamable HTTP Client Verification")
    print("=" * 72)

    host = "127.0.0.1"
    port = 8000
    endpoint = "/mcp"
    url = f"http://{host}:{port}{endpoint}"

    server_process = None

    if not is_port_in_use(port, host):
        print(f"\n[INFO] No server detected at {url}. Starting 'python server.py' in background...")
        server_process = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=_repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Wait up to 5 seconds for port to open
        for _ in range(50):
            if is_port_in_use(port, host):
                break
            time.sleep(0.1)
        else:
            print(f"[ERROR] Server failed to start on port {port}.")
            if server_process:
                server_process.kill()
            return 1
        print(f"[✓] Server started successfully on PID {server_process.pid}")
    else:
        print(f"\n[INFO] Detected active server listening at {url}")

    try:
        print(f"\n[STEP 1] Connecting to Streamable HTTP endpoint: {url}...")
        async with streamable_http_client(url) as (read_stream, write_stream, get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                init_res = await session.initialize()
                proto_ver = getattr(init_res, "protocol_version", getattr(init_res, "protocolVersion", "unknown"))
                session_id = get_session_id() or "active"
                print(f"[✓] Protocol initialized: {proto_ver} (Session: {session_id[:8]}...)")

                # Step 2: List tools
                print("\n[STEP 2] Discovering registered tools over HTTP...")
                tools_res = await session.list_tools()
                tool_names = [t.name for t in tools_res.tools]
                print(f"[✓] Discovered {len(tool_names)} tools: {', '.join(tool_names)}")

                expected_tools = [
                    "check_environment",
                    "list_scenes",
                    "run_simulation",
                    "generate_radio_map",
                    "list_experiments",
                    "get_experiment_details",
                    "compare_experiments",
                ]
                for exp in expected_tools:
                    assert exp in tool_names, f"Missing tool: {exp}"

                # Step 3: check_environment
                print("\n[STEP 3] Calling 'check_environment' over HTTP...")
                env_res = await session.call_tool("check_environment", {})
                env_data = json.loads(env_res.content[0].text)
                print(f"[✓] check_environment response: backend={env_data.get('backend')}, is_usable={env_data.get('is_usable')}")
                assert env_data.get("is_usable") is True

                # Step 4: list_scenes
                print("\n[STEP 4] Calling 'list_scenes' over HTTP...")
                scenes_res = await session.call_tool("list_scenes", {})
                scenes_data = json.loads(scenes_res.content[0].text)
                print(f"[✓] list_scenes response: default={scenes_data.get('default_scene')}, count={scenes_data.get('count')}")
                assert scenes_data.get("default_scene") == "simple_reflector"

                # Step 5: run_simulation
                print("\n[STEP 5] Calling 'run_simulation' (Point-to-Point Ray Tracing) over HTTP...")
                t0 = time.time()
                sim_res = await session.call_tool(
                    "run_simulation",
                    {
                        "scene": "simple_reflector",
                        "frequency_hz": 3.5e9,
                        "tx_position": [0.0, -10.0, 5.0],
                        "rx_position": [0.0, 10.0, 5.0],
                        "tx_power_dbm": 30.0,
                    },
                )
                dt = time.time() - t0
                sim_data = json.loads(sim_res.content[0].text)
                print(f"[✓] run_simulation executed in {dt:.3f} s:")
                print(f"    Paths found:    {sim_data.get('num_paths')}")
                print(f"    Path loss:      {sim_data.get('total_path_loss_db'):.2f} dB")
                print(f"    Received power: {sim_data.get('received_power_dbm'):.2f} dBm")
                print(f"    Delays:         {sim_data.get('delays_ns')} ns")
                assert sim_data.get("num_paths") == 2

                # Step 6: list_experiments
                print("\n[STEP 6] Calling 'list_experiments' over HTTP...")
                exp_res = await session.call_tool("list_experiments", {})
                exp_data = json.loads(exp_res.content[0].text)
                print(f"[✓] list_experiments response: count={exp_data.get('count')}")
                assert exp_data.get("status") == "success"

        print("\n" + "=" * 72)
        print("RESULT: Streamable HTTP Client Verification PASSED (All 6 Steps OK)! ✓")
        print("=" * 72)
        return 0

    finally:
        if server_process is not None:
            print("\n[INFO] Terminating background server process...")
            server_process.terminate()
            try:
                server_process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                server_process.kill()


if __name__ == "__main__":
    sys.exit(anyio.run(main))

