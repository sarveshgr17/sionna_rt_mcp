"""Simulation result storage and retrieval manager."""

from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, List, Optional
import uuid

try:
    from src.analyzer import AnalysisResult
    from src.config import SimulationConfig
    from src.result import SimulationResult
except ImportError:
    from analyzer import AnalysisResult
    from config import SimulationConfig
    from result import SimulationResult


class SimulationStorage:
    """Manages persistent on-disk storage of simulation configurations and metrics."""

    def __init__(self, base_dir: str = "results") -> None:
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def generate_simulation_id(self) -> str:
        """Generate a unique, predictable, timestamped simulation identifier."""
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_suffix = uuid.uuid4().hex[:6]
        return f"sim_{now_str}_{short_suffix}"

    def get_simulation_dir(self, simulation_id: str) -> str:
        """Return the directory path for a specific simulation."""
        return os.path.join(self.base_dir, simulation_id)

    def exists(self, simulation_id: str) -> bool:
        """Check whether a simulation directory with valid metrics exists."""
        if not simulation_id or not isinstance(simulation_id, str):
            return False
        sim_dir = self.get_simulation_dir(simulation_id)
        metrics_file = os.path.join(sim_dir, "metrics.json")
        return os.path.isdir(sim_dir) and os.path.isfile(metrics_file)

    def save(
        self,
        config: SimulationConfig,
        result: SimulationResult,
        analysis: Optional[AnalysisResult] = None,
        simulation_id: Optional[str] = None,
    ) -> str:
        """Save simulation configuration and output metrics to disk.

        Args:
            config: SimulationConfig instance.
            result: SimulationResult instance.
            analysis: Optional AnalysisResult instance.
            simulation_id: Optional custom simulation ID (auto-generated if None).

        Returns:
            str: The unique simulation ID used for storage.
        """
        sim_id = simulation_id or self.generate_simulation_id()
        sim_dir = self.get_simulation_dir(sim_id)
        os.makedirs(sim_dir, exist_ok=True)

        # 1. Save config.json
        config_path = os.path.join(sim_dir, "config.json")
        config_data = config.to_dict() if hasattr(config, "to_dict") else vars(config)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        # 2. Save metrics.json
        metrics_path = os.path.join(sim_dir, "metrics.json")
        metrics_data: Dict[str, Any] = {
            "simulation_id": sim_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "simulation": result.to_dict(),
            "analysis": analysis.to_dict() if analysis else None,
        }
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics_data, f, indent=2)

        return sim_id

    def load(self, simulation_id: str) -> Dict[str, Any]:
        """Load stored simulation configuration and metrics.

        Args:
            simulation_id: The ID of the simulation to load.

        Returns:
            dict containing 'simulation_id', 'config', 'metrics', and 'dir'.

        Raises:
            FileNotFoundError: If the simulation ID directory or metrics.json does not exist.
        """
        if not simulation_id or not isinstance(simulation_id, str):
            raise FileNotFoundError(f"Invalid simulation ID: {simulation_id}")
        sim_dir = self.get_simulation_dir(simulation_id)
        if not os.path.isdir(sim_dir):
            raise FileNotFoundError(f"Simulation '{simulation_id}' not found in '{self.base_dir}'.")

        metrics_path = os.path.join(sim_dir, "metrics.json")
        if not os.path.isfile(metrics_path):
            raise FileNotFoundError(f"Simulation metrics missing for '{simulation_id}'.")

        with open(metrics_path, "r", encoding="utf-8") as f:
            metrics_data = json.load(f)

        config_path = os.path.join(sim_dir, "config.json")
        config_data = {}
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)

        return {
            "simulation_id": simulation_id,
            "dir": sim_dir,
            "config": config_data,
            "metrics": metrics_data,
            "simulation": metrics_data.get("simulation", {}),
            "analysis": metrics_data.get("analysis"),
        }

    def list_simulations(self) -> List[str]:
        """List all available simulation IDs stored on disk in chronological order."""
        if not os.path.exists(self.base_dir):
            return []
        items = os.listdir(self.base_dir)
        sim_ids = [
            item
            for item in items
            if os.path.isdir(os.path.join(self.base_dir, item))
            and os.path.isfile(os.path.join(self.base_dir, item, "metrics.json"))
        ]
        return sorted(sim_ids)
