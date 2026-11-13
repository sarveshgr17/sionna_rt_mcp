import React, { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Grid, Eye, RefreshCw, ZoomIn, Layers, Maximize2, Crosshair } from "lucide-react";
import { useSceneGeometry } from "@/hooks/useMcp";
import { SceneMesh } from "@/types/mcp";

interface RayTracingVisualizer3DProps {
  txPosition: [number, number, number];
  rxPosition: [number, number, number];
  paths?: Array<{
    interaction_type: string;
    path_distance: number;
    delay_ns: number;
    path_gain_db: number;
  }>;
  sceneName?: string;
}

// Coordinate mapping: Sionna RT [X, Y, Z] (Z=Up, Y=North) -> Three.js [X, Z, -Y] (Y=Up, -Z=North)
const toThree = (p: [number, number, number]): THREE.Vector3 => {
  return new THREE.Vector3(p[0], p[2], -p[1]);
};

// ITU-R P.2040 Material Color & PBR Properties
const ITU_PALETTE: Record<
  string,
  { color: number; roughness: number; metalness: number; opacity?: number }
> = {
  marble: { color: 0xd4c8b8, roughness: 0.45, metalness: 0.1 },
  metal: { color: 0x64748b, roughness: 0.3, metalness: 0.75 },
  concrete: { color: 0x5a6978, roughness: 0.85, metalness: 0.05 },
  brick: { color: 0xba5338, roughness: 0.8, metalness: 0.05 },
  glass: { color: 0x38bdf8, roughness: 0.1, metalness: 0.9, opacity: 0.65 },
  wood: { color: 0x92400e, roughness: 0.8, metalness: 0.05 },
  "itu-radio-material": { color: 0x475569, roughness: 0.5, metalness: 0.3 },
  "reflector-mat": { color: 0x38bdf8, roughness: 0.2, metalness: 0.8 },
};

