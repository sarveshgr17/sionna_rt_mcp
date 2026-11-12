"""Model Context Protocol (MCP) Server for NVIDIA Sionna RT and Radio Map Management.

This server provides an interface layer exposing the Sionna RT SimulationEngine
and RadioMap subsystems to MCP-compatible AI clients (Claude Desktop, Cursor, etc.)
via stdio transport.

Supported Tools:
1. Point-to-Point Propagation Tools:
   - check_environment: Verify runtime simulator availability and backend.
   - list_scenes: List available 3D geometric propagation scenes.
   - run_simulation: Execute point-to-point ray-tracing simulations.

2. Radio Map & Experiment Management Tools (Phases 2-6 Integration):
   - generate_radio_map: Execute 2D spatial radio-map simulation, extract metrics,
     render heatmaps, and persist the experiment.
   - list_experiments: Retrieve metadata summaries of saved experiments.
   - get_experiment_details: Retrieve detailed metadata and artifact paths for an experiment.
   - compare_experiments: Calculate spatial differences (B - A) between two experiments
     and generate diverging difference heatmaps.
"""

from datetime import datetime, timezone
import json
import logging
import math
import os
import shutil
import sys
import tempfile
from typing import Annotated, Any, Dict, List, Optional, Tuple, Union

from pydantic import Field

# Ensure repository root is on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_dir = os.path.abspath(os.path.dirname(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Standalone LLVM environment configuration for native Windows runtime
_llvm_standalone = r"C:\Users\eulo_\LLVM-standalone\LLVM-C.dll"
if os.path.isfile(_llvm_standalone):
    os.environ.setdefault("DRJIT_LIBLLVM_PATH", _llvm_standalone)
    os.environ.setdefault("DRJIT_LIBCUDA_PATH", "DISABLED")
    os.environ.setdefault("DRJIT_LIBOPTIX_PATH", "DISABLED")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

def _harmonize_module_aliases() -> None:
    """Ensure modules imported via 'src.<mod>' and '<mod>' share identical class identities."""
    for mod_name in [
        "config",
        "engine",
        "result",
        "formatter",
        "simulation",
        "radio_map_config",
        "radio_map_engine",
        "radio_map_result",
        "radio_map_formatter",
        "experiment_store",
        "experiment_comparator",
    ]:
        src_name = f"src.{mod_name}"
        if src_name in sys.modules and mod_name not in sys.modules:
            sys.modules[mod_name] = sys.modules[src_name]
        elif mod_name in sys.modules and src_name not in sys.modules:
            sys.modules[src_name] = sys.modules[mod_name]
        elif src_name in sys.modules and mod_name in sys.modules:
            if sys.modules[mod_name] is not sys.modules[src_name]:
                sys.modules[mod_name] = sys.modules[src_name]

_harmonize_module_aliases()

# Route all application diagnostics to stderr to prevent corrupting stdio MCP frames
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sionna_rt_mcp")

# Import MCP SDK (supporting MCP 2.x MCPServer, MCP 1.x FastMCP, and graceful in-process fallback)
try:
    try:
        from mcp.server.mcpserver import MCPServer as FastMCP
        from mcp.server.mcpserver.exceptions import ToolError
    except (ImportError, ModuleNotFoundError):
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError
except (ImportError, ModuleNotFoundError):
    # Standalone fallback when mcp package is not installed in current environment
    class ToolError(Exception):  # type: ignore
        """Tool execution error raised by MCP tools."""
        pass

    class FastMCP:  # type: ignore
        """Lightweight in-process FastMCP implementation."""
        def __init__(
            self,
            name: str = "sionna-rt-mcp",
            instructions: Optional[str] = None,
            host: str = "127.0.0.1",
            port: int = 8000,
            streamable_http_path: str = "/mcp",
            **kwargs: Any,
        ) -> None:
            self.name = name
            self.instructions = instructions
            self._tools: Dict[str, Dict[str, Any]] = {}
            self.settings = type("Settings", (), {
                "host": host,
                "port": port,
                "streamable_http_path": streamable_http_path,
            })()

        def tool(self, name: Optional[str] = None, description: Optional[str] = None):
            def decorator(func):
                tool_name = name or func.__name__
                tool_desc = description or func.__doc__ or ""
                self._tools[tool_name] = {
                    "func": func,
                    "name": tool_name,
                    "description": tool_desc.strip(),
                }
                return func
            return decorator

        async def list_tools(self):
            class _ToolDesc:
                def __init__(self, name: str, description: str):
                    self.name = name
                    self.description = description
            return [_ToolDesc(t["name"], t["description"]) for t in self._tools.values()]

        async def call_tool(self, name: str, arguments: Dict[str, Any]):
            if name not in self._tools:
                raise ToolError(f"Tool '{name}' not found.")
            func = self._tools[name]["func"]
            result = func(**arguments)
            class _CallToolResult:
                def __init__(self, res):
                    self.structured_content = {"result": res}
                    self.content = [type("TextContent", (), {"text": json.dumps(res, default=str)})()]
                    self.is_error = False
            return _CallToolResult(result)

        def run(self, transport: str = "stdio") -> None:
            logger.info("Running FastMCP server '%s' over %s", self.name, transport)

