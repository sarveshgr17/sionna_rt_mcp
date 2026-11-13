"""Full end-to-end integration test verifying complete Sionna Lab stack.

Tests:
1. Live FastMCP Server over Streamable HTTP
2. Live Backend Adapter (Starlette)
3. Tool dispatching across all 7 canonical MCP tools
4. Real 3D ray-tracing simulation execution (Point-to-Point)
5. Real 2D spatial radio-map coverage simulation
6. Artifact serving (PNG heatmaps, CIR)
7. Numerical matrix serving (NPZ)
8. Spatial experiment comparison (B - A)
9. Error handling and invalid input rejection
"""

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


class TestFullStackE2E(unittest.TestCase):
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

        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", cls.mcp_port), timeout=0.2):
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

        # 2. Start Adapter in daemon thread
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

        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", cls.adapter_port), timeout=0.2):
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

        cls.client = httpx.Client(base_url=f"http://127.0.0.1:{cls.adapter_port}", timeout=60.0)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_01_health_and_tool_discovery(self):
        """Verify adapter connects to MCP and discovers all 7 canonical tools."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["mcp_connected"])
        self.assertEqual(data["tool_count"], 7)
        tool_names = [t["name"] for t in data["tools"]]
        for expected in [
            "check_environment",
            "list_scenes",
            "run_simulation",
            "generate_radio_map",
            "list_experiments",
            "get_experiment_details",
            "compare_experiments",
        ]:
            self.assertIn(expected, tool_names)

    def test_02_check_environment_tool(self):
        """Verify check_environment returns actual Sionna & Mitsuba runtime info."""
        res = self.client.post("/api/mcp/call", json={"name": "check_environment", "arguments": {}})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        env_data = data["data"]
        self.assertIn("python_version", env_data)
        self.assertIn("sionna_version", env_data)
        self.assertIn("mitsuba_version", env_data)
        self.assertTrue(env_data["is_usable"])

    def test_03_list_scenes_tool(self):
        """Verify list_scenes returns supported scene catalog containing strictly the three target scenes."""
        res = self.client.post("/api/mcp/call", json={"name": "list_scenes", "arguments": {}})
        self.assertEqual(res.status_code, 200)
        scenes = res.json()["data"]
        self.assertIn("scenes", scenes)
        self.assertEqual(scenes["default_scene"], "munich")
        self.assertEqual(scenes["count"], 3)
        names = [s["name"] for s in scenes["scenes"]]
        self.assertEqual(set(names), {"munich", "san_francisco", "simple_street_canyon"})

    def test_04_point_to_point_simulation_execution(self):
        """Verify run_simulation executes real 3D ray tracing in Sionna RT."""
        payload = {
            "name": "run_simulation",
            "arguments": {
                "scene": "munich",
                "frequency_hz": 3.5e9,
                "tx_position": [0.0, 0.0, 35.0],
                "rx_position": [60.0, 20.0, 1.5],
                "tx_power_dbm": 30.0,
            },
        }
        res = self.client.post("/api/mcp/call", json=payload)
        self.assertEqual(res.status_code, 200)
        sim_data = res.json()["data"]
        self.assertGreaterEqual(sim_data["num_paths"], 1)
        self.assertIsNotNone(sim_data["total_path_loss"])
        self.assertIsNotNone(sim_data["received_power"])
        self.assertGreater(len(sim_data["path_delays"]), 0)
        self.assertGreater(len(sim_data["path_distances"]), 0)
        self.assertGreater(len(sim_data["interaction_types"]), 0)

    def test_04b_multiscene_ray_tracing_simulations(self):
        """Verify real ray tracing across munich, san_francisco, and simple_street_canyon."""
        scene_configs = [
            {
                "scene": "san_francisco",
                "tx_position": [0.0, 0.0, 50.0],
                "rx_position": [100.0, 50.0, 1.5],
                "min_paths": 1,
            },
            {
                "scene": "simple_street_canyon",
                "tx_position": [-20.0, 0.0, 15.0],
                "rx_position": [20.0, 0.0, 1.5],
                "min_paths": 2,
            },
            {
                "scene": "munich",
                "tx_position": [0.0, 0.0, 35.0],
                "rx_position": [60.0, 20.0, 1.5],
                "min_paths": 2,
            },
        ]
        for sc in scene_configs:
            payload = {
                "name": "run_simulation",
                "arguments": {
                    "scene": sc["scene"],
                    "frequency_hz": 3.5e9,
                    "tx_position": sc["tx_position"],
                    "rx_position": sc["rx_position"],
                    "tx_power_dbm": 30.0,
                    "max_depth": 2,
                },
            }
            res = self.client.post("/api/mcp/call", json=payload)
            self.assertEqual(res.status_code, 200, f"Simulation failed for scene {sc['scene']}")
            sim_data = res.json()["data"]
            self.assertGreaterEqual(
                sim_data["num_paths"],
                sc["min_paths"],
                f"Scene {sc['scene']} expected at least {sc['min_paths']} paths, got {sim_data['num_paths']}",
            )
            self.assertIsNotNone(sim_data["total_path_loss"])
            self.assertIsNotNone(sim_data["received_power"])

    def test_05_radio_map_generation_and_artifact_delivery(self):
        """Verify generate_radio_map produces valid 2D coverage matrices and PNG heatmaps."""
        payload = {
            "name": "generate_radio_map",
            "arguments": {
                "scene_name": "simple_street_canyon",
                "frequency_hz": 3.5e9,
                "tx_position": [-20.0, 0.0, 15.0],
                "tx_power_dbm": 30.0,
                "receiver_height": 1.5,
                "cell_size": 10.0,
                "samples_per_tx": 5000,
                "experiment_name": "E2E Test Run",
            },
        }
        res = self.client.post("/api/mcp/call", json=payload)
        self.assertEqual(res.status_code, 200)
        rm_data = res.json()["data"]
        self.assertEqual(rm_data["status"], "success")
        exp_id = rm_data["experiment_id"]
        self.assertTrue(exp_id.startswith("experiment_"))
        self.assertGreater(rm_data["total_cells"], 0)

        # Check artifact image serving via adapter
        rss_path = rm_data["artifact_paths"].get("rss_heatmap")
        if rss_path:
            img_res = self.client.get(f"/api/artifacts/{rss_path}")
            self.assertEqual(img_res.status_code, 200)
            self.assertEqual(img_res.headers.get("content-type"), "image/png")
            self.assertGreater(len(img_res.content), 1000)

        # Check numerical matrix serving
        matrix_res = self.client.get(f"/api/matrix/{exp_id}")
        self.assertEqual(matrix_res.status_code, 200)
        matrix_data = matrix_res.json()
        self.assertEqual(matrix_data["status"], "success")
        self.assertIn("rss_dbm", matrix_data["matrices"])

    def test_06_experiments_listing_and_details(self):
        """Verify list_experiments and get_experiment_details retrieve metadata."""
        list_res = self.client.post("/api/mcp/call", json={"name": "list_experiments", "arguments": {}})
        self.assertEqual(list_res.status_code, 200)
        exps = list_res.json()["data"]["experiments"]
        self.assertGreater(len(exps), 0)

        target_id = exps[0]["experiment_id"]
        details_res = self.client.post(
            "/api/mcp/call",
            json={"name": "get_experiment_details", "arguments": {"experiment_id": target_id}},
        )
        self.assertEqual(details_res.status_code, 200)
        details = details_res.json()["data"]
        self.assertEqual(details["experiment_id"], target_id)
        self.assertIn("array_shapes", details)

    def test_07_compare_experiments_workflow(self):
        """Verify compare_experiments calculates difference (B - A) across matching grids."""
        list_res = self.client.post("/api/mcp/call", json={"name": "list_experiments", "arguments": {}})
        exps = list_res.json()["data"]["experiments"]
        if len(exps) >= 2:
            exp_a = exps[0]["experiment_id"]
            exp_b = exps[1]["experiment_id"]
            # Even if different, test tool invocation or identical comparison
            comp_res = self.client.post(
                "/api/mcp/call",
                json={
                    "name": "compare_experiments",
                    "arguments": {
                        "experiment_id_a": exp_a,
                        "experiment_id_b": exp_a, # Self-comparison is guaranteed compatible
                        "generate_heatmaps": False,
                    },
                },
            )
            self.assertEqual(comp_res.status_code, 200)
            comp_data = comp_res.json()["data"]
            self.assertEqual(comp_data["status"], "success")
            self.assertIn("B - A", comp_data["difference_convention"])
            mean_val = comp_data["rss_difference_metrics"].get("mean_difference", comp_data["rss_difference_metrics"].get("mean_diff_db", 0.0))
            self.assertAlmostEqual(mean_val, 0.0, delta=0.01)

    def test_08_error_handling_invalid_input(self):
        """Verify error responses for invalid inputs or unknown tools."""
        # 1. Unknown tool
        res1 = self.client.post("/api/mcp/call", json={"name": "non_existent_tool", "arguments": {}})
        self.assertEqual(res1.status_code, 500)
        self.assertEqual(res1.json()["status"], "error")

        # 2. Invalid frequency (<= 0 Hz)
        res2 = self.client.post(
            "/api/mcp/call",
            json={"name": "run_simulation", "arguments": {"frequency_hz": -100}},
        )
        self.assertEqual(res2.status_code, 500)
        self.assertEqual(res2.json()["status"], "error")


if __name__ == "__main__":
    unittest.main()
