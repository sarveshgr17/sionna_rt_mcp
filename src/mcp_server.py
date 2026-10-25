"""Model Context Protocol (MCP) Server for NVIDIA Sionna RT.

This server provides an interface layer exposing the Sionna RT SimulationEngine,
ChannelAnalyzer, and Visualizer to MCP-compatible AI clients via stdio transport.

Supported Tools:
1. check_environment: Verify runtime simulator availability and backend.
2. list_scenes: List available 3D geometric propagation scenes.
3. run_simulation: Execute ray-tracing simulations and return raw physical metrics.
4. analyze_simulation: Run ray tracing AND perform physical channel analysis
   (strongest path, RMS delay spread, path contributions, LOS detection).
5. generate_visualization: Generate scientifically readable plots (propagation_paths,
   received_power, cir, comparison) for stored simulations.
"""

import logging
import math
import os
import sys
from typing import Annotated, Any, Dict, List, Optional, Tuple

from pydantic import Field

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Route all application diagnostics to stderr to prevent corrupting stdio MCP frames
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sionna_rt_mcp")

# Import MCP SDK (supporting both MCP 2.x MCPServer and MCP 1.x FastMCP)
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
    from mcp.server.mcpserver.exceptions import ToolError
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError

try:
    from src.analyzer import ChannelAnalyzer
    from src.config import SimulationConfig
    from src.engine import SimulationEngine
    from src.result import SimulationResult
    from src.storage import SimulationStorage
    from src.visualizer import Visualizer
except ImportError:
    from analyzer import ChannelAnalyzer
    from config import SimulationConfig
    from engine import SimulationEngine
    from result import SimulationResult
    from storage import SimulationStorage
    from visualizer import Visualizer

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


def _validate_and_run_simulation(
    scene: str,
    frequency_hz: float,
    tx_position: List[float],
    rx_position: List[float],
    tx_power_dbm: float,
) -> Tuple[SimulationConfig, SimulationResult]:
    """Validate user inputs and execute the simulation via SimulationEngine."""
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

    # 6. Execute simulation via SimulationEngine
    try:
        config = SimulationConfig(
            scene=scene_key,
            frequency=freq,
            tx_position=[float(x) for x in tx_position],
            rx_position=[float(x) for x in rx_position],
            tx_power_dbm=power,
        )
        engine = SimulationEngine(config)
        result = engine.run()
        return config, result
    except Exception as e:
        logger.error("Simulation execution failure: %s", e, exc_info=True)
        raise ToolError(f"Simulation execution failed: {str(e)}")