export function RayTracingVisualizer3D({
  txPosition,
  rxPosition,
  paths = [],
  sceneName = "munich",
}: RayTracingVisualizer3DProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [viewMode, setViewMode] = useState<"focus" | "fit_scene" | "top" | "side">("focus");

  // Three.js Core Refs
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);

  // Group Refs
  const geometryGroupRef = useRef<THREE.Group>(new THREE.Group());
  const markersGroupRef = useRef<THREE.Group>(new THREE.Group());

  // Fetch real 3D mesh geometry from the backend adapter
  const { data: geomData, isLoading: geomLoading } = useSceneGeometry(sceneName);

  // --------------------------------------------------------------------------
  // 1. One-time Setup: Scene, Camera, Renderer, Controls, Lighting
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!mountRef.current) return;
    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight || 400;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0f1319");
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 8000);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = false; // keep fast on web
    mountRef.current.replaceChildren(renderer.domElement);
    rendererRef.current = renderer;

    // Architectural Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    scene.add(ambientLight);

    const hemiLight = new THREE.HemisphereLight(0xe2e8f0, 0x1e293b, 0.7);
    scene.add(hemiLight);

    const sunLight = new THREE.DirectionalLight(0xfff7ed, 1.25);
    sunLight.position.set(300, 600, 300);
    scene.add(sunLight);

    const fillLight = new THREE.DirectionalLight(0x94a3b8, 0.5);
    fillLight.position.set(-300, 200, -300);
    scene.add(fillLight);

    // Add Scene Hierarchy Groups
    const geomGroup = geometryGroupRef.current;
    const markGroup = markersGroupRef.current;
    geomGroup.clear();
    markGroup.clear();
    scene.add(geomGroup);
    scene.add(markGroup);

    // OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;
    controls.maxDistance = 5000;
    controls.minDistance = 2;
    controlsRef.current = controls;

    // Render loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!mountRef.current) return;
      const newWidth = mountRef.current.clientWidth;
      const newHeight = mountRef.current.clientHeight || 400;
      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);
    };

    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", handleResize);
      controls.dispose();
      renderer.dispose();
    };
  }, []);

  // --------------------------------------------------------------------------
  // 2. Camera Positioning Logic
  // --------------------------------------------------------------------------
  const setCameraPosition = useCallback(
    (mode: "focus" | "fit_scene" | "top" | "side") => {
      const camera = cameraRef.current;
      const controls = controlsRef.current;
      if (!camera || !controls) return;

      const threeTx = toThree(txPosition);
      const threeRx = toThree(rxPosition);
      const midX = (threeTx.x + threeRx.x) / 2;
      const midY = (threeTx.y + threeRx.y) / 2;
      const midZ = (threeTx.z + threeRx.z) / 2;
      const span = Math.max(threeTx.distanceTo(threeRx), 40);

      if (mode === "focus") {
        // Aerial elevated view above local rooftops looking down into the simulation area
        const camElevation = Math.max(threeTx.y + 70, midY + span * 0.9, 90);
        const camDist = span * 1.35;
        camera.position.set(midX + camDist * 0.85, camElevation, midZ + camDist * 0.85);
        controls.target.set(midX, midY, midZ);
      } else if (mode === "fit_scene") {
        // Frame entire 3D city bounding box
        if (geomData?.bbox) {
          const bMin = geomData.bbox.min;
          const bMax = geomData.bbox.max;
          const centerX = (bMin[0] + bMax[0]) / 2;
          const centerY = (bMin[1] + bMax[1]) / 2;
          const centerZ = (bMin[2] + bMax[2]) / 2;
          const sizeX = Math.abs(bMax[0] - bMin[0]);
          const sizeZ = Math.abs(bMax[2] - bMin[2]);
          const maxExtent = Math.max(sizeX, sizeZ, 120);

          camera.position.set(
            centerX + maxExtent * 0.9,
            centerY + maxExtent * 0.85,
            centerZ + maxExtent * 0.9
          );
          controls.target.set(centerX, centerY, centerZ);
        } else {
          camera.position.set(midX + span * 2.5, midY + span * 2.0, midZ + span * 2.5);
          controls.target.set(midX, midY, midZ);
        }
      } else if (mode === "top") {
        const topHeight = Math.max(threeTx.y + 120, span * 2.2, 180);
        camera.position.set(midX, topHeight, midZ);
        controls.target.set(midX, 0, midZ);
      } else if (mode === "side") {
        const sideDist = Math.max(span * 2.0, 100);
        camera.position.set(midX + sideDist, Math.max(threeTx.y + 20, 30), midZ);
        controls.target.set(midX, midY, midZ);
      }

      controls.update();
      setViewMode(mode);
    },
    [txPosition, rxPosition, geomData]
  );

  // --------------------------------------------------------------------------
  // 3. Geometry Update: Real 3D Building & Terrain Meshes
  // --------------------------------------------------------------------------
  useEffect(() => {
    const group = geometryGroupRef.current;
    const scene = sceneRef.current;
    if (!group || !scene) return;

    // Clear previous geometries and meshes
    while (group.children.length > 0) {
      const child = group.children[0];
      group.remove(child);
      if (child instanceof THREE.Mesh) {
        child.geometry?.dispose();
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => m.dispose());
        } else {
          child.material?.dispose();
        }
      }
    }

    // Ground Grid Helper setup
    if (gridHelperRef.current) {
      scene.remove(gridHelperRef.current);
      gridHelperRef.current.dispose();
      gridHelperRef.current = null;
    }

    const threeTx = toThree(txPosition);
    const threeRx = toThree(rxPosition);
    const midX = (threeTx.x + threeRx.x) / 2;
    const midZ = (threeTx.z + threeRx.z) / 2;
    const span = Math.max(threeTx.distanceTo(threeRx), 40);

    const gridSize = geomData?.bbox
      ? Math.max(160, Math.ceil(Math.max(
          Math.abs(geomData.bbox.max[0] - geomData.bbox.min[0]),
          Math.abs(geomData.bbox.max[2] - geomData.bbox.min[2])
        ) * 0.75 / 20) * 20)
      : Math.max(120, Math.ceil(span * 3 / 10) * 10);

    const grid = new THREE.GridHelper(
      gridSize,
      Math.min(80, Math.max(20, Math.floor(gridSize / 10))),
      0x475569,
      0x1e293b
    );
    // Slight Y offset to prevent Z-fighting with ground surface
    grid.position.set(midX, 0.05, midZ);
    grid.visible = showGrid;
    scene.add(grid);
    gridHelperRef.current = grid;

    // Render real 3D mesh geometry from Sionna RT
    if (geomData?.meshes && geomData.meshes.length > 0) {
      geomData.meshes.forEach((m: SceneMesh) => {
        if (!m.vertices || m.vertices.length === 0) return;

        const geom = new THREE.BufferGeometry();
        geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(m.vertices), 3));
        if (m.faces && m.faces.length > 0) {
          geom.setIndex(m.faces);
        }
        geom.computeVertexNormals();

        const isGround =
          m.name.toLowerCase().includes("ground") ||
          m.name.toLowerCase().includes("terrain") ||
          m.name.toLowerCase() === "floor";

        if (isGround) {
          // Terrain / Ground Material
          const groundMat = new THREE.MeshStandardMaterial({
            color: 0x141b24,
            roughness: 0.95,
            metalness: 0.05,
            side: THREE.DoubleSide,
          });
          const mesh = new THREE.Mesh(geom, groundMat);
          mesh.position.y = -0.05; // Drop slightly to eliminate Z-fighting
          group.add(mesh);
        } else {
          // Architectural Building Material
          const pal = ITU_PALETTE[m.material.toLowerCase()] || {
            color: 0x5a6978,
            roughness: 0.6,
            metalness: 0.25,
          };

          const buildingMat = new THREE.MeshStandardMaterial({
            color: pal.color,
            roughness: pal.roughness,
            metalness: pal.metalness,
            transparent: pal.opacity !== undefined,
            opacity: pal.opacity ?? 1.0,
            side: THREE.DoubleSide,
          });

          const mesh = new THREE.Mesh(geom, buildingMat);
          group.add(mesh);

          // Add crisp building edge lines for structures with moderate face counts
          if (m.faces && m.faces.length < 18000) {
            const edges = new THREE.EdgesGeometry(geom, 28);
            const lineMat = new THREE.LineBasicMaterial({
              color: 0x94a3b8,
              transparent: true,
              opacity: 0.32,
            });
            const wire = new THREE.LineSegments(edges, lineMat);
            group.add(wire);
          }
        }
      });
    } else {
      // Fallback schematic buildings while loading or offline
      const addBuilding = (
        x: number,
        y: number,
        z: number,
        w: number,
        h: number,
        d: number,
        color = 0x243242,
        wireColor = 0x38bdf8
      ) => {
        const geom = new THREE.BoxGeometry(w, h, d);
        const mat = new THREE.MeshStandardMaterial({
          color,
          roughness: 0.5,
          metalness: 0.3,
        });
        const mesh = new THREE.Mesh(geom, mat);
        mesh.position.set(x, y + h / 2, z);
        group.add(mesh);

        const edges = new THREE.EdgesGeometry(geom);
        const lMat = new THREE.LineBasicMaterial({ color: wireColor, transparent: true, opacity: 0.4 });
        const wire = new THREE.LineSegments(edges, lMat);
        wire.position.copy(mesh.position);
        group.add(wire);
      };

      if (sceneName === "munich") {
        addBuilding(20, 0, -40, 20, 50, 20, 0x334155, 0xf97316);
        addBuilding(-15, 0, -40, 20, 50, 20, 0x334155, 0xf97316);
        addBuilding(5, 0, -60, 34, 30, 48, 0x1e293b, 0x64748b);
        addBuilding(-50, 0, -10, 28, 24, 28, 0x1e293b, 0x38bdf8);
      } else if (sceneName === "san_francisco") {
        addBuilding(0, 0, 0, 100, 35, 100, 0x334155, 0x38bdf8);
        addBuilding(55, 0, -55, 65, 50, 65, 0x1e293b, 0xf97316);
        addBuilding(-65, 0, 45, 75, 40, 75, 0x1e293b, 0x64748b);
      } else {
        addBuilding(0, 0, -18, 90, 25, 12, 0x1e293b, 0x38bdf8);
        addBuilding(0, 0, 18, 90, 25, 12, 0x1e293b, 0x38bdf8);
      }
    }

    // Set initial camera view
    setCameraPosition("focus");
  }, [geomData, sceneName, setCameraPosition, txPosition, rxPosition, showGrid]);

  // --------------------------------------------------------------------------
  // 4. Markers & Rays Update: TX Beacon, RX Beacon, Ground Stems, Rays
  // --------------------------------------------------------------------------
  useEffect(() => {
    const group = markersGroupRef.current;
    if (!group) return;

    // Clear markers
    while (group.children.length > 0) {
      const child = group.children[0];
      group.remove(child);
      if (child instanceof THREE.Mesh || child instanceof THREE.Line) {
        child.geometry?.dispose();
      }
    }

    const threeTx = toThree(txPosition);
    const threeRx = toThree(rxPosition);
    const span = Math.max(threeTx.distanceTo(threeRx), 30);

    // TX Marker (Glowing Orange Sphere)
    const txRadius = Math.max(1.2, span * 0.022);
    const txGeom = new THREE.SphereGeometry(txRadius, 20, 20);
    const txMat = new THREE.MeshStandardMaterial({
      color: 0xf97316,
      emissive: 0xea580c,
      emissiveIntensity: 0.85,
    });
    const txMesh = new THREE.Mesh(txGeom, txMat);
    txMesh.position.copy(threeTx);
    group.add(txMesh);

    // TX Ground Stem (Dashed vertical line down to Y=0)
    if (threeTx.y > 0.5) {
      const txStemGeom = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(threeTx.x, 0, threeTx.z),
        threeTx,
      ]);
      const txStemMat = new THREE.LineDashedMaterial({
        color: 0xf97316,
        dashSize: 1.0,
        gapSize: 0.6,
        transparent: true,
        opacity: 0.65,
      });
      const txStem = new THREE.Line(txStemGeom, txStemMat);
      txStem.computeLineDistances();
      group.add(txStem);
    }

    // RX Marker (Glowing Cyan Box)
    const rxBoxSize = Math.max(1.5, span * 0.028);
    const rxGeom = new THREE.BoxGeometry(rxBoxSize, rxBoxSize, rxBoxSize);
    const rxMat = new THREE.MeshStandardMaterial({
      color: 0x06b6d4,
      emissive: 0x0891b2,
      emissiveIntensity: 0.85,
    });
    const rxMesh = new THREE.Mesh(rxGeom, rxMat);
    rxMesh.position.copy(threeRx);
    group.add(rxMesh);

    // RX Ground Stem
    if (threeRx.y > 0.5) {
      const rxStemGeom = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(threeRx.x, 0, threeRx.z),
        threeRx,
      ]);
      const rxStemMat = new THREE.LineDashedMaterial({
        color: 0x06b6d4,
        dashSize: 0.8,
        gapSize: 0.5,
        transparent: true,
        opacity: 0.65,
      });
      const rxStem = new THREE.Line(rxStemGeom, rxStemMat);
      rxStem.computeLineDistances();
      group.add(rxStem);
    }

    // Direct Line-of-Sight (LOS) Ray
    const losGeom = new THREE.BufferGeometry().setFromPoints([threeTx, threeRx]);
    const losMat = new THREE.LineBasicMaterial({
      color: 0xf97316,
      linewidth: 3,
    });
    const losLine = new THREE.Line(losGeom, losMat);
    group.add(losLine);

    // Secondary / Reflected Rays (if paths or scene features exist)
    if (paths && paths.length > 1) {
      // Color-code secondary paths
      paths.slice(1, 5).forEach((p, idx) => {
        const offsetMultiplier = (idx + 1) * 0.25;
        // Construct approximate bounce point based on path distance
        const midPoint = new THREE.Vector3(
          (threeTx.x + threeRx.x) / 2 + (idx % 2 === 0 ? span * 0.35 : -span * 0.35),
          Math.max(threeTx.y, threeRx.y) * 0.65,
          (threeTx.z + threeRx.z) / 2 + (idx % 2 === 0 ? span * 0.25 : -span * 0.25)
        );

        const rayGeom = new THREE.BufferGeometry().setFromPoints([threeTx, midPoint, threeRx]);
        const rayMat = new THREE.LineDashedMaterial({
          color: idx === 0 ? 0x38bdf8 : 0xa855f7,
          dashSize: 1.2,
          gapSize: 0.8,
          linewidth: 2,
        });
        const rayLine = new THREE.Line(rayGeom, rayMat);
        rayLine.computeLineDistances();
        group.add(rayLine);
      });
    }
  }, [txPosition, rxPosition, paths]);

  const toggleGrid = () => {
    if (gridHelperRef.current) {
      gridHelperRef.current.visible = !showGrid;
      setShowGrid(!showGrid);
    }
  };

  return (
    <div className="relative rounded-md overflow-hidden border border-slate-800 bg-terminal shadow-technical">
      {/* Visualizer Top Bar */}
      <div className="absolute top-0 left-0 right-0 z-10 px-3 py-2 bg-terminal-surface/90 backdrop-blur border-b border-terminal-border flex items-center justify-between text-xs font-mono text-slate-300">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-200">3D Ray-Tracing Visualizer</span>
          {geomLoading ? (
            <span className="text-[10px] font-mono text-amber-400 animate-pulse flex items-center gap-1">
              <RefreshCw className="w-3 h-3 animate-spin" /> Loading Real 3D Mesh...
            </span>
          ) : geomData?.meshes?.length ? (
            <span className="text-[10px] font-mono text-teal-400 bg-teal-950/70 border border-teal-800/80 px-2 py-0.5 rounded flex items-center gap-1.5 shadow-sm">
              <Layers className="w-3 h-3 text-teal-400" />
              <span>
                REAL 3D MESH ({geomData.total_faces.toLocaleString()} faces, {geomData.meshes.length} objects)
              </span>
            </span>
          ) : (
            <span className="text-[10px] text-slate-400">Cartesian Isometric View</span>
          )}
        </div>

        {/* Viewport Action Controls */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setCameraPosition("focus")}
            title="Focus on Transmitter & Receiver"
            className={`px-2 py-0.5 rounded text-[10px] border transition-colors flex items-center gap-1 ${
              viewMode === "focus"
                ? "bg-rust text-white border-rust font-bold"
                : "border-slate-700 text-slate-400 hover:text-white"
            }`}
          >
            <Crosshair className="w-3 h-3" />
            <span>Focus TX/RX</span>
          </button>
          <button
            onClick={() => setCameraPosition("fit_scene")}
            title="Frame Entire City Scene"
            className={`px-2 py-0.5 rounded text-[10px] border transition-colors flex items-center gap-1 ${
              viewMode === "fit_scene"
                ? "bg-slate-700 text-white border-slate-500 font-bold"
                : "border-slate-700 text-slate-400 hover:text-white"
            }`}
          >
            <Maximize2 className="w-3 h-3" />
            <span>Fit Scene</span>
          </button>
          <button
            onClick={() => setCameraPosition("top")}
            className={`px-2 py-0.5 rounded text-[10px] border transition-colors ${
              viewMode === "top"
                ? "bg-slate-700 text-white border-slate-500 font-bold"
                : "border-slate-700 text-slate-400 hover:text-white"
            }`}
          >
            Top (XY)
          </button>
          <button
            onClick={() => setCameraPosition("side")}
            className={`px-2 py-0.5 rounded text-[10px] border transition-colors ${
              viewMode === "side"
                ? "bg-slate-700 text-white border-slate-500 font-bold"
                : "border-slate-700 text-slate-400 hover:text-white"
            }`}
          >
            Side (XZ)
          </button>
          <button
            onClick={toggleGrid}
            title="Toggle Ground Grid"
            className={`p-1 rounded border transition-colors ${
              showGrid
                ? "bg-slate-700 text-white border-slate-500"
                : "border-slate-700 text-slate-400 hover:text-white"
            }`}
          >
            <Grid className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* 3D WebGL Canvas */}
      <div ref={mountRef} className="w-full h-[400px] cursor-grab active:cursor-grabbing" />

      {/* Floating Coordinate Labels & Overlays */}
      <div className="absolute top-12 left-3 z-10 space-y-1 pointer-events-none text-[10px] font-mono text-slate-400">
        <div className="bg-slate-900/85 px-2 py-0.5 rounded border border-slate-700/60 inline-flex items-center gap-2 text-slate-300">
          <span>+X [East] →</span>
          <span>+Y [North] ↑</span>
          <span>+Z [Up]</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 bg-slate-900/85 px-1.5 py-0.5 rounded border border-orange-500/40 text-orange-400">
            <span className="w-2 h-2 rounded-full bg-orange-500 inline-block" /> TX [
            {txPosition.map((v) => v.toFixed(1)).join(", ")}]
          </span>
          <span className="inline-flex items-center gap-1 bg-slate-900/85 px-1.5 py-0.5 rounded border border-cyan-500/40 text-cyan-400">
            <span className="w-2 h-2 rounded-sm bg-cyan-500 inline-block" /> RX [
            {rxPosition.map((v) => v.toFixed(1)).join(", ")}]
          </span>
        </div>
      </div>

      {/* Viewport Control Instructions */}
      <div className="absolute bottom-2 right-3 z-10 pointer-events-none text-[10px] font-mono text-slate-500 bg-slate-900/80 px-2 py-0.5 rounded border border-slate-800">
        Left-drag: Orbit • Right-drag: Pan • Scroll: Zoom
      </div>
    </div>
  );
}
