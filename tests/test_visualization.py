"""Tests for simulation storage and visualizer (Step 5)."""

import os
import shutil
import tempfile
from typing import List, Optional
import pytest

from src.analyzer import ChannelAnalyzer
from src.config import SimulationConfig
from src.engine import SimulationEngine
from src.result import SimulationResult
from src.storage import SimulationStorage
from src.visualizer import Visualizer


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory for isolated testing."""
    tmp_dir = tempfile.mkdtemp(prefix="sionna_test_storage_")
    storage = SimulationStorage(base_dir=tmp_dir)
    yield storage
    shutil.rmtree(tmp_dir, ignore_errors=True)


def make_test_result(
    num_paths: int = 2,
    delays_ns: Optional[List[float]] = None,
    path_gains_db: Optional[List[float]] = None,
    interaction_types: Optional[List[str]] = None,
    total_path_loss: float = 66.80,
    received_power: float = -36.80,
    frequency_hz: float = 3.5e9,
) -> SimulationResult:
    """Helper creating a valid SimulationResult instance."""
    delays = delays_ns if delays_ns is not None else [66.71, 74.59]
    gains = path_gains_db if path_gains_db is not None else [-69.35, -70.44]
    itypes = (
        interaction_types
        if interaction_types is not None
        else ["Line of Sight", "Specular Reflection"]
    )
    min_d = min(delays) if delays else 0.0
    max_d = max(delays) if delays else 0.0
    distances = [round(d * 1e-9 * 3e8, 2) for d in delays]

    return SimulationResult(
        scene_name="simple_reflector",
        frequency_hz=frequency_hz,
        tx_position=(0.0, -10.0, 5.0),
        tx_power_dbm=30.0,
        rx_position=(0.0, 10.0, 5.0),
        backend_variant="llvm_ad_mono_polarized",
        num_paths=num_paths,
        path_loss_db=total_path_loss,
        rx_power_dbm=received_power,
        min_delay_ns=min_d,
        max_delay_ns=max_d,
        delays_ns=delays,
        path_distances_m=distances,
        path_gains_db=gains,
        interaction_types=itypes,
    )


def test_storage_save_load_and_existence(temp_storage):
    """Verify that SimulationStorage accurately saves and reloads simulation artifacts."""
    config = SimulationConfig(
        scene="simple_reflector",
        frequency=3.5e9,
        tx_position=[0.0, -10.0, 5.0],
        rx_position=[0.0, 10.0, 5.0],
        tx_power_dbm=30.0,
    )
    engine = SimulationEngine(config)
    result = engine.run()
    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(result)

    # 1. Save simulation
    sim_id = temp_storage.save(config, result, analysis=analysis)
    assert sim_id.startswith("sim_")
    assert temp_storage.exists(sim_id)

    # 2. Verify files created on disk
    sim_dir = temp_storage.get_simulation_dir(sim_id)
    assert os.path.isfile(os.path.join(sim_dir, "config.json"))
    assert os.path.isfile(os.path.join(sim_dir, "metrics.json"))

    # 3. Load simulation
    loaded = temp_storage.load(sim_id)
    assert loaded["simulation_id"] == sim_id
    assert loaded["config"]["scene_name"] == "simple_reflector"
    assert loaded["config"]["frequency_hz"] == 3.5e9
    assert loaded["simulation"]["num_paths"] == 2
    assert loaded["analysis"]["los_present"] is True


def test_storage_unique_ids_and_no_overwrite(temp_storage):
    """Verify that consecutive simulations receive distinct IDs and do not overwrite each other."""
    config = SimulationConfig(
        scene="simple_reflector",
        frequency=3.5e9,
        tx_position=[0.0, -10.0, 5.0],
        rx_position=[0.0, 10.0, 5.0],
    )
    result = make_test_result(
        num_paths=1,
        delays_ns=[66.71],
        path_gains_db=[-69.35],
        interaction_types=["Line of Sight"],
        total_path_loss=69.35,
        received_power=-39.35,
    )

    sim_id_1 = temp_storage.save(config, result)
    sim_id_2 = temp_storage.save(config, result)

    assert sim_id_1 != sim_id_2
    assert temp_storage.exists(sim_id_1)
    assert temp_storage.exists(sim_id_2)

    sim_list = temp_storage.list_simulations()
    assert sim_id_1 in sim_list
    assert sim_id_2 in sim_list
    assert len(sim_list) >= 2


def test_storage_load_non_existent(temp_storage):
    """Verify loading non-existent simulation raises FileNotFoundError."""
    assert not temp_storage.exists("sim_non_existent_123")
    with pytest.raises(FileNotFoundError, match="not found"):
        temp_storage.load("sim_non_existent_123")


def test_visualizer_generate_all_plots(temp_storage):
    """Verify visualizer generates propagation_paths, received_power, and cir plots."""
    config = SimulationConfig(
        scene="simple_reflector",
        frequency=3.5e9,
        tx_position=[0.0, -10.0, 5.0],
        rx_position=[0.0, 10.0, 5.0],
        tx_power_dbm=30.0,
    )
    engine = SimulationEngine(config)
    result = engine.run()
    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(result)

    sim_id = temp_storage.save(config, result, analysis=analysis)
    visualizer = Visualizer(temp_storage)

    # Generate 'all' plots
    generated = visualizer.generate_plots(sim_id, plot_type="all")
    assert len(generated) == 3

    types_generated = {g["plot_type"] for g in generated}
    assert types_generated == {"propagation_paths", "received_power", "cir"}

    for g in generated:
        file_path = g["file_path"]
        assert os.path.isfile(file_path)
        assert os.path.getsize(file_path) > 1000  # Non-trivial PNG file size


def test_visualizer_individual_plot_types(temp_storage):
    """Verify visualizer can generate each plot type individually."""
    config = SimulationConfig(
        scene="simple_reflector",
        frequency=3.5e9,
        tx_position=[0.0, -10.0, 5.0],
        rx_position=[0.0, 10.0, 5.0],
    )
    result = make_test_result(
        num_paths=2,
        delays_ns=[66.71, 74.59],
        path_gains_db=[-69.35, -70.44],
        interaction_types=["Line of Sight", "Specular Reflection"],
        total_path_loss=66.80,
        received_power=-36.80,
    )
    analyzer = ChannelAnalyzer()
    analysis = analyzer.analyze(result)
    sim_id = temp_storage.save(config, result, analysis=analysis)

    visualizer = Visualizer(temp_storage)

    # 1. Individual propagation_paths
    plots_prop = visualizer.generate_plots(sim_id, plot_type="propagation_paths")
    assert len(plots_prop) == 1
    assert plots_prop[0]["plot_type"] == "propagation_paths"
    assert os.path.basename(plots_prop[0]["file_path"]) == "propagation_paths.png"

    # 2. Individual received_power
    plots_pwr = visualizer.generate_plots(sim_id, plot_type="received_power")
    assert len(plots_pwr) == 1
    assert plots_pwr[0]["plot_type"] == "received_power"
    assert os.path.basename(plots_pwr[0]["file_path"]) == "received_power.png"

    # 3. Individual cir
    plots_cir = visualizer.generate_plots(sim_id, plot_type="cir")
    assert len(plots_cir) == 1
    assert plots_cir[0]["plot_type"] == "cir"
    assert os.path.basename(plots_cir[0]["file_path"]) == "cir.png"


def test_visualizer_comparison_plot(temp_storage):
    """Verify visualizer comparison plot comparing 3.5 GHz and 28 GHz simulations."""
    config_3_5 = SimulationConfig(
        scene="simple_reflector",
        frequency=3.5e9,
        tx_position=[0.0, -10.0, 5.0],
        rx_position=[0.0, 10.0, 5.0],
    )
    result_3_5 = make_test_result(
        num_paths=2,
        delays_ns=[66.71, 74.59],
        path_gains_db=[-69.35, -70.44],
        interaction_types=["Line of Sight", "Specular Reflection"],
        total_path_loss=66.80,
        received_power=-36.80,
        frequency_hz=3.5e9,
    )
    sim_id_1 = temp_storage.save(config_3_5, result_3_5)

    config_28 = SimulationConfig(
        scene="simple_reflector",
        frequency=28.0e9,
        tx_position=[0.0, -10.0, 5.0],
        rx_position=[0.0, 10.0, 5.0],
    )
    result_28 = make_test_result(
        num_paths=2,
        delays_ns=[66.71, 74.59],
        path_gains_db=[-87.41, -88.50],
        interaction_types=["Line of Sight", "Specular Reflection"],
        total_path_loss=84.86,
        received_power=-54.86,
        frequency_hz=28.0e9,
    )
    sim_id_2 = temp_storage.save(config_28, result_28)

    visualizer = Visualizer(temp_storage)
    comparison_plots = visualizer.generate_plots(
        simulation_id=sim_id_1,
        plot_type="comparison",
        comparison_simulation_id=sim_id_2,
    )

    assert len(comparison_plots) == 1
    assert comparison_plots[0]["plot_type"] == "comparison"
    out_file = comparison_plots[0]["file_path"]
    assert os.path.isfile(out_file)
    assert os.path.basename(out_file) == "comparison.png"
    assert os.path.getsize(out_file) > 2000


def test_visualizer_error_handling(temp_storage):
    """Verify visualizer properly validates plot types and required parameters."""
    config = SimulationConfig(
        scene="simple_reflector",
        frequency=3.5e9,
        tx_position=[0.0, -10.0, 5.0],
        rx_position=[0.0, 10.0, 5.0],
    )
    result = make_test_result(
        num_paths=0,
        delays_ns=[],
        path_gains_db=[],
        interaction_types=[],
        total_path_loss=100.0,
        received_power=-70.0,
    )
    sim_id = temp_storage.save(config, result)
    visualizer = Visualizer(temp_storage)

    # 1. Unsupported plot type
    with pytest.raises(ValueError, match="Unsupported plot type 'invalid_plot'"):
        visualizer.generate_plots(sim_id, plot_type="invalid_plot")

    # 2. Missing comparison_simulation_id when plot_type='comparison'
    with pytest.raises(ValueError, match="comparison_simulation_id is required"):
        visualizer.generate_plots(sim_id, plot_type="comparison", comparison_simulation_id=None)

    # 3. Empty paths handling should succeed gracefully without exceptions
    plots = visualizer.generate_plots(sim_id, plot_type="all")
    assert len(plots) == 3
    for p in plots:
        assert os.path.isfile(p["file_path"])