# Point-to-Point simulation imports
try:
    from src.config import SimulationConfig
    from src.engine import SimulationEngine
    from src.result import SimulationResult
except ImportError:
    from config import SimulationConfig
    from engine import SimulationEngine
    from result import SimulationResult

# Radio Map & Experiment Management imports (Phases 2-6)
try:
    from src.radio_map_config import RadioMapConfig
except (ImportError, ModuleNotFoundError):
    from radio_map_config import RadioMapConfig

try:
    from src.radio_map_engine import RadioMapEngine
except (ImportError, ModuleNotFoundError):
    from radio_map_engine import RadioMapEngine

try:
    from src.radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from radio_map_result import RadioMapResult

try:
    from src.radio_map_formatter import RadioMapFormatter
except (ImportError, ModuleNotFoundError):
    from radio_map_formatter import RadioMapFormatter

try:
    from src.experiment_store import ExperimentStore
except (ImportError, ModuleNotFoundError):
    from experiment_store import ExperimentStore

try:
    from src.experiment_comparator import ComparisonResult, ExperimentComparator
except (ImportError, ModuleNotFoundError):
    from experiment_comparator import ComparisonResult, ExperimentComparator

_harmonize_module_aliases()

# Supported 3D geometric scenes catalog
SUPPORTED_SCENES = {
    "simple_reflector": {
        "name": "simple_reflector",
        "description": (
            "Canonical two-path propagation scene containing a planar reflector. "
            "Produces a direct Line of Sight (LOS) ray and a single Specular Reflection ray."
        ),
        "is_default": True,
    }
}


