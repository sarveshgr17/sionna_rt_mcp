"""Sionna Lab Backend Adapter.

Bridges modern web browser frontends (React / Vite) to the NVIDIA Sionna RT
MCP Server over the official Model Context Protocol (MCP) Streamable HTTP transport.

Responsibilities:
1. Connects to the canonical MCP server via self-contained `streamable_http_client`
   and `ClientSession` context managers, avoiding AnyIO TaskGroup/CancelScope corruption.
2. Exposes clean REST endpoints for MCP tool dispatching (`/api/mcp/call`, `/api/mcp/tools`).
3. Serves simulation artifacts (PNG heatmaps, CIR plots, ray paths) securely from
   `results/` and `experiments/` with robust path traversal validation.
4. Parses `.npz` numerical matrices for high-performance interactive 2D heatmaps.
5. Offloads synchronous file and matrix disk I/O to background threads via `anyio.to_thread`.
6. Recursively sanitizes `Infinity`, `-Infinity`, and `NaN` to `None` for standard JSON compliance.
7. Provides CORS headers for Vite frontend development.
"""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import math
import os
import sys
from typing import Any, Dict, List, Optional
import urllib.parse

# Ensure repository root is on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import anyio
import numpy as np
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route
import uvicorn

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] sionna_adapter: %(message)s",
)
logger = logging.getLogger("sionna_adapter")

MCP_SERVER_URL = os.environ.get("SIONNA_MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
ADAPTER_HOST = os.environ.get("SIONNA_ADAPTER_HOST", "0.0.0.0")
ADAPTER_PORT = int(os.environ.get("SIONNA_ADAPTER_PORT", "8080"))

RESULTS_DIR = os.path.join(_repo_root, "results")
EXPERIMENTS_DIR = os.path.join(_repo_root, "experiments")


def sanitize_floats(obj: Any) -> Any:
    """Recursively convert float('inf'), float('-inf'), and NaN to None for JSON compliance."""
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_floats(item) for item in obj]
    return obj


class MCPBridge:
    """Manages active MCP client operations to the Sionna RT MCP server.
    
    Executes each MCP tool call and tool listing inside a self-contained async with
    context manager block within the same async task to prevent AnyIO TaskGroup
    and CancelScope corruption across different tasks.
    """

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.discovered_tools: Dict[str, Any] = {}
        self.is_connected = False
        self._lock = asyncio.Lock()

    async def refresh_tools(self, timeout_seconds: float = 5.0) -> bool:
        """Query MCP server and refresh discovered tools cache with a strict timeout."""
        try:
            with anyio.fail_after(timeout_seconds):
                async with streamable_http_client(self.server_url) as streams:
                    read_stream, write_stream = streams[0], streams[1]
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools_res = await session.list_tools()
                        tools_dict = {}
                        for t in tools_res.tools:
                            tools_dict[t.name] = {
                                "name": t.name,
                                "description": t.description or "",
                                "inputSchema": getattr(t, "inputSchema", getattr(t, "input_schema", {})),
                            }
                        self.discovered_tools = tools_dict
                        self.is_connected = True
                        logger.info(
                            "Discovered %d MCP tools from %s: %s",
                            len(self.discovered_tools),
                            self.server_url,
                            list(self.discovered_tools.keys()),
                        )
                        return True
        except Exception as exc:
            logger.warning("Could not refresh MCP tools from %s (%s)", self.server_url, exc)
            self.is_connected = False
            return False

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        timeout_seconds: float = 60.0,
    ) -> Dict[str, Any]:
        """Invoke tool on MCP server inside a clean, self-contained session."""
        async with self._lock:
            with anyio.fail_after(timeout_seconds):
                async with streamable_http_client(self.server_url) as streams:
                    read_stream, write_stream = streams[0], streams[1]
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        res = await session.call_tool(name, arguments)

            is_error = bool(getattr(res, "isError", False) or getattr(res, "is_error", False))
            content_text = ""
            if hasattr(res, "content") and res.content:
                for item in res.content:
                    if hasattr(item, "text") and item.text:
                        content_text += item.text

            if is_error:
                raise RuntimeError(f"MCP Tool '{name}' returned error: {content_text}")

            try:
                return json.loads(content_text)
            except Exception:
                return {"raw_text": content_text}


bridge = MCPBridge(MCP_SERVER_URL)


@asynccontextmanager
async def lifespan(app: Starlette):
    """Starlette lifespan: non-blocking MCP warmup so Uvicorn binds immediately."""
    asyncio.create_task(bridge.refresh_tools(timeout_seconds=5.0))
    yield


