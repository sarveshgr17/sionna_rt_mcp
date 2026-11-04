"""Tests for natural-language parameter extraction and unit conversion."""

import unittest
from src.terminal_agent.parser import (
    extract_all_parameters,
    extract_antenna_config,
    extract_cell_size,
    extract_coordinates,
    extract_experiment_ids,
    extract_frequency,
    extract_max_depth,
    extract_receiver_height,
    extract_samples_per_tx,
    extract_scene_name,
    extract_tx_power,
)


class TestParserExtraction(unittest.TestCase):
    """Verify rule-based parameter extraction."""

    def test_01_frequency_units_and_conversions(self):
        # GHz
        self.assertAlmostEqual(extract_frequency("simulate at 3.5 GHz"), 3.5e9)
        self.assertAlmostEqual(extract_frequency("Carrier frequency 28GHz"), 28.0e9)
        self.assertAlmostEqual(extract_frequency("at 5 ghz"), 5.0e9)

        # MHz
        self.assertAlmostEqual(extract_frequency("simulate at 3500 MHz"), 3.5e9)
        self.assertAlmostEqual(extract_frequency("band at 700 mhz"), 700.0e6)

        # Hz
        self.assertAlmostEqual(extract_frequency("3500000000 Hz"), 3.5e9)
        self.assertAlmostEqual(extract_frequency("frequency 3.5e9 Hz"), 3.5e9)

        # Scientific notation with keyword
        self.assertAlmostEqual(extract_frequency("frequency: 3.5e9"), 3.5e9)

        # No frequency present
        self.assertIsNone(extract_frequency("Show available scenes"))

    def test_02_coordinate_extraction(self):
        # Explicit TX and RX coordinates
        text = "Place transmitter at [0, -10, 5] and receiver at [0, 10, 5]"
        tx, rx, all_coords = extract_coordinates(text)
        self.assertEqual(tx, [0.0, -10.0, 5.0])
        self.assertEqual(rx, [0.0, 10.0, 5.0])
        self.assertEqual(len(all_coords), 2)

        # Single coordinate tagged with transmitter
        text_tx = "Put transmitter at [0, -10.5, 3.2]"
        tx2, rx2, all_coords2 = extract_coordinates(text_tx)
        self.assertEqual(tx2, [0.0, -10.5, 3.2])
        self.assertIsNone(rx2)

        # Coordinate in parentheses
        text_paren = "tx at (1.0, 2.0, 3.0)"
        tx3, rx3, _ = extract_coordinates(text_paren)
        self.assertEqual(tx3, [1.0, 2.0, 3.0])

    def test_03_cell_size_extraction(self):
        self.assertEqual(extract_cell_size("Use 5 metre cell size"), 5.0)
        self.assertEqual(extract_cell_size("5m cell size"), 5.0)
        self.assertEqual(extract_cell_size("5 meters cell size"), 5.0)
        self.assertEqual(extract_cell_size("cell size 5m"), 5.0)
        self.assertEqual(extract_cell_size("resolution of 2.5 metres"), 2.5)
        self.assertEqual(extract_cell_size("5m grid"), 5.0)
        self.assertEqual(extract_cell_size("cell size: 1.0"), 1.0)
        self.assertIsNone(extract_cell_size("No cell size here"))

    def test_04_samples_per_tx_extraction(self):
        self.assertEqual(extract_samples_per_tx("Use 10000 rays"), 10000)
        self.assertEqual(extract_samples_per_tx("10,000 rays"), 10000)
        self.assertEqual(extract_samples_per_tx("10000 samples"), 10000)
        self.assertEqual(extract_samples_per_tx("10000 samples per tx"), 10000)
        self.assertEqual(extract_samples_per_tx("ray budget 50000"), 50000)
        self.assertEqual(extract_samples_per_tx("1e4 rays"), 10000)
        self.assertIsNone(extract_samples_per_tx("Check scenes"))

    def test_05_tx_power_extraction(self):
        self.assertEqual(extract_tx_power("Change power to 30 dBm"), 30.0)
        self.assertEqual(extract_tx_power("30.0 dbm"), 30.0)
        self.assertEqual(extract_tx_power("power: 23 dBm"), 23.0)
        self.assertEqual(extract_tx_power("tx power 30"), 30.0)
        self.assertIsNone(extract_tx_power("simple_reflector"))

    def test_06_receiver_height_extraction(self):
        self.assertEqual(extract_receiver_height("receiver height 1.5m"), 1.5)
        self.assertEqual(extract_receiver_height("rx height: 1.5"), 1.5)
        self.assertEqual(extract_receiver_height("height of 2.0 metres"), 2.0)
        self.assertIsNone(extract_receiver_height("simple_reflector"))

    def test_07_scene_name_extraction(self):
        self.assertEqual(extract_scene_name("Generate map for simple_reflector"), "simple_reflector")
        self.assertEqual(extract_scene_name("scene: simple_reflector"), "simple_reflector")
        self.assertIsNone(extract_scene_name("Generate map at 3.5 GHz"))

    def test_08_experiment_id_extraction(self):
        text = "Compare experiment_20261101_100000_aaa with experiment_20261101_200000_bbb"
        ids = extract_experiment_ids(text)
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], "experiment_20261101_100000_aaa")
        self.assertEqual(ids[1], "experiment_20261101_200000_bbb")

    def test_09_max_depth_extraction(self):
        self.assertEqual(extract_max_depth("max depth 3"), 3)
        self.assertEqual(extract_max_depth("depth 4"), 4)
        self.assertEqual(extract_max_depth("3 bounces"), 3)
        self.assertIsNone(extract_max_depth("simple_reflector"))

    def test_10_antenna_config_extraction(self):
        t, p = extract_antenna_config("use isotropic antenna with vertical polarization")
        self.assertEqual(t, "isotropic")
        self.assertEqual(p, "V")

        t2, p2 = extract_antenna_config("dipole with horizontal polarization")
        self.assertEqual(t2, "dipole")
        self.assertEqual(p2, "H")

    def test_11_full_prompt_extraction(self):
        prompt = (
            "Generate a radio map for simple_reflector at 3.5 GHz. "
            "Place transmitter at [0,-10,5]. Use 5 metre cell size and 10000 rays."
        )
        params = extract_all_parameters(prompt)
        self.assertAlmostEqual(params["frequency_hz"], 3.5e9)
        self.assertEqual(params["scene_name"], "simple_reflector")
        self.assertEqual(params["tx_position"], [0.0, -10.0, 5.0])
        self.assertEqual(params["cell_size"], 5.0)
        self.assertEqual(params["samples_per_tx"], 10000)


if __name__ == "__main__":
    unittest.main()

