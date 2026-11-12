"""Integration tests for Sionna Lab backend adapter."""

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

import httpx2 as httpx
from src.mcp_server import create_mcp_server


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestBackendAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mcp_port = get_free_port()
        cls.adapter_port = get_free_port()
        cls.mcp_url = f"http://127.0.0.1:{cls.mcp_port}/mcp"

        # 1. Start MCP Server in daemon thread
        cls.mcp_server = create_mcp_server(
            host="127.0.0.1",
            port=cls.mcp_port,
            streamable_http_path="/mcp",
        )

        def run_mcp():
            cls.mcp_server.run(transport="streamable-http")

        cls.mcp_thread = threading.Thread(target=run_mcp, daemon=True)
        cls.mcp_thread.start()

        # Wait for MCP server port
        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", cls.mcp_port), timeout=0.2):
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

        # 2. Start Adapter in daemon thread pointing to test MCP server
        os.environ["SIONNA_MCP_SERVER_URL"] = cls.mcp_url
        os.environ["SIONNA_ADAPTER_HOST"] = "127.0.0.1"
        os.environ["SIONNA_ADAPTER_PORT"] = str(cls.adapter_port)

        import adapter.server as srv
        srv.bridge.server_url = cls.mcp_url
        import uvicorn

        def run_adapter():
            uvicorn.run(srv.app, host="127.0.0.1", port=cls.adapter_port, log_level="warning")

        cls.adapter_thread = threading.Thread(target=run_adapter, daemon=True)
        cls.adapter_thread.start()

        # Wait for Adapter port
        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", cls.adapter_port), timeout=0.2):
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

    def test_01_adapter_health_and_tools_discovery(self):
        """Verify adapter connects to MCP server and lists all 7 tools."""
        with httpx.Client(base_url=f"http://127.0.0.1:{self.adapter_port}") as client:
            resp = client.get("/api/health")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "ok")
            self.assertTrue(data["mcp_connected"])
            self.assertEqual(data["tool_count"], 7)

    def test_02_adapter_call_check_environment(self):
        """Verify tool execution through adapter endpoint."""
        with httpx.Client(base_url=f"http://127.0.0.1:{self.adapter_port}") as client:
            resp = client.post("/api/mcp/call", json={"name": "check_environment", "arguments": {}})
            self.assertEqual(resp.status_code, 200)
            res_data = resp.json()
            self.assertEqual(res_data["status"], "success")
            self.assertIn("python_version", res_data["data"])
            self.assertIn("mitsuba_version", res_data["data"])

    def test_03_adapter_telemetry_recent(self):
        """Verify telemetry recent runs endpoint."""
        with httpx.Client(base_url=f"http://127.0.0.1:{self.adapter_port}") as client:
            resp = client.get("/api/telemetry/recent")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "success")
            self.assertGreater(data["total_runs"], 0)


if __name__ == "__main__":
    unittest.main()

