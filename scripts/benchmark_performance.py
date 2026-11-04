"""Performance and memory benchmark for Sionna RT Radio Map on CPU LLVM backend.

Phase 9.5 Deliverable:
Measures execution time, memory usage, and numerical scaling across three
representative radio-map grid resolutions on the native Windows 11 platform:
  - Small Grid:  5.0m cell size, 10,000 rays (approx 15 cells)
  - Medium Grid: 2.5m cell size, 10,000 rays (approx 45 cells)
  - Fine Grid:   1.0m cell size, 20,000 rays (approx 231 cells)
"""

import ctypes
from ctypes import wintypes
import json
import os
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, List

# Ensure standalone LLVM is loaded if present
_llvm_standalone = r"C:\Users\eulo_\LLVM-standalone\LLVM-C.dll"
if os.path.isfile(_llvm_standalone):
    os.environ["DRJIT_LIBLLVM_PATH"] = _llvm_standalone
    os.environ["DRJIT_LIBCUDA_PATH"] = "DISABLED"
    os.environ["DRJIT_LIBOPTIX_PATH"] = "DISABLED"

# Ensure repo root and src are on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_dir = os.path.join(_repo_root, "src")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import numpy as np

from src.radio_map_config import RadioMapConfig
from src.radio_map_engine import RadioMapEngine
from src.radio_map_result import RadioMapResult
from src.radio_map_formatter import RadioMapFormatter
from src.experiment_store import ExperimentStore


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def get_memory_info() -> Dict[str, float]:
    """Retrieve current and peak working set memory in MB on Windows."""
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        # Open current process with PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
        h_process = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, os.getpid())
        if h_process:
            try:
                if ctypes.windll.psapi.GetProcessMemoryInfo(h_process, ctypes.byref(counters), counters.cb):
                    return {
                        "working_set_mb": round(counters.WorkingSetSize / (1024 * 1024), 2),
                        "peak_working_set_mb": round(counters.PeakWorkingSetSize / (1024 * 1024), 2),
                        "pagefile_mb": round(counters.PagefileUsage / (1024 * 1024), 2),
                    }
            finally:
                ctypes.windll.kernel32.CloseHandle(h_process)
    except Exception:
        pass
    return {"working_set_mb": 0.0, "peak_working_set_mb": 0.0, "pagefile_mb": 0.0}