# -----------------------------------------------------------------------------
# REST API Handlers
# -----------------------------------------------------------------------------

async def api_health(request: Request) -> JSONResponse:
    """Return health and connection status of adapter and MCP server without hanging."""
    # If locked by an active simulation, return immediately with status: busy
    if bridge._lock.locked():
        return JSONResponse({
            "status": "busy",
            "mcp_connected": True,
            "mcp_server_url": bridge.server_url,
            "tool_count": len(bridge.discovered_tools),
            "tools": list(bridge.discovered_tools.values()),
        })

    if not bridge.is_connected or not bridge.discovered_tools:
        try:
            await bridge.refresh_tools(timeout_seconds=2.0)
        except Exception:
            pass

    return JSONResponse({
        "status": "ok" if bridge.is_connected else "degraded",
        "mcp_connected": bridge.is_connected,
        "mcp_server_url": bridge.server_url,
        "tool_count": len(bridge.discovered_tools),
        "tools": list(bridge.discovered_tools.values()),
    })


async def api_tools(request: Request) -> JSONResponse:
    """List discovered MCP tools with full schemas."""
    if not bridge.is_connected or not bridge.discovered_tools:
        await bridge.refresh_tools(timeout_seconds=3.0)

    return JSONResponse({
        "status": "success",
        "tools": list(bridge.discovered_tools.values()),
    })


async def api_call_tool(request: Request) -> JSONResponse:
    """Execute an MCP tool via a clean, self-contained MCP session."""
    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse({"status": "error", "error": f"Invalid JSON body: {exc}"}, status_code=400)

    tool_name = body.get("name")
    if not tool_name:
        return JSONResponse({"status": "error", "error": "Missing 'name' field"}, status_code=400)

    arguments = body.get("arguments", {})
    logger.info("Executing MCP tool: %s with args: %s", tool_name, arguments)

    try:
        data = await bridge.call_tool(tool_name, arguments)
        return JSONResponse({"status": "success", "data": sanitize_floats(data)})
    except Exception as exc:
        logger.error("Error executing tool '%s': %s", tool_name, exc, exc_info=True)
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)


async def api_artifacts(request: Request) -> Response:
    """Safely serve simulation artifacts (PNG, JSON) from results/ or experiments/."""
    rel_path = request.path_params.get("path", "")
    decoded_path = urllib.parse.unquote(rel_path)

    # Disallow directory traversal markers
    if ".." in decoded_path:
        return JSONResponse({"status": "error", "error": "Invalid artifact path"}, status_code=400)

    # Allow absolute paths within repo or relative to repo
    if decoded_path.startswith(_repo_root) and os.path.isfile(decoded_path):
        candidate = os.path.abspath(decoded_path)
    elif os.path.isfile(os.path.abspath(os.path.join(_repo_root, decoded_path.lstrip("/")))):
        candidate = os.path.abspath(os.path.join(_repo_root, decoded_path.lstrip("/")))
    else:
        # Check within results or experiments
        candidate = None
        for root in [RESULTS_DIR, EXPERIMENTS_DIR]:
            alt = os.path.abspath(os.path.join(root, decoded_path.lstrip("/")))
            if os.path.isfile(alt):
                candidate = alt
                break

    if not candidate or not os.path.isfile(candidate):
        return JSONResponse({"status": "error", "error": f"Artifact not found: {decoded_path}"}, status_code=404)

    # Robust path traversal validation using os.path.commonpath
    allowed_roots = [os.path.abspath(RESULTS_DIR), os.path.abspath(EXPERIMENTS_DIR)]
    def is_safe(target: str, root_dir: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(target), os.path.abspath(root_dir)]) == os.path.abspath(root_dir)
        except Exception:
            return False

    if not any(is_safe(candidate, root) for root in allowed_roots):
        return JSONResponse({"status": "error", "error": "Access denied"}, status_code=403)

    media_type = "application/octet-stream"
    if candidate.endswith(".png"):
        media_type = "image/png"
    elif candidate.endswith(".jpg") or candidate.endswith(".jpeg"):
        media_type = "image/jpeg"
    elif candidate.endswith(".json"):
        media_type = "application/json"
    elif candidate.endswith(".npz"):
        media_type = "application/octet-stream"

    return FileResponse(candidate, media_type=media_type)


