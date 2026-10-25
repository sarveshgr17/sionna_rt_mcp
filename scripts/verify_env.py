"""Environment verification script for Sionna RT.

Verifies:
1. Python version compatibility (>= 3.10).
2. Availability and version of sionna-rt.
3. Mitsuba variant selection (CUDA with OptiX or LLVM CPU fallback).
4. Loading a basic scene to confirm end-to-end functionality.
"""

import sys
from typing import Tuple


def check_python_version() -> Tuple[bool, str]:
    ver = sys.version_info
    if ver >= (3, 10):
        return True, f"Python {ver.major}.{ver.minor}.{ver.micro}"
    return False, f"Python {ver.major}.{ver.minor}.{ver.micro} (requires >= 3.10)"


def check_mitsuba_and_sionna() -> Tuple[bool, str, str]:
    try:
        import mitsuba as mi
    except ImportError as e:
        return False, f"Mitsuba import failed: {e}", ""

    # Test backend variant: attempt CUDA/OptiX first, fall back to LLVM
    active_variant = None
    if mi.variant() is None:
        import os
        stderr_fd = sys.stderr.fileno()
        saved_stderr = os.dup(stderr_fd)
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull, stderr_fd)
            try:
                mi.set_variant("cuda_ad_mono_polarized")
                mi.load_dict({"type": "scene"})
                active_variant = "cuda_ad_mono_polarized (GPU OptiX)"
            except Exception:
                mi.set_variant("llvm_ad_mono_polarized")
                active_variant = "llvm_ad_mono_polarized (CPU LLVM)"
        finally:
            os.dup2(saved_stderr, stderr_fd)
            os.close(saved_stderr)
            os.close(devnull)
    else:
        active_variant = f"{mi.variant()} (existing)"

    try:
        import sionna.rt as rt
        sionna_ver = getattr(rt, "__version__", "unknown")
        return True, f"sionna-rt v{sionna_ver}", active_variant
    except ImportError as e:
        return False, f"Sionna RT import failed: {e}", active_variant


def check_scene_load() -> Tuple[bool, str]:
    try:
        import sionna.rt as rt
        from sionna.rt import load_scene
        scene = load_scene(rt.scene.simple_reflector)
        if scene is not None:
            return True, "Loaded built-in scene 'simple_reflector'"
        return False, "load_scene returned None"
    except Exception as e:
        return False, f"Scene load error: {e}"


def main() -> int:
    print("=" * 60)
    print("       Sionna RT Environment Verification")
    print("=" * 60)

    all_passed = True

    # 1. Python
    py_ok, py_msg = check_python_version()
    print(f"[{'✓' if py_ok else '✗'}] Python: {py_msg}")
    if not py_ok:
        all_passed = False

    # 2. Mitsuba and Sionna RT
    rt_ok, rt_msg, variant = check_mitsuba_and_sionna()
    print(f"[{'✓' if rt_ok else '✗'}] Sionna RT: {rt_msg}")
    if variant:
        print(f"    Active Backend: {variant}")
    if not rt_ok:
        all_passed = False

    # 3. Scene Loading
    if rt_ok:
        scene_ok, scene_msg = check_scene_load()
        print(f"[{'✓' if scene_ok else '✗'}] Scene Loading: {scene_msg}")
        if not scene_ok:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("RESULT: Environment is ready for Sionna RT simulations! ✓")
        return 0
    else:
        print("RESULT: Environment verification failed. Please check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
