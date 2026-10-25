"""Wireless channel analysis layer for Sionna RT simulation results."""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional

try:
    from src.result import SimulationResult
except ImportError:
    from result import SimulationResult


@dataclass
class StrongestPath:
    """Attributes of the dominant (highest gain) propagation path."""

    path_index: int  # 1-indexed
    interaction_type: str
    gain_db: float
    delay_ns: float
    path_distance_m: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert strongest path to a JSON-serializable dictionary."""
        return {
            "path_index": int(self.path_index),
            "interaction_type": str(self.interaction_type),
            "gain_db": float(self.gain_db),
            "delay_ns": float(self.delay_ns),
            "path_distance_m": float(self.path_distance_m),
        }


@dataclass
class PathContribution:
    """Detailed breakdown for an individual propagation path."""

    path_index: int  # 1-indexed
    interaction_type: str
    gain_db: float
    delay_ns: float
    path_distance_m: float
    power_contribution_percent: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert path contribution to a JSON-serializable dictionary."""
        return {
            "path_index": int(self.path_index),
            "interaction_type": str(self.interaction_type),
            "gain_db": float(self.gain_db),
            "delay_ns": float(self.delay_ns),
            "path_distance_m": float(self.path_distance_m),
            "power_contribution_percent": float(self.power_contribution_percent),
        }


@dataclass
class AnalysisResult:
    """Structured channel analysis derived from a SimulationResult."""

    strongest_path: Optional[StrongestPath]
    los_present: bool
    los_path_index: Optional[int]
    rms_delay_spread_ns: float
    min_delay_ns: float
    max_delay_ns: float
    paths: List[PathContribution] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert analysis result to a JSON-serializable dictionary."""
        return {
            "strongest_path": self.strongest_path.to_dict() if self.strongest_path else None,
            "los_present": self.los_present,
            "los_path_index": self.los_path_index,
            "rms_delay_spread_ns": float(self.rms_delay_spread_ns),
            "min_delay_ns": float(self.min_delay_ns),
            "max_delay_ns": float(self.max_delay_ns),
            "paths": [p.to_dict() for p in self.paths],
        }


class ChannelAnalyzer:
    """Analyzes physical propagation results from a completed SimulationResult."""

    def __init__(self, result: Optional[SimulationResult] = None) -> None:
        self.result = result

    def analyze(self, result: Optional[SimulationResult] = None) -> AnalysisResult:
        """Derive wireless channel metrics from a SimulationResult.

        Args:
            result: SimulationResult instance to analyze (defaults to initialized result).

        Returns:
            AnalysisResult containing strongest path, LOS presence, RMS delay spread,
            and relative path power contributions.
        """
        res = result if result is not None else self.result
        if res is None:
            raise ValueError("SimulationResult must be provided for analysis.")

        num_paths = res.num_paths
        if num_paths == 0:
            return AnalysisResult(
                strongest_path=None,
                los_present=False,
                los_path_index=None,
                rms_delay_spread_ns=0.0,
                min_delay_ns=0.0,
                max_delay_ns=0.0,
                paths=[],
            )

        delays = res.delays_ns
        gains_db = res.path_gains_db
        distances = res.path_distances_m
        itypes = res.interaction_types

        # 1. Linear powers P_i = 10^(gain_db / 10)
        powers_linear = [
            10.0 ** (g / 10.0) if g > -140.0 else 0.0
            for g in gains_db
        ]
        total_power = sum(powers_linear)

        # 2. Strongest Path (highest gain in dB)
        best_idx = 0
        best_gain = gains_db[0]
        for idx in range(1, num_paths):
            if gains_db[idx] > best_gain:
                best_gain = gains_db[idx]
                best_idx = idx

        strongest_path = StrongestPath(
            path_index=best_idx + 1,  # 1-indexed
            interaction_type=itypes[best_idx] if best_idx < len(itypes) else "Unknown",
            gain_db=round(float(gains_db[best_idx]), 2),
            delay_ns=round(float(delays[best_idx]), 2),
            path_distance_m=round(float(distances[best_idx]), 2) if best_idx < len(distances) else 0.0,
        )

        # 3. Path Contributions & Relative Percentages
        paths_list: List[PathContribution] = []
        for i in range(num_paths):
            if total_power > 0.0:
                pct = (powers_linear[i] / total_power) * 100.0
            else:
                pct = 0.0

            dist_m = distances[i] if i < len(distances) else 0.0
            itype = itypes[i] if i < len(itypes) else "Unknown"

            paths_list.append(
                PathContribution(
                    path_index=i + 1,  # 1-indexed
                    interaction_type=itype,
                    gain_db=round(float(gains_db[i]), 2),
                    delay_ns=round(float(delays[i]), 2),
                    path_distance_m=round(float(dist_m), 2),
                    power_contribution_percent=round(float(pct), 2),
                )
            )

        # 4. RMS Delay Spread (sigma_tau)
        if num_paths > 1 and total_power > 0.0:
            # Mean excess delay: tau_bar = sum(P_i * tau_i) / sum(P_i)
            mean_delay = sum(p * d for p, d in zip(powers_linear, delays)) / total_power
            # Second moment: tau_sq_bar = sum(P_i * tau_i^2) / sum(P_i)
            mean_sq_delay = sum(p * (d ** 2) for p, d in zip(powers_linear, delays)) / total_power
            # Variance = E[tau^2] - (E[tau])^2
            variance = max(0.0, mean_sq_delay - (mean_delay ** 2))
            rms_delay_spread_ns = round(math.sqrt(variance), 2)
        else:
            rms_delay_spread_ns = 0.0

        # 5. LOS Detection (do not assume path #1 is always LOS)
        los_present = False
        los_path_index: Optional[int] = None
        for i, itype in enumerate(itypes):
            itype_lower = itype.lower()
            if "line of sight" in itype_lower or "los" in itype_lower:
                los_present = True
                los_path_index = i + 1  # 1-indexed
                break

        return AnalysisResult(
            strongest_path=strongest_path,
            los_present=los_present,
            los_path_index=los_path_index,
            rms_delay_spread_ns=rms_delay_spread_ns,
            min_delay_ns=round(float(res.min_delay_ns), 2),
            max_delay_ns=round(float(res.max_delay_ns), 2),
            paths=paths_list,
        )