def create_mcp_server() -> FastMCP:
    """Create and configure the Sionna RT MCP server with registered tools."""
    server = FastMCP(
        name="sionna-rt-mcp",
        instructions=(
            "NVIDIA Sionna RT Radio Ray-Tracing Simulator MCP Server. "
            "Provides tools to verify simulator availability, discover geometric "
            "scenes, execute electromagnetic ray tracing, perform wireless channel analysis, "
            "and generate visualization plots."
        ),
    )

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
    ) -> Dict[str, Any]:
        """Run an NVIDIA Sionna RT ray-tracing simulation and return raw physical propagation metrics.

        Executes physical 3D electromagnetic ray-tracing between a radio transmitter (TX)
        and receiver (RX) in the specified geometric scene. Calculates multipath propagation
        delays, path distances, power gains, total path loss, and received power. Automatically
        saves configuration and metrics with a unique simulation ID.

        Args:
            scene: Geometric scene identifier (default: 'simple_reflector').
            frequency_hz: Radio carrier frequency in Hertz (Hz, NOT GHz). Must be > 0.
            tx_position: 3D coordinates [x, y, z] of transmitter in meters.
            rx_position: 3D coordinates [x, y, z] of receiver in meters.
            tx_power_dbm: Transmit power in dBm (default: 30.0 dBm = 1 Watt).

        Returns:
            dict: Structured propagation results including simulation_id, total_path_loss,
                  received_power, path_delays, path_distances, and path_gains.
        """
        config, result = _validate_and_run_simulation(
            scene=scene,
            frequency_hz=frequency_hz,
            tx_position=tx_position,
            rx_position=rx_position,
            tx_power_dbm=tx_power_dbm,
        )
        storage = SimulationStorage()
        sim_id = storage.save(config, result)

        res_dict = result.to_dict()
        res_dict["simulation_id"] = sim_id
        return res_dict

    @server.tool()
    def analyze_simulation(
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
    ) -> Dict[str, Any]:
        """Run a Sionna RT simulation AND perform comprehensive wireless channel analysis.

        Executes ray-tracing propagation between TX and RX, saves the simulation with a unique
        simulation ID, and analyzes channel characteristics:
        - Identifies the strongest (dominant) propagation path.
        - Computes the physically meaningful RMS delay spread (ns).
        - Calculates the relative percentage power contribution for every multipath component.
        - Detects whether a Line of Sight (LOS) path is present and reports its path index.

        Args:
            scene: Geometric scene identifier (default: 'simple_reflector').
            frequency_hz: Radio carrier frequency in Hertz (Hz, NOT GHz). Must be > 0.
            tx_position: 3D coordinates [x, y, z] of transmitter in meters.
            rx_position: 3D coordinates [x, y, z] of receiver in meters.
            tx_power_dbm: Transmit power in dBm (default: 30.0 dBm = 1 Watt).

        Returns:
            dict: Composite response containing:
                - simulation_id (str): Unique simulation ID for visualization and retrieval.
                - simulation (dict): Core ray-tracing metrics (paths, path loss, received power).
                - analysis (dict): Derived wireless channel metrics (strongest_path, LOS, RMS delay spread).
        """
        # 1. Run simulation via SimulationEngine
        config, sim_result = _validate_and_run_simulation(
            scene=scene,
            frequency_hz=frequency_hz,
            tx_position=tx_position,
            rx_position=rx_position,
            tx_power_dbm=tx_power_dbm,
        )

        # 2. Analyze simulation results via ChannelAnalyzer
        analyzer = ChannelAnalyzer()
        analysis_result = analyzer.analyze(sim_result)

        # 3. Store simulation result and analysis on disk
        storage = SimulationStorage()
        sim_id = storage.save(config, sim_result, analysis=analysis_result)

        # 4. Return composite simulation + analysis payload
        return {
            "simulation_id": sim_id,
            "simulation": sim_result.to_dict(),
            "analysis": analysis_result.to_dict(),
        }

    @server.tool()
    def generate_visualization(
        simulation_id: Annotated[
            str,
            Field(
                description=(
                    "Unique simulation identifier (e.g. 'sim_20261025_193000_a1b2c3') "
                    "returned by run_simulation or analyze_simulation."
                )
            ),
        ],
        plot_type: Annotated[
            str,
            Field(
                description=(
                    "Type of visualization to generate: 'all' (default), 'propagation_paths', "
                    "'received_power', 'cir' (channel impulse response), or 'comparison'."
                )
            ),
        ] = "all",
        comparison_simulation_id: Annotated[
            Optional[str],
            Field(
                description=(
                    "Optional second simulation identifier for scenario comparison plots "
                    "(required when plot_type='comparison')."
                )
            ),
        ] = None,
    ) -> Dict[str, Any]:
        """Generate scientifically readable visualization plots for a completed simulation.

        Renders publication-quality plots:
        - propagation_paths: 2D geometric multipath ray propagation from TX to RX.
        - received_power: Link power budget and attenuation waterfall.
        - cir: Channel Impulse Response stem plot showing delays and power gains.
        - comparison: Side-by-side comparison between two simulations (e.g. 3.5 GHz vs 28 GHz).

        Args:
            simulation_id: ID of the simulation to plot.
            plot_type: Plot to generate ('all', 'propagation_paths', 'received_power', 'cir', 'comparison').
            comparison_simulation_id: Second simulation ID if plot_type='comparison'.

        Returns:
            dict: List of generated plots with file paths on disk.
        """
        storage = SimulationStorage()

        # Validate existence of primary simulation ID
        if not storage.exists(simulation_id):
            raise ToolError(f"Simulation ID '{simulation_id}' not found in storage.")

        # Validate comparison simulation ID if required
        if plot_type == "comparison":
            if not comparison_simulation_id:
                raise ToolError("comparison_simulation_id is required when plot_type='comparison'.")
            if not storage.exists(comparison_simulation_id):
                raise ToolError(f"Comparison simulation ID '{comparison_simulation_id}' not found in storage.")

        visualizer = Visualizer(storage)
        try:
            plots = visualizer.generate_plots(
                simulation_id=simulation_id,
                plot_type=plot_type,
                comparison_simulation_id=comparison_simulation_id,
            )
            return {
                "simulation_id": simulation_id,
                "plot_type": plot_type,
                "generated_plots": plots,
            }
        except ValueError as e:
            raise ToolError(str(e))
        except Exception as e:
            logger.error("Visualization generation failed: %s", e, exc_info=True)
            raise ToolError(f"Visualization generation failed: {str(e)}")

    return server


# Server instance for script execution or programmatic import
mcp = create_mcp_server()


def main() -> None:
    """Run MCP server over standard input/output (stdio) transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
