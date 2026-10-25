"""Unit tests for the wireless ChannelAnalyzer (Step 4)."""

import math
import pytest

from src.analyzer import ChannelAnalyzer, AnalysisResult, StrongestPath, PathContribution
from src.result import SimulationResult


def make_mock_result(
    gains_db,
    delays_ns,
    distances_m,
    interaction_types,
    num_paths=None,
    scene_name="test_scene",
) -> SimulationResult:
    """Helper to create a deterministic SimulationResult for unit testing."""
    n = len(delays_ns) if num_paths is None else num_paths
    min_d = min(delays_ns) if delays_ns else 0.0
    max_d = max(delays_ns) if delays_ns else 0.0
    return SimulationResult(
        scene_name=scene_name,
        frequency_hz=3.5e9,
        tx_position=(0.0, -10.0, 5.0),
        tx_power_dbm=30.0,
        rx_position=(0.0, 10.0, 5.0),
        backend_variant="llvm_ad_mono_polarized",
        num_paths=n,
        path_loss_db=66.8,
        rx_power_dbm=-36.8,
        min_delay_ns=min_d,
        max_delay_ns=max_d,
        delays_ns=delays_ns,
        path_distances_m=distances_m,
        path_gains_db=gains_db,
        interaction_types=interaction_types,
    )


def test_strongest_path_identification():
    """Verify correct identification of dominant propagation path."""
    # Path 2 has highest gain (-65.0 dB vs -75.0 dB and -80.0 dB)
    sim_result = make_mock_result(
        gains_db=[-75.0, -65.0, -80.0],
        delays_ns=[50.0, 60.0, 70.0],
        distances_m=[15.0, 18.0, 21.0],
        interaction_types=["Line of Sight (LOS)", "Specular Reflection", "Diffuse Scattering"],
    )

    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(sim_result)

    assert analysis.strongest_path is not None
    assert analysis.strongest_path.path_index == 2  # 1-indexed
    assert analysis.strongest_path.interaction_type == "Specular Reflection"
    assert pytest.approx(analysis.strongest_path.gain_db, abs=0.01) == -65.0
    assert pytest.approx(analysis.strongest_path.delay_ns, abs=0.01) == 60.0
    assert pytest.approx(analysis.strongest_path.path_distance_m, abs=0.01) == 18.0


def test_rms_delay_spread_calculation():
    """Verify power-weighted RMS delay spread calculation against theoretical values."""
    # Two paths:
    # Path 1: gain = -70 dB, delay = 10 ns -> P1 = 1e-7
    # Path 2: gain = -70 dB, delay = 20 ns -> P2 = 1e-7 (equal power)
    # Mean delay = 15 ns
    # Deviations = -5 ns and +5 ns -> squared: 25 ns^2
    # RMS delay spread = sqrt(25) = 5.0 ns
    sim_result = make_mock_result(
        gains_db=[-70.0, -70.0],
        delays_ns=[10.0, 20.0],
        distances_m=[3.0, 6.0],
        interaction_types=["Line of Sight (LOS)", "Specular Reflection"],
    )

    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(sim_result)

    assert pytest.approx(analysis.rms_delay_spread_ns, abs=0.05) == 5.0
    assert analysis.min_delay_ns == 10.0
    assert analysis.max_delay_ns == 20.0


def test_single_path_delay_spread():
    """Verify single-path propagation has zero RMS delay spread."""
    sim_result = make_mock_result(
        gains_db=[-60.0],
        delays_ns=[40.0],
        distances_m=[12.0],
        interaction_types=["Line of Sight (LOS)"],
    )

    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(sim_result)

    assert analysis.rms_delay_spread_ns == 0.0
    assert analysis.strongest_path.path_index == 1
    assert analysis.paths[0].power_contribution_percent == 100.0


def test_path_contribution_percentages():
    """Verify relative power contribution percentages sum to approximately 100%."""
    # Path 1 is 10 dB stronger than Path 2 (10x linear power)
    # P1 = 1.0, P2 = 0.1 -> Total = 1.1 -> P1 = 90.91%, P2 = 9.09%
    sim_result = make_mock_result(
        gains_db=[-60.0, -70.0],
        delays_ns=[66.7, 74.6],
        distances_m=[20.0, 22.36],
        interaction_types=["Line of Sight (LOS)", "Specular Reflection"],
    )

    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(sim_result)

    assert len(analysis.paths) == 2
    p1 = analysis.paths[0].power_contribution_percent
    p2 = analysis.paths[1].power_contribution_percent

    assert pytest.approx(p1, abs=0.2) == 90.91
    assert pytest.approx(p2, abs=0.2) == 9.09
    assert pytest.approx(p1 + p2, abs=0.1) == 100.0


def test_los_detection_present_at_first_path():
    """Verify LOS detection when path #1 is LOS."""
    sim_result = make_mock_result(
        gains_db=[-69.35, -70.32],
        delays_ns=[66.71, 74.59],
        distances_m=[20.0, 22.36],
        interaction_types=["Line of Sight (LOS)", "Specular Reflection"],
    )

    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(sim_result)

    assert analysis.los_present is True
    assert analysis.los_path_index == 1


def test_los_detection_present_at_non_first_path():
    """Verify LOS detection does not assume path #1 is always LOS."""
    sim_result = make_mock_result(
        gains_db=[-80.0, -65.0],
        delays_ns=[50.0, 66.7],
        distances_m=[15.0, 20.0],
        interaction_types=["Specular Reflection", "Line of Sight"],
    )

    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(sim_result)

    assert analysis.los_present is True
    assert analysis.los_path_index == 2  # Found at index 2


def test_los_detection_absent():
    """Verify LOS detection when no LOS path exists."""
    sim_result = make_mock_result(
        gains_db=[-75.0, -78.0],
        delays_ns=[60.0, 75.0],
        distances_m=[18.0, 22.5],
        interaction_types=["Specular Reflection", "Diffraction"],
    )

    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(sim_result)

    assert analysis.los_present is False
    assert analysis.los_path_index is None


def test_empty_paths_handling():
    """Verify graceful handling when no propagation paths exist."""
    sim_result = make_mock_result(
        gains_db=[],
        delays_ns=[],
        distances_m=[],
        interaction_types=[],
        num_paths=0,
    )

    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(sim_result)

    assert analysis.strongest_path is None
    assert analysis.los_present is False
    assert analysis.los_path_index is None
    assert analysis.rms_delay_spread_ns == 0.0
    assert len(analysis.paths) == 0
    dict_repr = analysis.to_dict()
    assert dict_repr["strongest_path"] is None