def create_mcp_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    streamable_http_path: str = "/mcp",
) -> FastMCP:
    """Create and configure the Sionna RT MCP server with registered tools."""
    try:
        server = FastMCP(
            name="sionna-rt-mcp",
            instructions=(
                "NVIDIA Sionna RT Radio Ray-Tracing Simulator MCP Server. "
                "Provides tools to verify simulator availability, discover geometric "
                "scenes, execute point-to-point physical 3D simulations, generate 2D spatial "
                "radio coverage maps, persist simulation experiments, and perform comparative "
                "evaluations with spatial difference heatmaps."
            ),
        )
    except TypeError:
        server = FastMCP(
            name="sionna-rt-mcp",
            instructions=(
                "NVIDIA Sionna RT Radio Ray-Tracing Simulator MCP Server. "
                "Provides tools to verify simulator availability, discover geometric "
                "scenes, execute point-to-point physical 3D simulations, generate 2D spatial "
                "radio coverage maps, persist simulation experiments, and perform comparative "
                "evaluations with spatial difference heatmaps."
            ),
            host=host,
            port=port,
            streamable_http_path=streamable_http_path,
        )

    if hasattr(server, "settings"):
        try:
            server.settings.__class__.__setattr__ = object.__setattr__
        except Exception:
            pass
        try:
            object.__setattr__(server.settings, "host", host)
            object.__setattr__(server.settings, "port", port)
            object.__setattr__(server.settings, "streamable_http_path", streamable_http_path)
        except Exception:
            pass

    orig_run = server.run

    def _run_with_defaults(transport: str = "stdio", **kwargs: Any) -> None:
        if transport in ("streamable-http", "sse"):
            kwargs.setdefault("host", getattr(server.settings, "host", host))
            kwargs.setdefault("port", getattr(server.settings, "port", port))
            kwargs.setdefault("streamable_http_path", getattr(server.settings, "streamable_http_path", streamable_http_path))
        return orig_run(transport=transport, **kwargs)

    server.run = _run_with_defaults

    # =========================================================================
    # 1. Point-to-Point Tools (Existing)
    # =========================================================================

    @server.tool()
    def check_environment() -> Dict[str, Any]:
        """Check whether the Sionna RT simulation environment is configured and usable.

        Use this tool before running simulations if you need to confirm simulator
        availability, verify software versions, or check which Mitsuba computational
        backend (GPU CUDA/OptiX or CPU LLVM fallback) is active.

        Returns:
            dict: Structured environment health report containing:
                - python_version (str): Python runtime version (e.g. '3.11.15').
                - sionna_version (str): Version of sionna-rt installed.
                - mitsuba_version (str): Version of mitsuba installed.
                - backend (str): Active computational backend (e.g. 'llvm_ad_mono_polarized').
                - is_usable (bool): True if simulation engine is ready to execute.
        """
        # 1. Probe and verify backend engine readiness first
        try:
            engine = SimulationEngine()
            backend = engine.backend
            is_usable = True
        except Exception as e:
            logger.error("Environment verification failed: %s", e, exc_info=True)
            backend = "unavailable"
            is_usable = False

        # 2. Inspect software component versions
        try:
            import sionna.rt as rt
            sionna_version = getattr(rt, "__version__", "unknown")
        except ImportError:
            sionna_version = "not installed"

        try:
            import mitsuba as mi
            mitsuba_version = getattr(mi, "__version__", "unknown")
        except ImportError:
            mitsuba_version = "not installed"

        return {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "sionna_version": sionna_version,
            "mitsuba_version": mitsuba_version,
            "backend": backend,
            "is_usable": is_usable,
        }

    @server.tool()
    def list_scenes() -> Dict[str, Any]:
        """Return 3D geometric scenes available for Sionna RT ray-tracing simulations.

        Use this tool to discover valid scene names before configuring and executing
        a simulation.

        Returns:
            dict: Structured scene catalog containing:
                - scenes (list): List of available scene descriptors with name and details.
                - default_scene (str): The default scene identifier ('simple_reflector').
                - count (int): Total number of supported scenes.
        """
        scenes_list = [
            {
                "name": s["name"],
                "description": s["description"],
                "is_default": s["is_default"],
            }
            for s in SUPPORTED_SCENES.values()
        ]

        return {
            "scenes": scenes_list,
            "default_scene": "simple_reflector",
            "count": len(scenes_list),
        }

    @server.tool()
    def run_simulation(
        scene: Annotated[
            str,
            Field(
                description=(
                    "Identifier of the 3D geometric scene to simulate (e.g. 'simple_reflector'). "
                    "Use list_scenes to see all supported scenes."
                )
            ),
        ] = "simple_reflector",
        frequency_hz: Annotated[
            float,
            Field(
                description=(
                    "Carrier frequency in Hertz (Hz). For example, 3.5e9 represents 3.5 GHz "
                    "(3,500,000,000 Hz). Note: parameter is in Hz, NOT GHz. Must be strictly positive (> 0 Hz)."
                )
            ),
        ] = 3.5e9,
        tx_position: Annotated[
            List[float],
            Field(
                description=(
                    "Transmitter Cartesian 3D coordinates [x, y, z] in meters. "
                    "Must be a list of exactly 3 numeric coordinates, e.g. [0.0, -10.0, 5.0]."
                )
            ),
        ] = [0.0, -10.0, 5.0],
        rx_position: Annotated[
            List[float],
            Field(
                description=(
                    "Receiver Cartesian 3D coordinates [x, y, z] in meters. "
                    "Must be a list of exactly 3 numeric coordinates, e.g. [0.0, 10.0, 5.0]."
                )
            ),
        ] = [0.0, 10.0, 5.0],
        tx_power_dbm: Annotated[
            float,
            Field(
                description=(
                    "Transmitter output power in decibel-milliwatts (dBm). "
                    "For example, 30.0 dBm represents 1.0 Watt of RF power."
                )
            ),
        ] = 30.0,
        antenna_type: Annotated[
            str,
            Field(
                description=(
                    "Antenna radiation pattern: 'isotropic', 'dipole', or 'directional' (default: 'isotropic')."
                )
            ),
        ] = "isotropic",
        polarization: Annotated[
            str,
            Field(
                description="Antenna polarization: 'V', 'H', 'VH', or 'cross' (default: 'V')."
            ),
        ] = "V",
        num_rows: Annotated[
            int,
            Field(description="Number of antenna array rows (>= 1, default: 1)."),
        ] = 1,
        num_cols: Annotated[
            int,
            Field(description="Number of antenna array columns (>= 1, default: 1)."),
        ] = 1,
        horizontal_spacing: Annotated[
            float,
            Field(description="Horizontal antenna spacing in carrier wavelengths (default: 0.5)."),
        ] = 0.5,
        vertical_spacing: Annotated[
            float,
            Field(description="Vertical antenna spacing in carrier wavelengths (default: 0.5)."),
        ] = 0.5,
        max_depth: Annotated[
            int,
            Field(description="Maximum ray bounce depth (>= 1, default: 2)."),
        ] = 2,
        tx_antenna_type: Annotated[
            Optional[str],
            Field(
                description=(
                    "Optional dedicated TX antenna pattern ('isotropic', 'dipole', or 'directional'). "
                    "Overrides antenna_type for TX."
                )
            ),
        ] = None,
        rx_antenna_type: Annotated[
            Optional[str],
            Field(
                description=(
                    "Optional dedicated RX antenna pattern ('isotropic', 'dipole', or 'directional'). "
                    "Overrides antenna_type for RX."
                )
            ),
        ] = None,
        tx_orientation_deg: Annotated[
            Optional[List[float]],
            Field(
                description="Transmitter orientation [yaw, pitch, roll] in degrees (default: facing receiver)."
            ),
        ] = None,
        rx_orientation_deg: Annotated[
            Optional[List[float]],
            Field(
                description="Receiver orientation [yaw, pitch, roll] in degrees."
            ),
        ] = None,
    ) -> Dict[str, Any]:
        """Run an NVIDIA Sionna RT ray-tracing simulation and return physical propagation metrics.

        Executes physical 3D electromagnetic ray-tracing between a radio transmitter (TX)
        and receiver (RX) in the specified geometric scene. Calculates multipath propagation
        delays, path distances, power gains, total path loss, and received power.

        Use this tool when you need genuine radio propagation metrics for wireless network
        analysis, coverage verification, or channel modeling.

        Args:
            scene: Geometric scene identifier (default: 'simple_reflector').
            frequency_hz: Radio carrier frequency in Hertz (Hz, NOT GHz). Must be > 0.
            tx_position: 3D coordinates [x, y, z] of transmitter in meters.
            rx_position: 3D coordinates [x, y, z] of receiver in meters.
            tx_power_dbm: Transmit power in dBm (default: 30.0 dBm = 1 Watt).

        Returns:
            dict: Structured propagation results containing:
                - frequency_hz (float): Carrier frequency in Hz.
                - tx_position (list): Transmitter coordinates [x, y, z] in meters.
                - rx_position (list): Receiver coordinates [x, y, z] in meters.
                - tx_power_dbm (float): Transmit power in dBm.
                - backend (str): Mitsuba computational backend used.
                - num_paths (int): Total number of resolved propagation paths.
                - total_path_loss (float): Combined channel path loss in dB.
                - received_power (float): Total received power at RX in dBm.
                - path_delays (list): Time-of-flight delays for each path in nanoseconds.
                - path_distances (list): Physical propagation distance for each path in meters.
                - path_gains (list): Individual power gain for each path in dB.
                - interaction_types (list): Physical interaction along each path (e.g. 'Line of Sight', 'Specular Reflection').
        """
        # 1. Validate scene
        if not isinstance(scene, str) or not scene.strip():
            raise ToolError("Scene name must be a non-empty string.")
        scene_key = scene.strip()
        if scene_key not in SUPPORTED_SCENES:
            available = ", ".join(sorted(SUPPORTED_SCENES.keys()))
            raise ToolError(f"Scene '{scene}' is not available. Available scenes: {available}")

        # 2. Validate frequency
        try:
            freq = float(frequency_hz)
        except (TypeError, ValueError):
            raise ToolError("Frequency must be greater than 0 Hz.")
        if freq <= 0 or math.isnan(freq) or math.isinf(freq):
            raise ToolError("Frequency must be greater than 0 Hz.")

        # 3. Validate transmitter position
        if not isinstance(tx_position, (list, tuple)) or len(tx_position) != 3:
            raise ToolError("Position must contain exactly 3 numeric coordinates [x, y, z].")
        for coord in tx_position:
            if not isinstance(coord, (int, float)) or math.isnan(coord) or math.isinf(coord):
                raise ToolError("Position must contain exactly 3 numeric coordinates [x, y, z].")

        # 4. Validate receiver position
        if not isinstance(rx_position, (list, tuple)) or len(rx_position) != 3:
            raise ToolError("Position must contain exactly 3 numeric coordinates [x, y, z].")
        for coord in rx_position:
            if not isinstance(coord, (int, float)) or math.isnan(coord) or math.isinf(coord):
                raise ToolError("Position must contain exactly 3 numeric coordinates [x, y, z].")

        # 5. Validate transmitter power
        try:
            power = float(tx_power_dbm)
            if math.isnan(power) or math.isinf(power):
                raise ValueError
        except (TypeError, ValueError):
            raise ToolError("Transmitter power must be a numeric value in dBm.")

        # 6. Validate antenna parameters
        norm_ant = str(antenna_type).strip().lower()
        if norm_ant not in ("isotropic", "iso", "omni", "omnidirectional", "dipole", "hw_dipole", "directional", "tr38901"):
            raise ToolError(
                f"Unsupported antenna type '{antenna_type}'. Supported antenna types: 'isotropic', 'dipole', 'directional'."
            )

        if tx_antenna_type is not None:
            norm_tx_ant = str(tx_antenna_type).strip().lower()
            if norm_tx_ant not in ("isotropic", "iso", "omni", "omnidirectional", "dipole", "hw_dipole", "directional", "tr38901"):
                raise ToolError(
                    f"Unsupported TX antenna type '{tx_antenna_type}'. Supported antenna types: 'isotropic', 'dipole', 'directional'."
                )

        if rx_antenna_type is not None:
            norm_rx_ant = str(rx_antenna_type).strip().lower()
            if norm_rx_ant not in ("isotropic", "iso", "omni", "omnidirectional", "dipole", "hw_dipole", "directional", "tr38901"):
                raise ToolError(
                    f"Unsupported RX antenna type '{rx_antenna_type}'. Supported antenna types: 'isotropic', 'dipole', 'directional'."
                )

        norm_pol = str(polarization).strip().upper()
        if norm_pol not in ("V", "H", "VH", "CROSS"):
            raise ToolError(
                f"Unsupported antenna polarization '{polarization}'. Supported values: 'V', 'H', 'VH', 'cross'."
            )

        try:
            r_rows = int(num_rows)
            r_cols = int(num_cols)
            if r_rows < 1 or r_cols < 1:
                raise ValueError
        except (TypeError, ValueError):
            raise ToolError("Antenna array rows and columns must be integers >= 1.")

        try:
            h_spacing = float(horizontal_spacing)
            v_spacing = float(vertical_spacing)
            if h_spacing <= 0 or v_spacing <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ToolError("Horizontal and vertical element spacings must be numbers > 0.")

        # 7. Validate orientations if provided
        tx_orient = None
        if tx_orientation_deg is not None:
            if not isinstance(tx_orientation_deg, (list, tuple)) or len(tx_orientation_deg) != 3:
                raise ToolError("Transmitter orientation must contain exactly 3 angles [yaw, pitch, roll] in degrees.")
            for ang in tx_orientation_deg:
                if not isinstance(ang, (int, float)) or math.isnan(ang) or math.isinf(ang):
                    raise ToolError("Transmitter orientation angles must be numeric.")
            tx_orient = [float(a) for a in tx_orientation_deg]

        rx_orient = None
        if rx_orientation_deg is not None:
            if not isinstance(rx_orientation_deg, (list, tuple)) or len(rx_orientation_deg) != 3:
                raise ToolError("Receiver orientation must contain exactly 3 angles [yaw, pitch, roll] in degrees.")
            for ang in rx_orientation_deg:
                if not isinstance(ang, (int, float)) or math.isnan(ang) or math.isinf(ang):
                    raise ToolError("Receiver orientation angles must be numeric.")
            rx_orient = [float(a) for a in rx_orientation_deg]

        # 8. Execute simulation via SimulationEngine (no duplicated ray-tracing logic)
        try:
            config = SimulationConfig(
                scene=scene_key,
                frequency=freq,
                tx_position=[float(x) for x in tx_position],
                rx_position=[float(x) for x in rx_position],
                tx_power_dbm=power,
                antenna_type=norm_ant,
                polarization=polarization,
                num_rows=r_rows,
                num_cols=r_cols,
                horizontal_spacing=h_spacing,
                vertical_spacing=v_spacing,
                max_depth=int(max_depth) if max_depth and int(max_depth) >= 1 else 2,
                tx_antenna_type=tx_antenna_type,
                rx_antenna_type=rx_antenna_type,
                tx_orientation_deg=tx_orient,
                rx_orientation_deg=rx_orient,
            )
            engine = SimulationEngine(config)
            result = engine.run()
            return result.to_dict()
        except Exception as e:
            logger.error("Simulation execution failure: %s", e, exc_info=True)
            raise ToolError(f"Simulation execution failed: {str(e)}")

    # =========================================================================
    # 2. Radio Map & Experiment Management Tools (Phases 2-6 Integration)
    # =========================================================================

    @server.tool()
    def generate_radio_map(
        scene_name: Annotated[
            str,
            Field(description="Geometric scene identifier (e.g. 'simple_reflector' or 'munich')."),
        ] = "simple_reflector",
        frequency_hz: Annotated[
            float,
            Field(description="Carrier frequency in Hertz (Hz). Must be > 0 Hz (e.g. 3.5e9 for 3.5 GHz)."),
        ] = 3.5e9,
        tx_name: Annotated[
            str,
            Field(description="Transmitter name/label in the scene."),
        ] = "tx",
        tx_position: Annotated[
            List[float],
            Field(description="Transmitter Cartesian 3D coordinates [x, y, z] in meters."),
        ] = [0.0, -10.0, 5.0],
        tx_power_dbm: Annotated[
            float,
            Field(description="Transmitter output power in dBm (e.g. 30.0 dBm = 1.0 Watt)."),
        ] = 30.0,
        tx_orientation_deg: Annotated[
            List[float],
            Field(description="Transmitter orientation [yaw, pitch, roll] in degrees."),
        ] = [0.0, 0.0, 0.0],
        antenna_type: Annotated[
            str,
            Field(description="Antenna radiation pattern: 'isotropic', 'dipole', or 'directional'."),
        ] = "isotropic",
        polarization: Annotated[
            str,
            Field(description="Antenna polarization: 'V', 'H', 'VH', or 'cross'."),
        ] = "V",
        num_rows: Annotated[
            int,
            Field(description="Number of antenna array rows (>= 1)."),
        ] = 1,
        num_cols: Annotated[
            int,
            Field(description="Number of antenna array columns (>= 1)."),
        ] = 1,
        horizontal_spacing: Annotated[
            float,
            Field(description="Horizontal antenna element spacing in carrier wavelengths (lambda)."),
        ] = 0.5,
        vertical_spacing: Annotated[
            float,
            Field(description="Vertical antenna element spacing in carrier wavelengths (lambda)."),
        ] = 0.5,
        region_mode: Annotated[
            str,
            Field(description="Measurement region bounding mode: 'auto' (derived from scene) or 'manual'."),
        ] = "auto",
        auto_margin: Annotated[
            float,
            Field(description="Buffer margin in meters added to scene bounds in auto mode."),
        ] = 5.0,
        auto_include_tx: Annotated[
            bool,
            Field(description="Whether to expand auto bounds to enclose the transmitter position."),
        ] = True,
        x_min: Annotated[
            Optional[float],
            Field(description="Minimum X coordinate in meters (required if region_mode is 'manual')."),
        ] = None,
        x_max: Annotated[
            Optional[float],
            Field(description="Maximum X coordinate in meters (required if region_mode is 'manual')."),
        ] = None,
        y_min: Annotated[
            Optional[float],
            Field(description="Minimum Y coordinate in meters (required if region_mode is 'manual')."),
        ] = None,
        y_max: Annotated[
            Optional[float],
            Field(description="Maximum Y coordinate in meters (required if region_mode is 'manual')."),
        ] = None,
        receiver_height: Annotated[
            float,
            Field(description="Measurement plane height (Z) in meters."),
        ] = 1.5,
        cell_size: Annotated[
            Union[float, List[float]],
            Field(description="Grid cell resolution in meters: scalar (e.g. 1.0) or [dx, dy]."),
        ] = 1.0,
        samples_per_tx: Annotated[
            int,
            Field(description="Monte Carlo ray budget per transmitter."),
        ] = 1_000_000,
        max_depth: Annotated[
            int,
            Field(description="Maximum ray bounce depth."),
        ] = 3,
        seed: Annotated[
            Optional[int],
            Field(description="Random seed for reproducible ray tracing."),
        ] = None,
        los: Annotated[
            bool,
            Field(description="Enable Line of Sight (LOS) propagation rays."),
        ] = True,
        specular_reflection: Annotated[
            bool,
            Field(description="Enable specular reflection rays."),
        ] = True,
        diffraction: Annotated[
            bool,
            Field(description="Enable edge diffraction rays."),
        ] = True,
        scattering: Annotated[
            bool,
            Field(description="Enable diffuse scattering rays."),
        ] = False,
        experiment_name: Annotated[
            Optional[str],
            Field(description="Optional human-readable label for saving this experiment."),
        ] = None,
    ) -> Dict[str, Any]:
        """Generate a 2D spatial radio coverage map and persist the experiment.

        Executes Sionna RT's RadioMapSolver over a horizontal evaluation plane at receiver_height,
        extracts numerical field matrices (linear and dB received power and path gain), renders
        publication-quality Received Signal Strength (RSS) and Path Gain heatmaps, and persists
        the complete experiment (numerical arrays and metadata) via ExperimentStore.

        Returns:
            dict: Structured summary including experiment ID, spatial grid metrics,
                  coverage statistics, and saved heatmap artifact paths.
        """
        # 1. Normalize container types for RadioMapConfig
        if isinstance(tx_position, (list, tuple)):
            if len(tx_position) != 3:
                raise ToolError("tx_position must contain exactly 3 coordinates [x, y, z].")
            tx_pos_tuple = (float(tx_position[0]), float(tx_position[1]), float(tx_position[2]))
        else:
            raise ToolError("tx_position must be a list or tuple of 3 numbers.")

        if isinstance(tx_orientation_deg, (list, tuple)):
            if len(tx_orientation_deg) != 3:
                raise ToolError("tx_orientation_deg must contain exactly 3 angles [yaw, pitch, roll].")
            tx_orient_tuple = (
                float(tx_orientation_deg[0]),
                float(tx_orientation_deg[1]),
                float(tx_orientation_deg[2]),
            )
        else:
            raise ToolError("tx_orientation_deg must be a list or tuple of 3 numbers.")

        if isinstance(cell_size, (list, tuple)):
            if len(cell_size) != 2:
                raise ToolError("cell_size as a sequence must contain exactly 2 numbers [dx, dy].")
            cell_size_val: Union[float, Tuple[float, float]] = (float(cell_size[0]), float(cell_size[1]))
        else:
            try:
                cell_size_val = float(cell_size)
            except (TypeError, ValueError):
                raise ToolError("cell_size must be a positive number or [dx, dy] pair.")

        # 2. Build and validate RadioMapConfig
        try:
            config = RadioMapConfig(
                scene_name=str(scene_name),
                frequency_hz=float(frequency_hz),
                tx_name=str(tx_name),
                tx_position=tx_pos_tuple,
                tx_power_dbm=float(tx_power_dbm),
                tx_orientation_deg=tx_orient_tuple,
                antenna_type=str(antenna_type),
                polarization=str(polarization),
                num_rows=int(num_rows),
                num_cols=int(num_cols),
                horizontal_spacing=float(horizontal_spacing),
                vertical_spacing=float(vertical_spacing),
                region_mode=str(region_mode),
                auto_margin=float(auto_margin),
                auto_include_tx=bool(auto_include_tx),
                x_min=float(x_min) if x_min is not None else None,
                x_max=float(x_max) if x_max is not None else None,
                y_min=float(y_min) if y_min is not None else None,
                y_max=float(y_max) if y_max is not None else None,
                receiver_height=float(receiver_height),
                cell_size=cell_size_val,
                samples_per_tx=int(samples_per_tx),
                max_depth=int(max_depth),
                seed=int(seed) if seed is not None else None,
                los=bool(los),
                specular_reflection=bool(specular_reflection),
                diffraction=bool(diffraction),
                scattering=bool(scattering),
            )
        except Exception as exc:
            logger.error("RadioMapConfig validation failed: %s", exc, exc_info=True)
            raise ToolError(f"Invalid radio map configuration: {exc}")

        # 3. Execute ray-tracing simulation via RadioMapEngine
        try:
            engine = RadioMapEngine(config)
            raw_result = engine.run()
        except Exception as exc:
            logger.error("Radio map simulation execution failure: %s", exc, exc_info=True)
            raise ToolError(f"Radio map simulation execution failed: {exc}")

        # 4. Extract numerical data via RadioMapResult
        try:
            result = RadioMapResult.from_raw_radio_map(
                raw_radio_map=raw_result,
                config=config,
                backend_variant=engine.backend,
                region_bounds=engine.last_bounds,
            )
        except Exception as exc:
            logger.error("Result extraction failure: %s", exc, exc_info=True)
            raise ToolError(f"Failed to extract radio map numerical results: {exc}")

        # 5. Generate heatmaps if visualization dependency is available
        heatmap_paths = None
        temp_vis_dir = None
        if RadioMapFormatter.is_visualization_available():
            try:
                temp_vis_dir = tempfile.mkdtemp(prefix=".tmp_vis_")
                heatmap_paths = RadioMapFormatter.generate_heatmaps(
                    result=result,
                    output_dir=temp_vis_dir,
                    prefix="radio_map",
                )
            except Exception as exc:
                logger.warning("Heatmap visualization failed: %s", exc)
                heatmap_paths = None

        # 6. Save experiment atomically via ExperimentStore
        try:
            store = ExperimentStore()
            exp_id = store.save_experiment(
                result=result,
                heatmap_paths=heatmap_paths,
                experiment_name=experiment_name,
            )
        except Exception as exc:
            logger.error("Experiment storage failure: %s", exc, exc_info=True)
            raise ToolError(f"Failed to persist experiment: {exc}")
        finally:
            if temp_vis_dir and os.path.exists(temp_vis_dir):
                shutil.rmtree(temp_vis_dir, ignore_errors=True)

        # 7. Query stored details to return exact artifact paths and metadata
        try:
            details = store.get_experiment_details(exp_id)
        except Exception:
            details = {}

        return {
            "status": "success",
            "experiment_id": exp_id,
            "experiment_name": experiment_name,
            "scene_name": config.scene_name,
            "frequency_hz": config.frequency_hz,
            "tx_position": list(config.tx_position),
            "tx_power_dbm": config.tx_power_dbm,
            "tx_orientation_deg": list(config.tx_orientation_deg),
            "antenna_type": config.antenna_type,
            "polarization": config.polarization,
            "measurement_height": float(result.measurement_height),
            "grid_dimensions": list(result.grid_dimensions),
            "cell_size": list(result.cell_size),
            "region_bounds": list(result.region_bounds),
            "total_cells": result.num_cells,
            "valid_cells": result.valid_cells_count,
            "zero_power_cells": result.zero_power_cells_count,
            "coverage_percentage": float(result.coverage_percentage),
            "min_rss_dbm": result.min_rss_dbm,
            "mean_rss_dbm": result.mean_rss_dbm,
            "max_rss_dbm": result.max_rss_dbm,
            "heatmaps_available": details.get("heatmaps_available", {}),
            "artifact_paths": details.get("artifact_paths", {}),
            "simulation_timestamp": result.simulation_timestamp,
            "backend_variant": result.backend_variant,
        }

    @server.tool()
    def list_experiments() -> Dict[str, Any]:
        """Retrieve lightweight summaries of previously saved radio-map simulation experiments.

        Lists all stored experiments with their identifier, scene name, carrier frequency,
        transmitter configuration, measurement plane height, grid dimensions, coverage
        metrics, and heatmap availability. Large numerical matrices are not loaded.

        Returns:
            dict: Catalog containing:
                - status (str): 'success'.
                - experiments (list): List of experiment summary dictionaries.
                - count (int): Total number of stored experiments.
        """
        try:
            store = ExperimentStore()
            experiments = store.list_experiments()
            return {
                "status": "success",
                "experiments": experiments,
                "count": len(experiments),
            }
        except Exception as exc:
            logger.error("Failed to list experiments: %s", exc, exc_info=True)
            raise ToolError(f"Failed to list experiments: {exc}")

    @server.tool()
    def get_experiment_details(
        experiment_id: Annotated[
            str,
            Field(description="Unique experiment identifier (e.g. 'experiment_20261101_120000_12345678')."),
        ],
    ) -> Dict[str, Any]:
        """Retrieve configuration metadata and numerical summaries for a saved experiment.

        Returns simulation parameters, antenna and grid specifications, coverage metrics,
        array dimensions, and absolute paths to saved heatmap PNG artifacts without
        loading large numerical matrices into memory.

        Args:
            experiment_id: Unique identifier of the target experiment.

        Returns:
            dict: Structured metadata and artifact information.
        """
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise ToolError("experiment_id must be a non-empty string.")

        try:
            store = ExperimentStore()
            details = store.get_experiment_details(experiment_id.strip())
            return {
                "status": "success",
                **details,
            }
        except FileNotFoundError as exc:
            raise ToolError(f"Experiment '{experiment_id}' not found: {exc}")
        except ValueError as exc:
            raise ToolError(f"Invalid experiment or corrupted metadata: {exc}")
        except Exception as exc:
            logger.error("Failed to retrieve experiment details: %s", exc, exc_info=True)
            raise ToolError(f"Failed to retrieve experiment details: {exc}")

    @server.tool()
    def compare_experiments(
        experiment_id_a: Annotated[
            str,
            Field(description="Identifier of baseline/reference Experiment A."),
        ],
        experiment_id_b: Annotated[
            str,
            Field(description="Identifier of modified/new Experiment B."),
        ],
        generate_heatmaps: Annotated[
            bool,
            Field(description="Whether to generate diverging difference heatmap PNG images."),
        ] = True,
        generate_heatmap: Annotated[
            Optional[bool],
            Field(description="Alias for generate_heatmaps."),
        ] = None,
    ) -> Dict[str, Any]:
        """Compare two saved radio-map experiments and calculate spatial differences (B - A).

        Computes received power difference (delta_rss_dbm = RSS_B - RSS_A) and path gain
        difference (delta_path_gain_db = Gain_B - Gain_A) across matching spatial grid cells.
        Enforces spatial compatibility: scene name, measurement height, grid dimensions,
        cell size, and bounding coordinates must match within tolerance.

        Interpretation:
            - Positive (> 0 dB): Experiment B has stronger received power / higher gain.
            - Negative (< 0 dB): Experiment B has weaker received power / lower gain.
            - Zero (== 0 dB): Both experiments have identical power / gain.

        Args:
            experiment_id_a: Baseline experiment identifier.
            experiment_id_b: Modified experiment identifier.
            generate_heatmaps: Whether to render and save difference heatmaps.

        Returns:
            dict: Structured comparison result including difference convention,
                  summary metrics, and generated heatmap artifact paths.
        """
        if not isinstance(experiment_id_a, str) or not experiment_id_a.strip():
            raise ToolError("experiment_id_a must be a non-empty string.")
        if not isinstance(experiment_id_b, str) or not experiment_id_b.strip():
            raise ToolError("experiment_id_b must be a non-empty string.")

        try:
            store = ExperimentStore()
            comparator = ExperimentComparator(experiment_store=store)
            do_generate = generate_heatmaps if generate_heatmap is None else generate_heatmap
            comp = comparator.compare_experiments(
                experiment_a_id=experiment_id_a.strip(),
                experiment_b_id=experiment_id_b.strip(),
                generate_heatmaps=bool(do_generate),
            )

            return {
                "status": "success",
                "difference_convention": comp.difference_convention,
                "experiment_a_id": comp.experiment_a_id,
                "experiment_b_id": comp.experiment_b_id,
                "scene_name": comp.scene_name,
                "measurement_height": comp.measurement_height,
                "frequency_a_hz": comp.frequency_a_hz,
                "frequency_b_hz": comp.frequency_b_hz,
                "frequency_match": comp.frequency_match,
                "grid_dimensions": list(comp.grid_dimensions),
                "cell_size": list(comp.cell_size),
                "region_bounds": list(comp.region_bounds),
                "total_cells": comp.rss_metrics["total_cells"],
                "valid_cells": comp.rss_metrics["valid_cells"],
                "invalid_cells": comp.rss_metrics["invalid_cells"],
                "valid_cells_percentage": comp.rss_metrics["valid_cells_percentage"],
                "rss_difference_metrics": comp.rss_metrics,
                "path_gain_difference_metrics": comp.path_gain_metrics,
                "heatmaps": comp.heatmap_paths,
                "artifacts": comp.heatmap_paths,
                "heatmaps_available": comp.heatmaps_available,
                "comparison_timestamp": comp.comparison_timestamp,
            }
        except FileNotFoundError as exc:
            raise ToolError(f"Experiment not found: {exc}")
        except ValueError as exc:
            # Spatial mismatch or invalid ID
            raise ToolError(f"Comparison failed: {exc}")
        except Exception as exc:
            logger.error("Experiment comparison failed: %s", exc, exc_info=True)
            raise ToolError(f"Experiment comparison failed: {exc}")

    # Compatibility mapping for tool introspection across SDK variants
    if hasattr(server, "_tool_manager") and hasattr(server._tool_manager, "_tools"):
        server._tools = {
            name: {"func": tool_obj.fn, "name": name}
            for name, tool_obj in server._tool_manager._tools.items()
        }

    return server


# Server instance for script execution or programmatic import
mcp = create_mcp_server()


def main() -> None:
    """Run MCP server. Defaults to stdio transport, supports --transport option."""
    import argparse
    parser = argparse.ArgumentParser(description="Run Sionna RT MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Transport protocol to use (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host address for HTTP transport (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP transport (default: 8000)")
    args, _ = parser.parse_known_args()

    if args.transport in ("streamable-http", "sse"):
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        print(
            f"Starting Sionna RT MCP server on http://{args.host}:{args.port}/mcp ({args.transport})",
            file=sys.stderr,
        )
        mcp.run(transport=args.transport)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
