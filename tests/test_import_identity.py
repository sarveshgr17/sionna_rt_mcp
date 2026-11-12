"""Unit tests verifying consistent single module identity across all project imports.

Phase 9.5 Import Identity Verification:
Confirms that modules and dataclasses imported via 'src.<module>' and '<module>'
share identical identities and satisfy strict isinstance() checks without
relying on class-name fallbacks.
"""

import sys
import unittest


class TestImportIdentity(unittest.TestCase):
    """Verify single class and module identity regardless of import style."""

    def test_01_radio_map_config_identity(self):
        """Verify RadioMapConfig class identity matches between src and root imports."""
        import src.radio_map_config as src_mod
        import radio_map_config as root_mod

        self.assertIs(
            src_mod.RadioMapConfig,
            root_mod.RadioMapConfig,
            "RadioMapConfig class identity must be identical across import paths.",
        )

        cfg1 = src_mod.RadioMapConfig()
        cfg2 = root_mod.RadioMapConfig()

        self.assertIsInstance(cfg1, root_mod.RadioMapConfig)
        self.assertIsInstance(cfg2, src_mod.RadioMapConfig)

    def test_02_radio_map_result_identity(self):
        """Verify RadioMapResult class identity matches between src and root imports."""
        import src.radio_map_result as src_mod
        import radio_map_result as root_mod

        self.assertIs(
            src_mod.RadioMapResult,
            root_mod.RadioMapResult,
            "RadioMapResult class identity must be identical across import paths.",
        )

    def test_03_radio_map_engine_identity(self):
        """Verify RadioMapEngine class identity matches between src and root imports."""
        import src.radio_map_engine as src_mod
        import radio_map_engine as root_mod

        self.assertIs(
            src_mod.RadioMapEngine,
            root_mod.RadioMapEngine,
            "RadioMapEngine class identity must be identical across import paths.",
        )

        cfg = root_mod.RadioMapConfig()
        engine = src_mod.RadioMapEngine(cfg)
        self.assertIsInstance(engine.config, src_mod.RadioMapConfig)
        self.assertIsInstance(engine.config, root_mod.RadioMapConfig)

    def test_04_experiment_store_identity(self):
        """Verify ExperimentStore class identity matches between src and root imports."""
        import src.experiment_store as src_mod
        import experiment_store as root_mod

        self.assertIs(
            src_mod.ExperimentStore,
            root_mod.ExperimentStore,
            "ExperimentStore class identity must be identical across import paths.",
        )

    def test_05_experiment_comparator_identity(self):
        """Verify ExperimentComparator class identity matches between src and root imports."""
        import src.experiment_comparator as src_mod
        import experiment_comparator as root_mod

        self.assertIs(
            src_mod.ExperimentComparator,
            root_mod.ExperimentComparator,
            "ExperimentComparator class identity must be identical across import paths.",
        )
        self.assertIs(
            src_mod.ComparisonResult,
            root_mod.ComparisonResult,
            "ComparisonResult class identity must be identical across import paths.",
        )

    def test_06_point_to_point_simulation_identities(self):
        """Verify SimulationConfig, SimulationEngine, SimulationResult identities."""
        import src.config as src_cfg
        import config as root_cfg
        import src.engine as src_eng
        import engine as root_eng
        import src.result as src_res
        import result as root_res

        self.assertIs(src_cfg.SimulationConfig, root_cfg.SimulationConfig)
        self.assertIs(src_eng.SimulationEngine, root_eng.SimulationEngine)
        self.assertIs(src_res.SimulationResult, root_res.SimulationResult)


if __name__ == "__main__":
    unittest.main()