def run_single_benchmark(
    name: str,
    cell_size: float,
    samples_per_tx: int,
    store: ExperimentStore,
    temp_dir: str,
) -> Dict[str, Any]:
    print(f"\n{'='*70}")
    print(f"Running Benchmark: {name}")
    print(f"Cell size: {cell_size}m | Rays: {samples_per_tx:,}")
    print(f"{'='*70}")

    mem_before = get_memory_info()

    # Step 1: Config & Engine Init
    t0_setup = time.perf_counter()
    config = RadioMapConfig(
        scene_name="simple_reflector",
        frequency_hz=3.5e9,
        tx_position=(0.0, -10.0, 5.0),
        tx_power_dbm=30.0,
        tx_orientation_deg=(0.0, 0.0, 0.0),
        antenna_type="isotropic",
        receiver_height=1.5,
        cell_size=cell_size,
        samples_per_tx=samples_per_tx,
        max_depth=3,
        los=True,
        specular_reflection=True,
        diffraction=True,
        scattering=False,
        seed=42,
    )
    engine = RadioMapEngine(config)
    t_setup = time.perf_counter() - t0_setup

    # Step 2: Solver Run
    t0_solver = time.perf_counter()
    raw_radio_map = engine.run()
    t_solver = time.perf_counter() - t0_solver

    # Step 3: Result Extraction
    t0_extract = time.perf_counter()
    result = RadioMapResult.from_raw_radio_map(
        raw_radio_map=raw_radio_map,
        config=config,
        backend_variant=engine.backend,
        region_bounds=engine.last_bounds,
    )
    t_extract = time.perf_counter() - t0_extract

    # Step 4: Heatmap Generation
    t0_heatmaps = time.perf_counter()
    heatmap_dir = os.path.join(temp_dir, f"heatmaps_{name}")
    os.makedirs(heatmap_dir, exist_ok=True)
    heatmaps = RadioMapFormatter.generate_heatmaps(result, output_dir=heatmap_dir)
    t_heatmaps = time.perf_counter() - t0_heatmaps

    # Step 5: Experiment Storage Save
    t0_storage = time.perf_counter()
    exp_id = store.save_experiment(
        result=result,
        heatmap_paths=heatmaps,
        experiment_name=f"benchmark_{name}",
    )
    t_storage = time.perf_counter() - t0_storage

    t_total = t_setup + t_solver + t_extract + t_heatmaps + t_storage
    mem_after = get_memory_info()

    bench_data = {
        "name": name,
        "cell_size_m": cell_size,
        "samples_per_tx": samples_per_tx,
        "grid_dimensions": list(result.grid_dimensions),
        "total_cells": result.num_cells,
        "valid_cells": result.valid_cells_count,
        "zero_power_cells": result.zero_power_cells_count,
        "coverage_percentage": round(result.coverage_percentage, 2),
        "min_rss_dbm": round(result.min_rss_dbm, 2) if result.min_rss_dbm is not None else None,
        "mean_rss_dbm": round(result.mean_rss_dbm, 2) if result.mean_rss_dbm is not None else None,
        "max_rss_dbm": round(result.max_rss_dbm, 2) if result.max_rss_dbm is not None else None,
        "time_setup_s": round(t_setup, 4),
        "time_solver_s": round(t_solver, 4),
        "time_extract_s": round(t_extract, 4),
        "time_heatmaps_s": round(t_heatmaps, 4),
        "time_storage_s": round(t_storage, 4),
        "time_total_s": round(t_total, 4),
        "mem_working_set_mb": mem_after["working_set_mb"],
        "mem_peak_mb": mem_after["peak_working_set_mb"],
        "experiment_id": exp_id,
    }

    print(f"  -> Grid: {result.grid_dimensions} ({result.num_cells} cells)")
    print(f"  -> Solver execution time:   {t_solver:.3f} s")
    print(f"  -> Result extraction time:   {t_extract:.3f} s")
    print(f"  -> Heatmap generation time:  {t_heatmaps:.3f} s")
    print(f"  -> Storage save time:        {t_storage:.3f} s")
    print(f"  -> Total pipeline time:      {t_total:.3f} s")
    print(f"  -> Working Set RAM:          {mem_after['working_set_mb']} MB (Peak: {mem_after['peak_working_set_mb']} MB)")

    return bench_data


def main():
    print("=" * 75)
    print("     PHASE 9.5: Sionna RT Performance and Memory Benchmarking")
    print("     Backend: CPU LLVM (llvm_ad_mono_polarized)")
    print("=" * 75)

    initial_mem = get_memory_info()
    print(f"Initial Process Memory: {initial_mem['working_set_mb']} MB")

    temp_bench_dir = tempfile.mkdtemp(prefix="sionna_bench_")
    store = ExperimentStore(storage_dir=os.path.join(temp_bench_dir, "experiments"))

    benchmarks = [
        ("Small Grid", 5.0, 10_000),
        ("Medium Grid", 2.5, 10_000),
        ("Fine Grid", 1.0, 20_000),
    ]

    results: List[Dict[str, Any]] = []

    try:
        for name, cell_size, rays in benchmarks:
            res = run_single_benchmark(name, cell_size, rays, store, temp_bench_dir)
            results.append(res)

        print("\n" + "=" * 75)
        print("                 BENCHMARK SUMMARY RESULTS TABLE")
        print("=" * 75)
        header = f"{'Grid':<12} | {'Cells':<6} | {'Dimensions':<10} | {'Rays':<8} | {'Solver':<9} | {'Heatmap':<9} | {'Total':<9} | {'Peak RAM':<9}"
        print(header)
        print("-" * len(header))
        for r in results:
            dims = f"{r['grid_dimensions'][0]}x{r['grid_dimensions'][1]}"
            print(f"{r['name']:<12} | {r['total_cells']:<6} | {dims:<10} | {r['samples_per_tx']:<8} | {r['time_solver_s']:<8.3f}s | {r['time_heatmaps_s']:<8.3f}s | {r['time_total_s']:<8.3f}s | {r['mem_peak_mb']:<6.1f} MB")

        # Save benchmark json artifact
        out_json = os.path.join(_repo_root, "benchmark_results_phase9_5.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump({
                "platform": "Windows 11",
                "backend": "llvm_ad_mono_polarized",
                "results": results,
            }, f, indent=2)
        print(f"\nBenchmark metrics written to: {out_json}")

    finally:
        shutil.rmtree(temp_bench_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
