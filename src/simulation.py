"""Simulation script entrypoint and backward-compatibility interface.

This module provides:
1. Command-line execution: python src/simulation.py
2. Backward-compatible functional interface: run_simulation() and format_results()
3. Direct exports of SimulationConfig, SimulationEngine, SimulationResult
"""

import os
import sys
from typing import Optional

# Ensure repository root is on sys.path when running as a standalone script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from src.config import SimulationConfig
    from src.engine import SimulationEngine
    from src.formatter import format_result, format_results
    from src.result import SimulationResult
except ImportError:
    from config import SimulationConfig
    from engine import SimulationEngine
    from formatter import format_result, format_results
    from result import SimulationResult


def run_simulation(config: Optional[SimulationConfig] = None) -> SimulationResult:
    """Run a Sionna RT simulation using SimulationEngine (backward-compatible)."""
    engine = SimulationEngine(config)
    return engine.run()


def main() -> int:
    """CLI execution entrypoint."""
    config = SimulationConfig()
    engine = SimulationEngine(config)
    result = engine.run()
    print(format_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