def _load_matrix_sync(exp_id: str) -> Dict[str, Any]:
    """Synchronous helper for loading and sanitizing .npz matrix data."""
    if not exp_id or ".." in exp_id:
        return {"error": "Invalid experiment_id", "code": 400}

    # Locate experiment folder
    exp_folder = os.path.join(EXPERIMENTS_DIR, exp_id)
    if not os.path.isdir(exp_folder):
        for d in os.listdir(EXPERIMENTS_DIR):
            if d == exp_id or d == f"experiment_{exp_id}":
                exp_folder = os.path.join(EXPERIMENTS_DIR, d)
                break

    npz_path = os.path.join(exp_folder, "radio_map_data.npz")
    if not os.path.isfile(npz_path):
        comp_npz = os.path.join(EXPERIMENTS_DIR, "comparisons", exp_id, "comparison_data.npz")
        if os.path.isfile(comp_npz):
            npz_path = comp_npz
        else:
            return {"error": f"Data not found for {exp_id}", "code": 404}

    with np.load(npz_path, allow_pickle=False) as data:
        result = {}
        for k in data.files:
            arr = data[k]
            if k in ("rss_dbm", "path_gain_db", "delta_rss_dbm", "delta_path_gain_db", "x_coordinates", "y_coordinates"):
                cleaned = np.where(np.isneginf(arr) | np.isnan(arr) | np.isposinf(arr), None, arr)
                result[k] = cleaned.tolist()
            elif k == "cell_centers":
                result["cell_centers_shape"] = list(arr.shape)

    return {"status": "success", "experiment_id": exp_id, "matrices": result}


async def api_matrix(request: Request) -> JSONResponse:
    """Return parsed 2D numerical data from radio_map_data.npz offloaded to worker thread."""
    exp_id = request.path_params.get("experiment_id", "").strip()
    try:
        data = await anyio.to_thread.run_sync(_load_matrix_sync, exp_id)
        if "error" in data:
            return JSONResponse({"status": "error", "error": data["error"]}, status_code=data.get("code", 400))
        return JSONResponse(sanitize_floats(data))
    except Exception as exc:
        logger.error("Failed to read npz file for %s: %s", exp_id, exc)
        return JSONResponse({"status": "error", "error": f"Failed reading numerical data: {exc}"}, status_code=500)


def _collect_telemetry_recent_sync() -> Dict[str, Any]:
    """Synchronous helper for reading P2P results and Radio Map experiments."""
    p2p_count = 0
    radio_map_count = 0
    recent_runs: List[Dict[str, Any]] = []
    latest_execution: Optional[Dict[str, Any]] = None

    # 1. Inspect P2P results directory
    if os.path.isdir(RESULTS_DIR):
        sim_folders = sorted(
            [d for d in os.listdir(RESULTS_DIR) if d.startswith("sim_")],
            reverse=True,
        )
        p2p_count = len(sim_folders)
        for d in sim_folders[:10]:
            metrics_path = os.path.join(RESULTS_DIR, d, "metrics.json")
            if os.path.isfile(metrics_path):
                try:
                    with open(metrics_path, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                    sim = m_data.get("simulation", {})
                    entry = {
                        "id": d,
                        "type": "p2p",
                        "scene": sim.get("scene_name", "munich"),
                        "carrier": f"{sim.get('frequency_hz', 3.5e9) / 1e9:.2f} GHz",
                        "received_power": sim.get("received_power_dbm"),
                        "num_paths": sim.get("num_paths", 2),
                        "created_at": m_data.get("created_at"),
                        "status": "SUCCESS",
                        "metrics": m_data,
                    }
                    recent_runs.append(entry)
                    if latest_execution is None:
                        latest_execution = entry
                except Exception:
                    pass

    # 2. Inspect Radio Map experiments directory
    if os.path.isdir(EXPERIMENTS_DIR):
        exp_folders = sorted(
            [d for d in os.listdir(EXPERIMENTS_DIR) if d.startswith("experiment_")],
            reverse=True,
        )
        radio_map_count = len(exp_folders)
        for d in exp_folders[:10]:
            meta_path = os.path.join(EXPERIMENTS_DIR, d, "metadata.json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                    entry = {
                        "id": d,
                        "type": "radio_map",
                        "scene": m_data.get("scene_name", "munich"),
                        "carrier": f"{m_data.get('frequency_hz', 3.5e9) / 1e9:.2f} GHz",
                        "mean_rss": m_data.get("mean_rss_dbm"),
                        "total_cells": m_data.get("total_cells"),
                        "created_at": m_data.get("created_at"),
                        "status": "SUCCESS",
                        "metadata": m_data,
                    }
                    recent_runs.append(entry)
                except Exception:
                    pass

    # Sort combined runs by created_at desc
    recent_runs.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)

    return {
        "status": "success",
        "total_runs": p2p_count + radio_map_count,
        "p2p_runs": p2p_count,
        "radio_map_runs": radio_map_count,
        "latest_execution": latest_execution,
        "recent_runs": recent_runs[:15],
    }


