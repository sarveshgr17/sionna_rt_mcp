"""Unit tests for the reusable SimulationEngine (Step 2)."""

import json
from src.config import SimulationConfig
from src.engine import SimulationEngine
from src.formatter import format_result
from src.result import SimulationResult


def test_simulation_engine_run_and_structured_result():
    """Verify SimulationEngine runs programmatically and returns core structured fields."""
    config = SimulationConfig(
        scene="simple_reflector",
        frequency=3.5e9,
        tx_position=[0, -10, 5],
        rx_position=[0, 10, 5],
        tx_power_dbm=30,
    )
    engine = SimulationEngine(config)
    result = engine.run()

    # 1. Engine runs and returns structured result
    assert isinstance(result, SimulationResult)

    # 2. Verify all core fields required by Step 2 specification
    assert result.frequency == 3.5e9
    assert result.tx_position == (0.0, -10.0, 5.0)
    assert result.rx_position == (0.0, 10.0, 5.0)
    assert result.number_of_paths >= 1
    assert result.num_paths >= 1
    assert len(result.path_delays) == result.num_paths
    assert len(result.path_distances) == result.num_paths
    assert len(result.path_gains) == result.num_paths
    assert result.total_path_loss > 0.0
    assert result.received_power == 30.0 - result.total_path_loss
    assert result.backend in ("llvm_ad_mono_polarized", "cuda_ad_mono_polarized")

    # 3. Easy to convert to JSON later
    result_dict = result.to_dict()
    assert isinstance(result_dict, dict)
    json_str = json.dumps(result_dict)
    assert isinstance(json_str, str)
    assert result_dict["frequency"] == 3.5e9
    assert result_dict["number_of_paths"] == result.num_paths
    assert len(result_dict["path_delays"]) == result.num_paths
    assert len(result_dict["path_distances"]) == result.num_paths


def test_engine_separate_formatting():
    """Verify engine output can be passed to the separate formatter."""
    config = SimulationConfig()
    engine = SimulationEngine(config)
    result = engine.run()

    # Engine result passed to standalone format_result function
    output = format_result(result)
    assert isinstance(output, str)
    assert "Scene loaded: ✓" in output
    assert "Propagation Results:" in output
    assert "Total Paths Found:" in output
    assert "Individual Path Breakdown:" in output
