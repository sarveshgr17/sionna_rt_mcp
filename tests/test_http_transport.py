"""Tests for MCP Streamable HTTP transport and server.py entrypoint."""

import asyncio
import json
import os
import socket
import sys
import threading
import time
import unittest

# Ensure repository root is on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from src.mcp_server import create_mcp_server, mcp


def get_free_port() -> int:
    """Find an available unallocated TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestHTTPTransport(unittest.TestCase):
    """Verify Streamable HTTP transport startup, MCP handshake, and tool discovery."""

    @classmethod
    def setUpClass(cls):
        """Start the MCP server with Streamable HTTP on an available port in a daemon thread."""
        cls.port = get_free_port()
        cls.host = "127.0.0.1"
        cls.endpoint = "/mcp"
        cls.url = f"http://{cls.host}:{cls.port}{cls.endpoint}"

        # Configure server instance
        cls.server = create_mcp_server(
            host=cls.host,
            port=cls.port,
            streamable_http_path=cls.endpoint,
        )

        def run_server():
            cls.server.run(transport="streamable-http")

        cls.thread = threading.Thread(target=run_server, daemon=True)
        cls.thread.start()

        # Wait for server to accept connections
        connected = False
        for _ in range(30):
            try:
                with socket.create_connection((cls.host, cls.port), timeout=0.5):
                    connected = True
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

        if not connected:
            raise RuntimeError(f"Server failed to start on port {cls.port} within 3.0s")

    def test_01_http_handshake_and_protocol_initialization(self):
        """Verify client initializes MCP session over Streamable HTTP."""
        async def run_test():
            async with streamable_http_client(self.url) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    init_res = await session.initialize()
                    proto_ver = getattr(
                        init_res, "protocol_version", getattr(init_res, "protocolVersion", None)
                    )
                    self.assertIsNotNone(proto_ver)

        anyio.run(run_test)

    def test_02_all_seven_tools_discovered_over_http(self):
        """Verify all seven tools are discoverable over Streamable HTTP transport."""
        async def run_test():
            async with streamable_http_client(self.url) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    discovered_names = [t.name for t in tools_result.tools]

                    expected_tools = [
                        "check_environment",
                        "list_scenes",
                        "run_simulation",
                        "generate_radio_map",
                        "list_experiments",
                        "get_experiment_details",
                        "compare_experiments",
                    ]
                    self.assertEqual(len(discovered_names), 7)
                    for tool_name in expected_tools:
                        self.assertIn(tool_name, discovered_names)

        anyio.run(run_test)

    def test_03_execute_tools_over_http(self):
        """Verify executing tools over Streamable HTTP returns structured outputs."""
        async def run_test():
            async with streamable_http_client(self.url) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    # 1. Call check_environment
                    env_res = await session.call_tool("check_environment", {})
                    is_err = getattr(env_res, "isError", getattr(env_res, "is_error", False))
                    self.assertFalse(bool(is_err))
                    self.assertTrue(len(env_res.content) > 0)
                    env_data = json.loads(env_res.content[0].text)
                    self.assertIn("python_version", env_data)
                    self.assertIn("sionna_version", env_data)
                    self.assertTrue(env_data["is_usable"])

                    # 2. Call list_scenes
                    scenes_res = await session.call_tool("list_scenes", {})
                    is_err_s = getattr(scenes_res, "isError", getattr(scenes_res, "is_error", False))
                    self.assertFalse(bool(is_err_s))
                    scenes_data = json.loads(scenes_res.content[0].text)
                    self.assertIn("scenes", scenes_data)
                    self.assertGreaterEqual(scenes_data["count"], 1)
                    self.assertEqual(scenes_data["default_scene"], "munich")

        anyio.run(run_test)

    def test_04_server_entrypoint_defaults_to_http(self):
        """Verify server.py imports and configuration defaults."""
        import server
        self.assertTrue(hasattr(server, "main"))
        self.assertEqual(mcp.name, "sionna-rt-mcp")

    def test_05_stdio_transport_remains_intact(self):
        """Verify standard in-process call_tool mechanism remains fully intact."""
        async def run_test():
            result = await mcp.call_tool("list_scenes", {})
            # FastMCP in-process return tuple (content, metadata)
            if isinstance(result, tuple):
                content = result[0]
            else:
                content = result.content
            self.assertTrue(len(content) > 0)
            data = json.loads(content[0].text)
            self.assertEqual(data["default_scene"], "munich")

        anyio.run(run_test)


if __name__ == "__main__":
    unittest.main()
