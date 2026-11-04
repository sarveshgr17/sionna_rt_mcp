"""End-to-end integration tests: MCPDirectClient and AgentExecutor with live MCP server."""

import os
import socket
import sys
import threading
import time
import unittest

# Ensure repository root is on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import anyio
from src.mcp_server import create_mcp_server
from src.terminal_agent.context import SessionContext
from src.terminal_agent.executor import AgentExecutor
from src.terminal_agent.mcp_client import MCPDirectClient


def get_free_port() -> int:
    """Finds an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestMCPClientAndTerminalE2E(unittest.TestCase):
    """End-to-end tests executing real operations against live MCP server."""

    @classmethod
    def setUpClass(cls):
        """Starts live FastMCP server over Streamable HTTP in a daemon thread."""
        cls.port = get_free_port()
        cls.host = "127.0.0.1"
        cls.endpoint = "/mcp"
        cls.url = f"http://{cls.host}:{cls.port}{cls.endpoint}"

        cls.server = create_mcp_server(
            host=cls.host,
            port=cls.port,
            streamable_http_path=cls.endpoint,
        )

        def run_srv():
            cls.server.run(transport="streamable-http")

        cls.thread = threading.Thread(target=run_srv, daemon=True)
        cls.thread.start()

        # Wait for port readiness
        connected = False
        for _ in range(40):
            try:
                with socket.create_connection((cls.host, cls.port), timeout=0.2):
                    connected = True
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

        if not connected:
            raise RuntimeError(f"Test MCP server failed to bind to {cls.url} within 4s")

    def test_01_client_connect_and_tool_discovery(self):
        """Verify MCPDirectClient discovers all seven tools dynamically."""
        async def run_test():
            client = MCPDirectClient(server_url=self.url)
            try:
                tools = await client.connect()
                expected = [
                    "check_environment",
                    "list_scenes",
                    "run_simulation",
                    "generate_radio_map",
                    "list_experiments",
                    "get_experiment_details",
                    "compare_experiments",
                ]
                self.assertEqual(len(tools), 7)
                for tool_name in expected:
                    self.assertIn(tool_name, tools)
                    self.assertIn(tool_name, client.tool_schemas)
            finally:
                await client.disconnect()

        anyio.run(run_test)

    def test_02_e2e_environment_and_scene_query(self):
        """Verify natural language commands for environment and scenes through executor."""
        async def run_test():
            client = MCPDirectClient(server_url=self.url)
            await client.connect()
            try:
                executor = AgentExecutor(mcp_client=client)

                # Check environment
                env_res = await executor.execute_instruction("Check whether Sionna is working")
                self.assertIn("READY (Usable)", env_res.output)
                self.assertIn("llvm_ad_mono_polarized", env_res.output)

                # List scenes
                scene_res = await executor.execute_instruction("Show available scenes")
                self.assertIn("simple_reflector", scene_res.output)
            finally:
                await client.disconnect()

        anyio.run(run_test)

    def test_03_e2e_radio_map_real_simulation(self):
        """Verify real Sionna RT radio map generation via natural language instruction."""
        async def run_test():
            client = MCPDirectClient(server_url=self.url)
            await client.connect()
            ctx = SessionContext()
            executor = AgentExecutor(mcp_client=client, context=ctx)
            try:
                # Use small cell size and ray budget for quick test execution (~1s)
                prompt = (
                    "Generate a radio map for simple_reflector at 3.5 GHz. "
                    "Place transmitter at [0, -10, 5]. Use 10 metre cell size and 1000 rays."
                )
                res = await executor.execute_instruction(prompt)

                self.assertIn("Assistant: I understood your request.", res.output)
                self.assertIn("MCP: Simulation completed successfully.", res.output)
                self.assertIn("Experiment ID:", res.output)
                self.assertIn("Coverage:", res.output)
                self.assertIn("RSS Heatmap:", res.output)
                self.assertIn("Path Gain Heatmap:", res.output)

                # Verify context updated
                self.assertIsNotNone(ctx.last_experiment_id)
                exp_id = ctx.last_experiment_id

                # Query details of the newly created experiment
                details_res = await executor.execute_instruction(f"Give me details of experiment ID {exp_id}")
                self.assertIn("Experiment Details:", details_res.output)
                self.assertIn(exp_id, details_res.output)

            finally:
                await client.disconnect()

        anyio.run(run_test)


if __name__ == "__main__":
    unittest.main()

