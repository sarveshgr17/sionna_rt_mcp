"""Diagnostic reproduction script for Sionna RT simulation crash on Windows.

Step-by-step diagnostic script executing the exact sequence performed by
SimulationEngine.run() to pinpoint the precise failing operation.
"""

import faulthandler
import os
import sys
import time

faulthandler.enable()


def log(msg: str):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [DIAG] {msg}", flush=True)


def main():
    log("=== Windows Sionna RT Simulation Crash Reproduction ===")
    log(f"Python executable: {sys.executable}")
    log(f"Python version: {sys.version}")
    log(f"Process PID: {os.getpid()}")
    log(f"DRJIT_LIBLLVM_PATH: {os.environ.get('DRJIT_LIBLLVM_PATH')}")
    log(f"DRJIT_LIBCUDA_PATH: {os.environ.get('DRJIT_LIBCUDA_PATH')}")
    log(f"DRJIT_LIBOPTIX_PATH: {os.environ.get('DRJIT_LIBOPTIX_PATH')}")

    # Step 1: Import Mitsuba & Dr.Jit
    log("STEP 1: Importing Mitsuba and Dr.Jit...")
    try:
        import drjit as dr
        import mitsuba as mi

        log(f"STEP 1 SUCCESS: Dr.Jit version: {dr.__version__}, Mitsuba version: {mi.__version__}")
    except Exception as e:
        log(f"STEP 1 FAILED: {e}")
        return 1

    # Step 2: Initialize Mitsuba variant
    log("STEP 2: Initializing Mitsuba variant 'llvm_ad_mono_polarized'...")
    try:
        mi.set_variant("llvm_ad_mono_polarized")
        current_variant = mi.variant()
        log(f"STEP 2 SUCCESS: Active Mitsuba variant: {current_variant}")
    except Exception as e:
        log(f"STEP 2 FAILED: {e}")
        return 2

    # Step 2b: Verify basic procedural scene instantiation
    log("STEP 2b: Verifying procedural scene instantiation via mi.load_dict({'type': 'scene'})...")
    try:
        proc_scene = mi.load_dict({"type": "scene"})
        log(f"STEP 2b SUCCESS: Procedural scene loaded: {proc_scene}")
    except Exception as e:
        log(f"STEP 2b FAILED: {e}")
        return 22

    # Step 3: Import Sionna RT
    log("STEP 3: Importing Sionna RT...")
    try:
        import sionna.rt as rt
        from sionna.rt import (
            PathSolver,
            PlanarArray,
            Receiver,
            Transmitter,
            load_scene,
        )

        log(f"STEP 3 SUCCESS: Sionna RT version: {getattr(rt, '__version__', 'unknown')}")
        log(f"Sionna RT file: {rt.__file__}")
    except Exception as e:
        log(f"STEP 3 FAILED: {e}")
        return 3

    # Step 4: Inspect scene resource
    log("STEP 4: Locating 'simple_reflector' scene resource...")
    try:
        scene_source = getattr(rt.scene, "simple_reflector", None)
        log(f"rt.scene.simple_reflector: {scene_source}")
        if hasattr(scene_source, "__file__"):
            log(f"scene file path: {scene_source.__file__}")
        else:
            log(f"scene object type: {type(scene_source)}")
    except Exception as e:
        log(f"STEP 4 FAILED: {e}")
        return 4

    # Step 5: Load scene
    log("STEP 5: Executing load_scene('simple_reflector')...")
    try:
        if scene_source is not None:
            log("Calling rt.load_scene(scene_source)...")
            scene = load_scene(scene_source)
        else:
            log("Calling rt.load_scene('simple_reflector')...")
            scene = load_scene("simple_reflector")
        log(f"STEP 5 SUCCESS: Scene loaded successfully: {scene}")
    except Exception as e:
        log(f"STEP 5 FAILED with Python exception: {e}")
        import traceback

        traceback.print_exc()
        return 5

    # Step 6: Configure carrier frequency
    log("STEP 6: Configuring carrier frequency (3.5 GHz)...")
    try:
        scene.frequency = 3.5e9
        log(f"STEP 6 SUCCESS: scene.frequency = {scene.frequency}")
    except Exception as e:
        log(f"STEP 6 FAILED: {e}")
        return 6

    # Step 7: Configure antenna arrays
    log("STEP 7: Configuring TX and RX antenna arrays (PlanarArray)...")
    try:
        scene.tx_array = PlanarArray(
            num_rows=1,
            num_cols=1,
            vertical_spacing=0.5,
            horizontal_spacing=0.5,
            pattern="iso",
            polarization="V",
        )
        scene.rx_array = PlanarArray(
            num_rows=1,
            num_cols=1,
            vertical_spacing=0.5,
            horizontal_spacing=0.5,
            pattern="iso",
            polarization="V",
        )
        log("STEP 7 SUCCESS: Antenna arrays configured.")
    except Exception as e:
        log(f"STEP 7 FAILED: {e}")
        return 7

    # Step 8: Create and place transmitter & receiver
    log("STEP 8: Placing transmitter and receiver...")
    try:
        tx = Transmitter(
            name="tx",
            position=mi.Point3f(0.0, -10.0, 5.0),
            power_dbm=30.0,
        )
        rx = Receiver(
            name="rx",
            position=mi.Point3f(0.0, 10.0, 5.0),
        )
        scene.add(tx)
        scene.add(rx)
        tx.look_at(rx)
        log("STEP 8 SUCCESS: Transmitter and Receiver added and aligned.")
    except Exception as e:
        log(f"STEP 8 FAILED: {e}")
        return 8

    # Step 9: Initialize PathSolver
    log("STEP 9: Initializing PathSolver()...")
    try:
        solver = PathSolver()
        log(f"STEP 9 SUCCESS: PathSolver initialized: {solver}")
    except Exception as e:
        log(f"STEP 9 FAILED: {e}")
        return 9

    # Step 10: Execute PathSolver
    log("STEP 10: Executing solver(scene)...")
    try:
        paths = solver(scene)
        log(f"STEP 10 SUCCESS: Paths computed: {paths}")
    except Exception as e:
        log(f"STEP 10 FAILED with Python exception: {e}")
        import traceback

        traceback.print_exc()
        return 10

    # Step 11: Extract propagation results
    log("STEP 11: Extracting results from paths...")
    try:
        import numpy as np

        a_raw = np.array(paths.a)
        tau_raw = np.array(paths.tau)
        log(f"paths.a shape: {a_raw.shape}")
        log(f"paths.tau shape: {tau_raw.shape}")
        log("STEP 11 SUCCESS: Results extracted successfully.")
    except Exception as e:
        log(f"STEP 11 FAILED: {e}")
        return 11

    log("=== SIMULATION COMPLETED SUCCESSFULLY! ===")
    return 0


if __name__ == "__main__":
    exit_code = main()
    log(f"Exiting python with code {exit_code}")
    sys.exit(exit_code)

