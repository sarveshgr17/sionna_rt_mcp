"""Detailed breakdown to isolate the exact Mitsuba element triggering Access Violation."""

import os
import sys

import mitsuba as mi

mi.set_variant("llvm_ad_mono_polarized")
print(f"[INIT] Variant: {mi.variant()}", flush=True)

# Test 1: Empty scene
print("[TEST 1] Empty scene...", flush=True)
s1 = mi.load_dict({"type": "scene"})
print(f"[TEST 1 PASS] {s1}", flush=True)

# Test 2: Standard Mitsuba BSDF
print("[TEST 2] Scene with diffuse BSDF...", flush=True)
s2 = mi.load_dict({"type": "scene", "mat": {"type": "diffuse"}})
print(f"[TEST 2 PASS] {s2}", flush=True)

# Test 3: Skipped (focus on shapes)
import sionna.rt as rt

# Test 4: Scene with a sphere shape
print("[TEST 4] Scene with sphere shape...", flush=True)
s4 = mi.load_dict({
    "type": "scene",
    "mysphere": {
        "type": "sphere",
        "radius": 1.0,
        "center": [0, 0, 0],
    },
})
print(f"[TEST 4 PASS] {s4}", flush=True)

# Test 5: Scene with a rectangle mesh shape
print("[TEST 5] Scene with rectangle mesh shape...", flush=True)
s5 = mi.load_dict({
    "type": "scene",
    "myrect": {
        "type": "rectangle",
    },
})
print(f"[TEST 5 PASS] {s5}", flush=True)

# Test 6: Scene with PLY mesh shape
print("[TEST 6] Scene with PLY mesh shape...", flush=True)
ply_path = os.path.join(
    os.path.dirname(rt.scene.simple_reflector), "meshes", "reflector.ply"
)
print(f"PLY path: {ply_path}, exists: {os.path.exists(ply_path)}", flush=True)
s6 = mi.load_dict({
    "type": "scene",
    "myreflector": {
        "type": "ply",
        "filename": ply_path,
    },
})
print(f"[TEST 6 PASS] {s6}", flush=True)

print("[ALL TESTS COMPLETED SUCCESSFULLY]", flush=True)
