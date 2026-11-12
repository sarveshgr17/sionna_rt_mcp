"""Unit tests for ExperimentStore (Phase 5).

Covers all 20 required test specifications:
1. Save an experiment successfully.
2. Verify metadata JSON is created.
3. Verify compressed NPZ data is created.
4. Load an experiment and reconstruct RadioMapResult.
5. Verify all numerical arrays match the original.
6. Verify -inf values survive round-trip serialization.
7. Verify metadata survives round-trip serialization.
8. Save and retrieve both heatmap PNGs.
9. Save an experiment without heatmaps.
10. List multiple experiments.
11. Retrieve experiment details.
12. Delete an experiment successfully.
13. Handle a nonexistent experiment.
14. Reject invalid experiment IDs.
15. Prevent path traversal.
16. Handle missing metadata.
17. Handle missing NPZ data.
18. Handle corrupted JSON.
19. Handle corrupted NPZ data.
20. Verify failed saves do not leave incomplete experiment directories.
Plus supplementary tests for 2D coordinates, corrupted directory skipping, and prefix resolution.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure repository root and src directory are on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_dir = os.path.join(repo_root, "src")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    import numpy as np
except (ImportError, ModuleNotFoundError):
    np = None

try:
    from experiment_store import ExperimentStore
except (ImportError, ModuleNotFoundError):
    from src.experiment_store import ExperimentStore

try:
    from radio_map_result import RadioMapResult
except (ImportError, ModuleNotFoundError):
    from src.radio_map_result import RadioMapResult


def _create_sample_radio_map_result(
    ny: int = 4,
    nx: int = 5,
    scene_name: str = "munich",
    freq_hz: float = 3.5e9,
    separable_coords: bool = True,
) -> RadioMapResult:
    """Helper to generate a valid RadioMapResult instance with deterministic test data."""
    if np is None:
        raise RuntimeError("NumPy is required to create sample RadioMapResult.")

    # Create realistic linear path gain matrix with unreached / zero-power cells
    gain_lin = np.zeros((ny, nx), dtype=np.float64)
    # Populate non-zero cells
    for r in range(ny):
        for c in range(nx):
            if (r + c) % 3 != 0:  # Intentionally leave some cells as 0.0
                gain_lin[r, c] = 1e-6 * (r * nx + c + 1)

    tx_power_dbm = 30.0
    tx_power_watts = 10.0 ** ((tx_power_dbm - 30.0) / 10.0)  # 1.0 Watt
    rss_watts = gain_lin * tx_power_watts

    # Logarithmic conversions with exact -inf for zero power / gain
    path_gain_db = np.full((ny, nx), -np.inf, dtype=np.float64)
    pos_gain = gain_lin > 0.0
    with np.errstate(divide="ignore"):
        path_gain_db[pos_gain] = 10.0 * np.log10(gain_lin[pos_gain])

    rss_dbm = np.full((ny, nx), -np.inf, dtype=np.float64)
    pos_rss = rss_watts > 0.0
    with np.errstate(divide="ignore"):
        rss_dbm[pos_rss] = 10.0 * np.log10(rss_watts[pos_rss]) + 30.0

    # Cell centers [Ny, Nx, 3]
    cell_centers = np.zeros((ny, nx, 3), dtype=np.float64)
    dx = 10.0
    dy = 8.0
    for r in range(ny):
        for c in range(nx):
            cell_centers[r, c] = [c * dx + dx / 2.0, r * dy + dy / 2.0, 1.5]

    if separable_coords:
        x_coords = np.array([c * dx + dx / 2.0 for c in range(nx)], dtype=np.float64)
        y_coords = np.array([r * dy + dy / 2.0 for r in range(ny)], dtype=np.float64)
    else:
        x_coords = cell_centers[:, :, 0]
        y_coords = cell_centers[:, :, 1]

    return RadioMapResult(
        scene_name=scene_name,
        frequency_hz=freq_hz,
        tx_position=(15.0, 20.0, 25.0),
        tx_power_dbm=tx_power_dbm,
        tx_orientation_deg=(0.0, 15.0, -5.0),
        antenna_type="directional",
        antenna_pattern="tr38901",
        polarization="V",
        measurement_height=1.5,
        region_bounds=(0.0, float(nx * dx), 0.0, float(ny * dy)),
        cell_size=(float(dx), float(dy)),
        grid_dimensions=(ny, nx),
        solver_parameters={
            "samples_per_tx": 500000,
            "max_depth": 3,
            "seed": 42,
            "los": True,
            "specular_reflection": True,
            "diffraction": False,
            "scattering": False,
        },
        simulation_timestamp="2026-11-01T12:00:00+00:00",
        backend_variant="llvm",
        path_gain_linear=gain_lin,
        path_gain_db=path_gain_db,
        rss_watts=rss_watts,
        rss_dbm=rss_dbm,
        cell_centers=cell_centers,
        x_coordinates=x_coords,
        y_coordinates=y_coords,
    )


class TestExperimentStore(unittest.TestCase):
    """Comprehensive test suite for ExperimentStore operations and edge cases."""

    def setUp(self):
        """Set up a fresh temporary directory for each test run."""
        if np is None:
            self.skipTest("NumPy is required for ExperimentStore tests.")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = self.temp_dir.name
        self.store = ExperimentStore(storage_dir=self.storage_dir)
        self.sample_result = _create_sample_radio_map_result()

    def tearDown(self):
        """Clean up the temporary directory."""
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # Test 1: Save an experiment successfully
    # -------------------------------------------------------------------------
    def test_01_save_experiment_success(self):
        """Verify that save_experiment persists files and returns a non-empty experiment ID."""
        exp_id = self.store.save_experiment(self.sample_result, experiment_name="campus_run_1")
        self.assertIsInstance(exp_id, str)
        self.assertTrue(len(exp_id) > 0)
        self.assertTrue(exp_id.startswith("experiment_"))

        target_dir = os.path.join(self.storage_dir, exp_id)
        self.assertTrue(os.path.isdir(target_dir))

    # -------------------------------------------------------------------------
    # Test 2: Verify metadata JSON is created
    # -------------------------------------------------------------------------
    def test_02_verify_metadata_json_created(self):
        """Verify that metadata.json exists, is valid JSON, and contains expected metadata."""
        exp_id = self.store.save_experiment(self.sample_result, experiment_name="meta_test")
        metadata_path = os.path.join(self.storage_dir, exp_id, "metadata.json")
        self.assertTrue(os.path.isfile(metadata_path))

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        self.assertEqual(metadata["schema_version"], "1.0")
        self.assertEqual(metadata["experiment_id"], exp_id)
        self.assertEqual(metadata["experiment_name"], "meta_test")
        self.assertEqual(metadata["scene_name"], self.sample_result.scene_name)
        self.assertEqual(metadata["frequency_hz"], self.sample_result.frequency_hz)
        self.assertEqual(metadata["tx_position"], list(self.sample_result.tx_position))
        self.assertEqual(metadata["tx_power_dbm"], self.sample_result.tx_power_dbm)
        self.assertEqual(metadata["grid_dimensions"], list(self.sample_result.grid_dimensions))
        self.assertIn("summary_metrics", metadata)
        self.assertEqual(metadata["summary_metrics"]["total_cells"], 20)
        self.assertIn("array_shapes", metadata)
        self.assertIn("path_gain_linear", metadata["array_shapes"])

    # -------------------------------------------------------------------------
    # Test 3: Verify compressed NPZ data is created
    # -------------------------------------------------------------------------
    def test_03_verify_compressed_npz_created(self):
        """Verify that radio_map_data.npz exists and contains all required numerical arrays."""
        exp_id = self.store.save_experiment(self.sample_result)
        npz_path = os.path.join(self.storage_dir, exp_id, "radio_map_data.npz")
        self.assertTrue(os.path.isfile(npz_path))

        with np.load(npz_path, allow_pickle=False) as npz:
            required_keys = [
                "path_gain_linear",
                "path_gain_db",
                "rss_watts",
                "rss_dbm",
                "cell_centers",
                "x_coordinates",
                "y_coordinates",
            ]
            for key in required_keys:
                self.assertIn(key, npz)

    # -------------------------------------------------------------------------
    # Test 4: Load an experiment and reconstruct RadioMapResult
    # -------------------------------------------------------------------------
    def test_04_load_experiment_reconstructs_result(self):
        """Verify that load_experiment reconstructs a valid RadioMapResult object."""
        exp_id = self.store.save_experiment(self.sample_result)
        loaded = self.store.load_experiment(exp_id)

        self.assertIsInstance(loaded, RadioMapResult)
        self.assertEqual(loaded.scene_name, self.sample_result.scene_name)
        self.assertEqual(loaded.grid_dimensions, self.sample_result.grid_dimensions)

    # -------------------------------------------------------------------------
    # Test 5: Verify all numerical arrays match the original
    # -------------------------------------------------------------------------
    def test_05_verify_all_numerical_arrays_match(self):
        """Verify that all numerical matrices match the original data with exact precision."""
        exp_id = self.store.save_experiment(self.sample_result)
        loaded = self.store.load_experiment(exp_id)

        self.assertTrue(
            np.array_equal(self.sample_result.path_gain_linear, loaded.path_gain_linear)
        )
        self.assertTrue(
            np.array_equal(self.sample_result.rss_watts, loaded.rss_watts)
        )
        self.assertTrue(
            np.array_equal(self.sample_result.cell_centers, loaded.cell_centers)
        )
        self.assertTrue(
            np.array_equal(self.sample_result.x_coordinates, loaded.x_coordinates)
        )
        self.assertTrue(
            np.array_equal(self.sample_result.y_coordinates, loaded.y_coordinates)
        )

    # -------------------------------------------------------------------------
    # Test 6: Verify -inf values survive round-trip serialization
    # -------------------------------------------------------------------------
    def test_06_verify_negative_inf_survives_round_trip(self):
        """Verify that -inf values in RSS and Path Gain are preserved exactly without noise floors."""
        exp_id = self.store.save_experiment(self.sample_result)
        loaded = self.store.load_experiment(exp_id)

        # Path Gain dB
        orig_pg_neginf = np.isneginf(self.sample_result.path_gain_db)
        loaded_pg_neginf = np.isneginf(loaded.path_gain_db)
        self.assertTrue(np.any(orig_pg_neginf))
        self.assertTrue(np.array_equal(orig_pg_neginf, loaded_pg_neginf))
        self.assertTrue(np.array_equal(self.sample_result.path_gain_db, loaded.path_gain_db))

        # RSS dBm
        orig_rss_neginf = np.isneginf(self.sample_result.rss_dbm)
        loaded_rss_neginf = np.isneginf(loaded.rss_dbm)
        self.assertTrue(np.any(orig_rss_neginf))
        self.assertTrue(np.array_equal(orig_rss_neginf, loaded_rss_neginf))
        self.assertTrue(np.array_equal(self.sample_result.rss_dbm, loaded.rss_dbm))

    # -------------------------------------------------------------------------
    # Test 7: Verify metadata survives round-trip serialization
    # -------------------------------------------------------------------------
    def test_07_verify_metadata_survives_round_trip(self):
        """Verify all metadata attributes survive round-trip without alteration."""
        exp_id = self.store.save_experiment(self.sample_result)
        loaded = self.store.load_experiment(exp_id)

        self.assertEqual(loaded.scene_name, self.sample_result.scene_name)
        self.assertAlmostEqual(loaded.frequency_hz, self.sample_result.frequency_hz)
        self.assertEqual(loaded.tx_position, self.sample_result.tx_position)
        self.assertAlmostEqual(loaded.tx_power_dbm, self.sample_result.tx_power_dbm)
        self.assertEqual(loaded.tx_orientation_deg, self.sample_result.tx_orientation_deg)
        self.assertEqual(loaded.antenna_type, self.sample_result.antenna_type)
        self.assertEqual(loaded.antenna_pattern, self.sample_result.antenna_pattern)
        self.assertEqual(loaded.polarization, self.sample_result.polarization)
        self.assertAlmostEqual(loaded.measurement_height, self.sample_result.measurement_height)
        self.assertEqual(loaded.region_bounds, self.sample_result.region_bounds)
        self.assertEqual(loaded.cell_size, self.sample_result.cell_size)
        self.assertEqual(loaded.grid_dimensions, self.sample_result.grid_dimensions)
        self.assertEqual(loaded.solver_parameters, self.sample_result.solver_parameters)
        self.assertEqual(loaded.backend_variant, self.sample_result.backend_variant)
        self.assertEqual(loaded.simulation_timestamp, self.sample_result.simulation_timestamp)

    # -------------------------------------------------------------------------
    # Test 8: Save and retrieve both heatmap PNGs
    # -------------------------------------------------------------------------
    def test_08_save_and_retrieve_both_heatmaps(self):
        """Verify that provided heatmaps are copied into the experiment directory and reported."""
        # Create temporary dummy PNG files
        dummy_dir = tempfile.mkdtemp(dir=self.storage_dir)
        rss_src = os.path.join(dummy_dir, "temp_rss.png")
        gain_src = os.path.join(dummy_dir, "temp_gain.png")

        with open(rss_src, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy_rss_data")
        with open(gain_src, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy_gain_data")

        try:
            heatmap_paths = {
                "rss_heatmap": rss_src,
                "path_gain_heatmap": gain_src,
            }
            exp_id = self.store.save_experiment(self.sample_result, heatmap_paths=heatmap_paths)

            # Check that files exist in experiment directory
            exp_dir = os.path.join(self.storage_dir, exp_id)
            self.assertTrue(os.path.isfile(os.path.join(exp_dir, "rss_heatmap.png")))
            self.assertTrue(os.path.isfile(os.path.join(exp_dir, "path_gain_heatmap.png")))

            details = self.store.get_experiment_details(exp_id)
            self.assertTrue(details["heatmaps_available"]["rss_heatmap"])
            self.assertTrue(details["heatmaps_available"]["path_gain_heatmap"])
            self.assertTrue(os.path.isabs(details["artifact_paths"]["rss_heatmap"]))
            self.assertTrue(os.path.isabs(details["artifact_paths"]["path_gain_heatmap"]))
        finally:
            shutil.rmtree(dummy_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Test 9: Save an experiment without heatmaps
    # -------------------------------------------------------------------------
    def test_09_save_without_heatmaps(self):
        """Verify that saving without heatmaps succeeds and reports heatmaps as unavailable."""
        exp_id = self.store.save_experiment(self.sample_result, heatmap_paths=None)

        exp_dir = os.path.join(self.storage_dir, exp_id)
        self.assertFalse(os.path.isfile(os.path.join(exp_dir, "rss_heatmap.png")))
        self.assertFalse(os.path.isfile(os.path.join(exp_dir, "path_gain_heatmap.png")))

        details = self.store.get_experiment_details(exp_id)
        self.assertFalse(details["heatmaps_available"]["rss_heatmap"])
        self.assertFalse(details["heatmaps_available"]["path_gain_heatmap"])
        self.assertIsNone(details["artifact_paths"]["rss_heatmap"])
        self.assertIsNone(details["artifact_paths"]["path_gain_heatmap"])

    # -------------------------------------------------------------------------
    # Test 10: List multiple experiments
    # -------------------------------------------------------------------------
    def test_10_list_multiple_experiments(self):
        """Verify that list_experiments returns lightweight summaries for all saved experiments."""
        # Save 3 distinct experiments
        id1 = self.store.save_experiment(self.sample_result, experiment_name="run_alpha")
        id2 = self.store.save_experiment(self.sample_result, experiment_name="run_beta")
        id3 = self.store.save_experiment(self.sample_result, experiment_name="run_gamma")

        listed = self.store.list_experiments()
        self.assertEqual(len(listed), 3)

        retrieved_ids = [item["experiment_id"] for item in listed]
        self.assertIn(id1, retrieved_ids)
        self.assertIn(id2, retrieved_ids)
        self.assertIn(id3, retrieved_ids)

        for summary in listed:
            self.assertIn("scene_name", summary)
            self.assertIn("frequency_hz", summary)
            self.assertIn("tx_position", summary)
            self.assertIn("coverage_percentage", summary)
            self.assertIn("heatmaps_available", summary)
            # Ensure heavy numerical arrays are not loaded in summary
            self.assertNotIn("path_gain_linear", summary)
            self.assertNotIn("rss_watts", summary)

    # -------------------------------------------------------------------------
    # Test 11: Retrieve experiment details
    # -------------------------------------------------------------------------
    def test_11_retrieve_experiment_details(self):
        """Verify get_experiment_details retrieves full metadata and artifact paths without loading arrays."""
        exp_id = self.store.save_experiment(self.sample_result, experiment_name="detail_test")
        details = self.store.get_experiment_details(exp_id)

        self.assertEqual(details["experiment_id"], exp_id)
        self.assertEqual(details["experiment_name"], "detail_test")
        self.assertEqual(details["scene_name"], self.sample_result.scene_name)
        self.assertIn("artifact_paths", details)
        self.assertTrue(os.path.isfile(details["artifact_paths"]["metadata"]))
        self.assertTrue(os.path.isfile(details["artifact_paths"]["radio_map_data"]))
        self.assertTrue(details["radio_map_data_exists"])
        self.assertNotIn("path_gain_linear", details)

    # -------------------------------------------------------------------------
    # Test 12: Delete an experiment successfully
    # -------------------------------------------------------------------------
    def test_12_delete_experiment_success(self):
        """Verify delete_experiment removes directory and subsequent queries fail cleanly."""
        exp_id = self.store.save_experiment(self.sample_result)
        exp_dir = os.path.join(self.storage_dir, exp_id)
        self.assertTrue(os.path.isdir(exp_dir))

        result = self.store.delete_experiment(exp_id)
        self.assertTrue(result)
        self.assertFalse(os.path.exists(exp_dir))

        with self.assertRaises(FileNotFoundError):
            self.store.load_experiment(exp_id)

    # -------------------------------------------------------------------------
    # Test 13: Handle a nonexistent experiment
    # -------------------------------------------------------------------------
    def test_13_handle_nonexistent_experiment(self):
        """Verify clear FileNotFoundError for missing experiments and False for deletion."""
        nonexistent_id = "experiment_20990101_000000_deadbeef"

        with self.assertRaises(FileNotFoundError):
            self.store.load_experiment(nonexistent_id)

        with self.assertRaises(FileNotFoundError):
            self.store.get_experiment_details(nonexistent_id)

        # Deleting nonexistent experiment returns False
        self.assertFalse(self.store.delete_experiment(nonexistent_id))

    # -------------------------------------------------------------------------
    # Test 14: Reject invalid experiment IDs
    # -------------------------------------------------------------------------
    def test_14_reject_invalid_experiment_ids(self):
        """Verify that invalid experiment IDs are rejected with ValueError."""
        invalid_ids = [
            "",
            "   ",
            None,
            12345,
            "test*id",
            "test?id",
            "test:id",
            "test|id",
            "test<id",
            "test>id",
            "test\"id",
            "null\0byte",
        ]

        for bad_id in invalid_ids:
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(ValueError):
                    self.store.load_experiment(bad_id)  # type: ignore
                with self.assertRaises(ValueError):
                    self.store.get_experiment_details(bad_id)  # type: ignore
                with self.assertRaises(ValueError):
                    self.store.delete_experiment(bad_id)  # type: ignore

    # -------------------------------------------------------------------------
    # Test 15: Prevent path traversal
    # -------------------------------------------------------------------------
    def test_15_prevent_path_traversal(self):
        """Verify that directory traversal attempts are strictly blocked."""
        traversal_attempts = [
            "../secret",
            "../../etc/passwd",
            "..\\windows\\system32",
            "/outside",
            "\\outside",
            ".",
            "..",
            "....//evil",
        ]

        for attempt in traversal_attempts:
            with self.subTest(attempt=attempt):
                with self.assertRaises(ValueError):
                    self.store.load_experiment(attempt)
                with self.assertRaises(ValueError):
                    self.store.get_experiment_details(attempt)
                with self.assertRaises(ValueError):
                    self.store.delete_experiment(attempt)
                with self.assertRaises(ValueError):
                    self.store.save_experiment(self.sample_result, experiment_id=attempt)

    # -------------------------------------------------------------------------
    # Test 16: Handle missing metadata
    # -------------------------------------------------------------------------
    def test_16_handle_missing_metadata(self):
        """Verify FileNotFoundError when metadata.json is missing from experiment folder."""
        exp_id = self.store.save_experiment(self.sample_result)
        metadata_file = os.path.join(self.storage_dir, exp_id, "metadata.json")
        os.remove(metadata_file)

        with self.assertRaises(FileNotFoundError):
            self.store.load_experiment(exp_id)

        with self.assertRaises(FileNotFoundError):
            self.store.get_experiment_details(exp_id)

    # -------------------------------------------------------------------------
    # Test 17: Handle missing NPZ data
    # -------------------------------------------------------------------------
    def test_17_handle_missing_npz_data(self):
        """Verify FileNotFoundError when radio_map_data.npz is missing from experiment folder."""
        exp_id = self.store.save_experiment(self.sample_result)
        npz_file = os.path.join(self.storage_dir, exp_id, "radio_map_data.npz")
        os.remove(npz_file)

        with self.assertRaises(FileNotFoundError):
            self.store.load_experiment(exp_id)

    # -------------------------------------------------------------------------
    # Test 18: Handle corrupted JSON
    # -------------------------------------------------------------------------
    def test_18_handle_corrupted_json(self):
        """Verify ValueError when metadata.json contains malformed non-JSON data."""
        exp_id = self.store.save_experiment(self.sample_result)
        metadata_file = os.path.join(self.storage_dir, exp_id, "metadata.json")

        with open(metadata_file, "w", encoding="utf-8") as f:
            f.write("{\n  invalid json: syntax error,\n")

        with self.assertRaises(ValueError) as ctx:
            self.store.load_experiment(exp_id)
        self.assertIn("Corrupted or invalid metadata JSON", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            self.store.get_experiment_details(exp_id)
        self.assertIn("Corrupted or invalid metadata JSON", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 19: Handle corrupted NPZ data
    # -------------------------------------------------------------------------
    def test_19_handle_corrupted_npz_data(self):
        """Verify ValueError when radio_map_data.npz contains unparseable binary data."""
        exp_id = self.store.save_experiment(self.sample_result)
        npz_file = os.path.join(self.storage_dir, exp_id, "radio_map_data.npz")

        with open(npz_file, "wb") as f:
            f.write(b"NOT_A_VALID_ZIP_OR_NPZ_ARCHIVE_DATA")

        with self.assertRaises(ValueError) as ctx:
            self.store.load_experiment(exp_id)
        self.assertIn("Corrupted or invalid NPZ numerical data", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 20: Verify failed saves do not leave incomplete experiment directories
    # -------------------------------------------------------------------------
    def test_20_failed_saves_leave_no_incomplete_directories(self):
        """Verify atomic saving: if an error occurs mid-save, no incomplete directory is left."""
        # Intentionally patch np.savez_compressed to simulate unexpected disk or I/O failure
        with patch("numpy.savez_compressed", side_effect=IOError("Simulated disk write failure")):
            with self.assertRaises(IOError):
                self.store.save_experiment(self.sample_result, experiment_name="doomed_save")

        # Verify no directories or temporary staging directories (.tmp_*) were left behind
        remaining_entries = os.listdir(self.storage_dir)
        self.assertEqual(
            remaining_entries,
            [],
            f"Stale directory or files remained after failed save: {remaining_entries}",
        )

    # -------------------------------------------------------------------------
    # Supplementary Test 21: Non-separable 2D coordinates round-trip
    # -------------------------------------------------------------------------
    def test_21_non_separable_2d_coordinates_round_trip(self):
        """Verify that 2D non-separable coordinate matrices survive round-trip serialization."""
        non_sep_result = _create_sample_radio_map_result(ny=3, nx=4, separable_coords=False)
        self.assertEqual(non_sep_result.x_coordinates.ndim, 2)
        self.assertEqual(non_sep_result.y_coordinates.ndim, 2)

        exp_id = self.store.save_experiment(non_sep_result, experiment_name="non_separable_grid")
        loaded = self.store.load_experiment(exp_id)

        self.assertEqual(loaded.x_coordinates.ndim, 2)
        self.assertEqual(loaded.y_coordinates.ndim, 2)
        self.assertTrue(np.array_equal(non_sep_result.x_coordinates, loaded.x_coordinates))
        self.assertTrue(np.array_equal(non_sep_result.y_coordinates, loaded.y_coordinates))

    # -------------------------------------------------------------------------
    # Supplementary Test 22: list_experiments skips corrupted directories gracefully
    # -------------------------------------------------------------------------
    def test_22_list_experiments_skips_corrupted_directories(self):
        """Verify list_experiments continues and lists valid experiments even if one directory is corrupted."""
        valid_id = self.store.save_experiment(self.sample_result, experiment_name="valid_run")

        # Create a corrupted directory in the same storage folder
        corrupt_dir = os.path.join(self.storage_dir, "experiment_corrupted_dir")
        os.makedirs(corrupt_dir, exist_ok=True)
        with open(os.path.join(corrupt_dir, "metadata.json"), "w") as f:
            f.write("{ invalid json")

        # list_experiments should not crash and should return the valid experiment
        listed = self.store.list_experiments()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["experiment_id"], valid_id)

    # -------------------------------------------------------------------------
    # Supplementary Test 23: Prefix-agnostic experiment resolution
    # -------------------------------------------------------------------------
    def test_23_prefix_agnostic_resolution(self):
        """Verify load_experiment and details resolve both with and without 'experiment_' prefix."""
        exp_id = self.store.save_experiment(self.sample_result)
        self.assertTrue(exp_id.startswith("experiment_"))

        suffix_only = exp_id[len("experiment_") :]
        loaded_by_suffix = self.store.load_experiment(suffix_only)
        self.assertEqual(loaded_by_suffix.scene_name, self.sample_result.scene_name)

        details_by_suffix = self.store.get_experiment_details(suffix_only)
        self.assertEqual(details_by_suffix["experiment_id"], exp_id)


if __name__ == "__main__":
    unittest.main()

