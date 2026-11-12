"""Complete end-to-end runtime verification of the Sionna RT Radio Map workflow.

Phase 9.4 Deliverable:
Validates the entire 2D spatial radio-map simulation, result extraction,
heatmap visualization, filesystem persistence, retrieval, and spatial
comparison workflows using actual Sionna RT RadioMapSolver output over
the official Model Context Protocol (MCP) stdio client.
"""

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np

# MCP client imports
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Ensure repo root and src are on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_dir = os.path.join(_repo_root, "src")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from experiment_store import ExperimentStore


def extract_data(call_result: Any) -> Dict[str, Any]:
    """Helper to extract dictionary payload from MCP CallToolResult."""
    if hasattr(call_result, "structured_content") and call_result.structured_content:
        if "result" in call_result.structured_content:
            return call_result.structured_content["result"]
        return call_result.structured_content
    if hasattr(call_result, "content") and call_result.content:
        for item in call_result.content:
            if hasattr(item, "text"):
                try:
                    return json.loads(item.text)
                except Exception:
                    pass
    return {}


async def main() -> int:
    print("=" * 75)
    print("     PHASE 9.4: Sionna RT Radio Map Runtime Verification (MCP)")
    print("=" * 75)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["src/mcp_server.py"],
    )

    print("\n[STEP 1] Connecting to MCP server via stdio transport...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_res = await session.initialize()
            proto_ver = getattr(init_res, "protocol_version", getattr(init_res, "protocolVersion", "unknown"))
            print(f"[✓] Protocol initialized: {proto_ver}")

            # Discover tools
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            print(f"[✓] Discovered {len(tool_names)} tools: {', '.join(tool_names)}")

            required_tools = [
                "generate_radio_map",
                "list_experiments",
                "get_experiment_details",
                "compare_experiments",
            ]
            for rt in required_tools:
                assert rt in tool_names, f"Required tool '{rt}' missing from MCP server"

            # -----------------------------------------------------------------
            # [STEP 2] Execute Experiment A (TX power = 30.0 dBm)
            # -----------------------------------------------------------------
            print("\n" + "-" * 75)
            print("[STEP 2] Executing generate_radio_map (Experiment A: 30 dBm)...")
            print("-" * 75)

            args_a = {
                "scene_name": "simple_reflector",
                "frequency_hz": 3.5e9,
                "tx_position": [0.0, -10.0, 5.0],
                "tx_power_dbm": 30.0,
                "receiver_height": 1.5,
                "cell_size": 5.0,
                "samples_per_tx": 10_000,
                "max_depth": 3,
                "los": True,
                "specular_reflection": True,
                "diffraction": True,
                "scattering": False,
                "experiment_name": "validation_run_30dbm",
            }
            print(f"    Parameters: scene={args_a['scene_name']}, freq={args_a['frequency_hz']/1e9} GHz, "
                  f"cell_size={args_a['cell_size']}m, rays={args_a['samples_per_tx']}")

            t0 = time.time()
            res_a = await session.call_tool("generate_radio_map", args_a)
            t_elapsed_a = time.time() - t0

            data_a = extract_data(res_a)
            exp_id_a = data_a.get("experiment_id")
            assert exp_id_a, f"Failed to get experiment_id from response: {res_a}"

            print(f"[✓] Experiment A completed in {t_elapsed_a:.2f} s")
            print(f"    Experiment ID:       {exp_id_a}")
            print(f"    Grid dimensions:     {data_a.get('grid_dimensions')}")
            print(f"    Total cells:         {data_a.get('total_cells')}")
            print(f"    Valid cells:         {data_a.get('valid_cells')}")
            print(f"    Zero power cells:    {data_a.get('zero_power_cells')}")
            print(f"    Coverage percentage: {data_a.get('coverage_percentage'):.1f}%")
            print(f"    RSS Min / Mean / Max: {data_a.get('min_rss_dbm'):.2f} / "
                  f"{data_a.get('mean_rss_dbm'):.2f} / {data_a.get('max_rss_dbm'):.2f} dBm")

            # -----------------------------------------------------------------
            # [STEP 3] Validate Heatmaps for Experiment A
            # -----------------------------------------------------------------
            print("\n[STEP 3] Verifying generated heatmap artifacts...")
            artifact_paths_a = data_a.get("artifact_paths", {})
            rss_png_a = artifact_paths_a.get("rss_heatmap")
            pg_png_a = artifact_paths_a.get("path_gain_heatmap")

            assert rss_png_a, "rss_heatmap path missing from artifact_paths"
            assert pg_png_a, "path_gain_heatmap path missing from artifact_paths"

            assert os.path.exists(rss_png_a), f"RSS heatmap file not found: {rss_png_a}"
            assert os.path.exists(pg_png_a), f"Path-gain heatmap file not found: {pg_png_a}"

            rss_size_a = os.path.getsize(rss_png_a)
            pg_size_a = os.path.getsize(pg_png_a)
            print(f"[✓] RSS heatmap:       {rss_png_a} ({rss_size_a:,} bytes)")
            print(f"[✓] Path-gain heatmap: {pg_png_a} ({pg_size_a:,} bytes)")
            assert rss_size_a > 1000, f"RSS heatmap file abnormally small ({rss_size_a} bytes)"
            assert pg_size_a > 1000, f"Path-gain heatmap file abnormally small ({pg_size_a} bytes)"

            # -----------------------------------------------------------------
            # [STEP 4] Validate Experiment Persistence & Array Storage
            # -----------------------------------------------------------------
            print("\n[STEP 4] Validating experiment persistence via MCP and ExperimentStore...")
            list_res = await session.call_tool("list_experiments", {})
            list_data = extract_data(list_res)
            exp_list = list_data.get("experiments", [])
            found_ids = [e.get("experiment_id") for e in exp_list]
            assert exp_id_a in found_ids, f"Experiment {exp_id_a} not found in list_experiments"
            print(f"[✓] list_experiments verified: found {len(exp_list)} stored experiments (including {exp_id_a})")

            details_res = await session.call_tool("get_experiment_details", {"experiment_id": exp_id_a})
            details_data = extract_data(details_res)
            assert details_data.get("experiment_id") == exp_id_a, "get_experiment_details returned wrong ID"
            assert details_data.get("scene_name") == "simple_reflector", "get_experiment_details metadata mismatch"
            print(f"[✓] get_experiment_details verified: metadata intact")

            # Load actual saved experiment and compressed NPZ arrays from disk
            store = ExperimentStore()
            loaded_result = store.load_experiment(exp_id_a)
            rss_dbm_arr_a = loaded_result.rss_dbm
            pg_db_arr_a = loaded_result.path_gain_db
            centers_arr_a = loaded_result.cell_centers

            print(f"[✓] Stored numerical arrays loaded:")
            print(f"    rss_dbm shape:      {rss_dbm_arr_a.shape}, finite count: {np.count_nonzero(np.isfinite(rss_dbm_arr_a))}")
            print(f"    path_gain_db shape: {pg_db_arr_a.shape}, finite count: {np.count_nonzero(np.isfinite(pg_db_arr_a))}")
            print(f"    cell_centers shape: {centers_arr_a.shape}")

            ny, nx = data_a["grid_dimensions"]
            assert rss_dbm_arr_a.shape == (ny, nx), f"Array shape {rss_dbm_arr_a.shape} != grid dimensions {(ny, nx)}"
            assert pg_db_arr_a.shape == (ny, nx), f"Path gain shape mismatch"
            assert centers_arr_a.shape == (ny, nx, 3), f"Cell centers shape mismatch"

            # -----------------------------------------------------------------
            # [STEP 5] Execute Experiment B (TX power = 40.0 dBm, delta = +10 dB)
            # -----------------------------------------------------------------
            print("\n" + "-" * 75)
            print("[STEP 5] Executing generate_radio_map (Experiment B: 40 dBm, delta = +10 dB)...")
            print("-" * 75)

            args_b = dict(args_a)
            args_b["tx_power_dbm"] = 40.0
            args_b["experiment_name"] = "validation_run_40dbm"

            t0 = time.time()
            res_b = await session.call_tool("generate_radio_map", args_b)
            t_elapsed_b = time.time() - t0

            data_b = extract_data(res_b)
            exp_id_b = data_b.get("experiment_id")
            assert exp_id_b, f"Failed to get experiment_id from response B: {res_b}"

            print(f"[✓] Experiment B completed in {t_elapsed_b:.2f} s")
            print(f"    Experiment ID:       {exp_id_b}")
            print(f"    RSS Min / Mean / Max: {data_b.get('min_rss_dbm'):.2f} / "
                  f"{data_b.get('mean_rss_dbm'):.2f} / {data_b.get('max_rss_dbm'):.2f} dBm")

            # -----------------------------------------------------------------
            # [STEP 6] Compare Experiments via MCP
            # -----------------------------------------------------------------
            print("\n" + "-" * 75)
            print("[STEP 6] Executing compare_experiments (Experiment B minus Experiment A)...")
            print("-" * 75)

            comp_args = {
                "experiment_id_a": exp_id_a,
                "experiment_id_b": exp_id_b,
                "generate_heatmaps": True,
            }
            res_comp = await session.call_tool("compare_experiments", comp_args)
            data_comp = extract_data(res_comp)

            convention = data_comp.get("difference_convention")
            rss_diff_metrics = data_comp.get("rss_difference_metrics", {})
            pg_diff_metrics = data_comp.get("path_gain_difference_metrics", {})
            comp_heatmaps = data_comp.get("heatmaps", {})

            print(f"[✓] Comparison completed:")
            print(f"    Convention:                 {convention}")
            print(f"    Total cells evaluated:      {data_comp.get('total_cells')}")
            print(f"    Valid cells:                {data_comp.get('valid_cells')}")
            print(f"    RSS difference mean:        {rss_diff_metrics.get('mean_difference'):.4f} dB (expected: ~+10.0 dB)")
            print(f"    RSS difference range:       [{rss_diff_metrics.get('min_difference'):.4f}, {rss_diff_metrics.get('max_difference'):.4f}] dB")
            print(f"    Path-gain difference mean:  {pg_diff_metrics.get('mean_difference'):.4f} dB (expected: ~0.0 dB)")
            print(f"    Path-gain difference range: [{pg_diff_metrics.get('min_difference'):.4f}, {pg_diff_metrics.get('max_difference'):.4f}] dB")

            # Validate physical plausibility of delta
            mean_rss_delta = rss_diff_metrics.get("mean_difference")
            mean_pg_delta = pg_diff_metrics.get("mean_difference")

            assert abs(mean_rss_delta - 10.0) < 0.2, (
                f"RSS difference mean {mean_rss_delta} deviates from expected +10.0 dB"
            )
            assert abs(mean_pg_delta - 0.0) < 0.2, (
                f"Path-gain difference mean {mean_pg_delta} deviates from expected 0.0 dB"
            )

            # Check comparison heatmaps
            assert "rss_diff_heatmap" in comp_heatmaps, "rss_diff_heatmap missing"
            assert "path_gain_diff_heatmap" in comp_heatmaps, "path_gain_diff_heatmap missing"

            rss_diff_png = comp_heatmaps["rss_diff_heatmap"]
            pg_diff_png = comp_heatmaps["path_gain_diff_heatmap"]
            assert os.path.exists(rss_diff_png), f"File not found: {rss_diff_png}"
            assert os.path.exists(pg_diff_png), f"File not found: {pg_diff_png}"
            print(f"[✓] RSS difference heatmap:       {rss_diff_png} ({os.path.getsize(rss_diff_png):,} bytes)")
            print(f"[✓] Path-gain difference heatmap: {pg_diff_png} ({os.path.getsize(pg_diff_png):,} bytes)")

    print("\n" + "=" * 75)
    print("PHASE 9.4 VERIFICATION COMPLETE: ALL RADIO MAP TESTS PASSED! ✓")
    print("=" * 75)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
