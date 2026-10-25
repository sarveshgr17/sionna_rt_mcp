"""Unit tests for the minimal Sionna RT simulation."""

import pytest
from src.config import SimulationConfig
from src.simulation import SimulationResult, format_results, run_simulation


def test_simulation_runs_successfully():
    """Verify that run_simulation completes and returns a valid result."""
    config = SimulationConfig()
    result = run_simulation(config)

    assert isinstance(result, SimulationResult)
    assert result.scene_name == "simple_reflector"
    assert result.frequency_hz == 3.5e9
    assert result.num_paths >= 1


def test_propagation_results_validity():
    """Verify the physical plausibility of the extracted propagation metrics."""
    config = SimulationConfig()
    result = run_simulation(config)

    # Delays must be positive
    assert result.min_delay_ns > 0.0
    assert result.max_delay_ns >= result.min_delay_ns

    # Path loss must be positive and non-zero
    assert result.path_loss_db > 0.0

    # Received power formula: RX power = TX power - Path Loss
    expected_rx_power = config.tx_power_dbm - result.path_loss_db
    assert pytest.approx(result.rx_power_dbm, rel=1e-3) == expected_rx_power

    # Array lengths must match number of paths
    assert len(result.delays_ns) == result.num_paths
    assert len(result.path_gains_db) == result.num_paths
    assert len(result.interaction_types) == result.num_paths


def test_custom_frequency_and_power():
    """Verify simulation responds correctly to modified configuration."""
    # Test at 28 GHz mmWave frequency with 20 dBm TX power
    custom_config = SimulationConfig(
        frequency_hz=28.0e9,
        tx_power_dbm=20.0,
    )
    result = run_simulation(custom_config)

    assert result.frequency_hz == 28.0e9
    assert result.tx_power_dbm == 20.0
    assert result.num_paths >= 1
    # Higher frequency typically exhibits higher free-space path loss (Friis)
    # At 3.5 GHz path loss was ~66.8 dB; at 28 GHz it should be ~84.8 dB (20*log10(28/3.5) = 18 dB higher)
    assert result.path_loss_db > 75.0


def test_format_results_output():
    """Verify terminal formatting string includes required markers."""
    config = SimulationConfig()
    result = run_simulation(config)
    output = format_results(result)

    assert "Scene loaded: ✓" in output
    assert "Transmitter: ✓" in output
    assert "Receiver: ✓" in output
    assert "Frequency: 3.5 GHz ✓" in output
    assert "Ray tracing: ✓" in output
    assert "Propagation Results:" in output