async def api_telemetry_recent(request: Request) -> JSONResponse:
    """Return high-level telemetry stats offloaded to worker thread without blocking event loop."""
    data = await anyio.to_thread.run_sync(_collect_telemetry_recent_sync)
    return JSONResponse(sanitize_floats(data))


_GEOMETRY_CACHE: Dict[str, Dict[str, Any]] = {}


def _extract_scene_geometry_sync(scene_name: str) -> Dict[str, Any]:
    """Extract full 3D mesh geometry for a scene in Three.js coordinates."""
    if scene_name in _GEOMETRY_CACHE:
        return _GEOMETRY_CACHE[scene_name]

    from src.engine import ensure_mitsuba_variant
    ensure_mitsuba_variant()
    import sionna.rt as rt

    scene_source = getattr(rt.scene, scene_name, None)
    if scene_source is None:
        return {"status": "error", "error": f"Unknown scene '{scene_name}'", "code": 404}

    scene = rt.load_scene(scene_source)
    bbox = scene.mi_scene.bbox()
    min_pt = [round(float(bbox.min[i]), 2) for i in range(3)]
    max_pt = [round(float(bbox.max[i]), 2) for i in range(3)]

    meshes_data = []
    for name, obj in scene.objects.items():
        mesh = getattr(obj, "mi_mesh", None)
        if mesh is not None:
            # Vertex positions in Sionna: [X, Y, Z] -> Three.js: [X, Z, -Y]
            raw_verts = np.array(mesh.vertex_positions_buffer(), dtype=np.float32).reshape(-1, 3)
            three_verts = np.column_stack([raw_verts[:, 0], raw_verts[:, 2], -raw_verts[:, 1]])
            faces = np.array(mesh.faces_buffer(), dtype=np.uint32)

            mat = getattr(obj, "radio_material", None)
            mat_type = getattr(mat, "itu_type", getattr(mat, "name", "concrete"))

            meshes_data.append({
                "name": str(name),
                "material": str(mat_type),
                "vertices": np.round(three_verts, 2).flatten().tolist(),
                "faces": faces.tolist(),
            })

    result = {
        "status": "success",
        "scene": scene_name,
        "bbox": {
            "min": [min_pt[0], min_pt[2], -max_pt[1]],
            "max": [max_pt[0], max_pt[2], -min_pt[1]],
            "raw_min": min_pt,
            "raw_max": max_pt,
        },
        "meshes": meshes_data,
        "total_vertices": sum(len(m["vertices"]) // 3 for m in meshes_data),
        "total_faces": sum(len(m["faces"]) // 3 for m in meshes_data),
    }

    _GEOMETRY_CACHE[scene_name] = result
    return result


async def api_scene_geometry(request: Request) -> JSONResponse:
    """Return full 3D mesh geometry for a scene offloaded to worker thread."""
    scene_name = request.path_params.get("scene_name", "").strip()
    try:
        data = await anyio.to_thread.run_sync(_extract_scene_geometry_sync, scene_name)
        if data.get("status") == "error":
            return JSONResponse({"status": "error", "error": data.get("error")}, status_code=data.get("code", 400))
        return JSONResponse(data)
    except Exception as exc:
        logger.error("Failed to extract scene geometry for %s: %s", scene_name, exc)
        return JSONResponse({"status": "error", "error": f"Failed extracting geometry: {exc}"}, status_code=500)


# -----------------------------------------------------------------------------
# Starlette Application Routing & Middleware
# -----------------------------------------------------------------------------

routes = [
    Route("/api/health", api_health, methods=["GET"]),
    Route("/api/mcp/tools", api_tools, methods=["GET"]),
    Route("/api/mcp/call", api_call_tool, methods=["POST"]),
    Route("/api/artifacts/{path:path}", api_artifacts, methods=["GET"]),
    Route("/api/matrix/{experiment_id:str}", api_matrix, methods=["GET"]),
    Route("/api/telemetry/recent", api_telemetry_recent, methods=["GET"]),
    Route("/api/scenes/{scene_name:str}/geometry", api_scene_geometry, methods=["GET"]),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    ),
    Middleware(GZipMiddleware, minimum_size=1000),
]

app = Starlette(
    routes=routes,
    middleware=middleware,
    lifespan=lifespan,
)


def main():
    logger.info("Starting Sionna Lab Backend Adapter on http://%s:%d", ADAPTER_HOST, ADAPTER_PORT)
    uvicorn.run(app, host=ADAPTER_HOST, port=ADAPTER_PORT, log_level="info")


if __name__ == "__main__":
    main()
