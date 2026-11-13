import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Grid, Eye, RefreshCw, ZoomIn, Layers } from "lucide-react";
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

// Coordinate mapping helper: Sionna RT [X, Y, Z] -> Three.js [X, Z, -Y]
// (In Three.js: Y is up, Z is depth; in Sionna RT: Z is up, Y is north)
const toThree = (p: [number, number, number]): THREE.Vector3 => {
  return new THREE.Vector3(p[0], p[2], -p[1]);
};

const ITU_PALETTE: Record<
  string,
  { color: number; roughness: number; metalness: number; opacity?: number }
> = {
  marble: { color: 0xb5a793, roughness: 0.6, metalness: 0.1 },
  metal: { color: 0x475569, roughness: 0.3, metalness: 0.8 },
  concrete: { color: 0x64748b, roughness: 0.8, metalness: 0.1 },
  brick: { color: 0x9a3412, roughness: 0.7, metalness: 0.1 },
  glass: { color: 0x38bdf8, roughness: 0.1, metalness: 0.9, opacity: 0.6 },
  wood: { color: 0x78350f, roughness: 0.8, metalness: 0.05 },
  "itu-radio-material": { color: 0x334155, roughness: 0.4, metalness: 0.6 },
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
  const [viewMode, setViewMode] = useState<"iso" | "top" | "side">("iso");

  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);

  // Fetch real 3D mesh geometry for the active scene from backend adapter
  const { data: geomData, isLoading: geomLoading } = useSceneGeometry(sceneName);

  // Compute specular reflection point for the reflector plane (Plane at Y=10)
  const planeY = 10.0;
  const reflTxY = 2 * planeY - txPosition[1];
  const t = (planeY - txPosition[1]) / (rxPosition[1] - txPosition[1] + 0.0001 || 1);
  const reflX = txPosition[0] + (rxPosition[0] - txPosition[0]) * 0.5; // midpoint reflection
  const reflY = planeY;
  const reflZ = (txPosition[2] + rxPosition[2]) / 2;

  // Distances
  const losDistance = Math.sqrt(
    Math.pow(rxPosition[0] - txPosition[0], 2) +
    Math.pow(rxPosition[1] - txPosition[1], 2) +
    Math.pow(rxPosition[2] - txPosition[2], 2)
  );

  const reflDistance =
    Math.sqrt(
      Math.pow(reflX - txPosition[0], 2) +
      Math.pow(reflY - txPosition[1], 2) +
      Math.pow(reflZ - txPosition[2], 2)
    ) +
    Math.sqrt(
      Math.pow(rxPosition[0] - reflX, 2) +
      Math.pow(rxPosition[1] - reflY, 2) +
      Math.pow(rxPosition[2] - reflZ, 2)
    );

  useEffect(() => {
    if (!mountRef.current) return;
    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight || 340;

    // 1. Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#14181F");
    sceneRef.current = scene;

    // 2. Camera setup (Isometric perspective)
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 5000);
    cameraRef.current = camera;

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mountRef.current.replaceChildren(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.1);
    scene.add(ambientLight);
    const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.9);
    dirLight1.position.set(100, 200, 100);
    scene.add(dirLight1);
    const dirLight2 = new THREE.DirectionalLight(0x94a3b8, 0.4);
    dirLight2.position.set(-100, -50, -100);
    scene.add(dirLight2);

    // 5. Node Vectors & Framing Dimensions
    const threeTx = toThree(txPosition);
    const threeRx = toThree(rxPosition);
    const threeRefl = toThree([reflX, reflY, reflZ]);

    const midX = (threeTx.x + threeRx.x) / 2;
    const midY = (threeTx.y + threeRx.y) / 2;
    const midZ = (threeTx.z + threeRx.z) / 2;
    const threeMid = new THREE.Vector3(midX, midY, midZ);
    const span = Math.max(threeTx.distanceTo(threeRx), 30);

    // Dynamic Ground Grid Helper
    const gridSize = Math.max(80, Math.ceil((span * 2.5) / 10) * 10);
    const grid = new THREE.GridHelper(
      gridSize,
      Math.min(60, Math.max(20, Math.floor(gridSize / 2))),
      0x334155,
      0x1e293b
    );
    grid.position.set(threeMid.x, 0, threeMid.z);
    scene.add(grid);
    gridHelperRef.current = grid;

    // 6. Draw Real 3D Mesh Geometry (from Sionna RT Backend)
    if (geomData && geomData.meshes && geomData.meshes.length > 0) {
      geomData.meshes.forEach((m: SceneMesh) => {
        if (!m.vertices || m.vertices.length === 0) return;
        const geom = new THREE.BufferGeometry();
        geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(m.vertices), 3));
        if (m.faces && m.faces.length > 0) {
          geom.setIndex(m.faces);
        }
        geom.computeVertexNormals();

        const pal = ITU_PALETTE[m.material.toLowerCase()] || {
          color: 0x475569,
          roughness: 0.6,
          metalness: 0.3,
        };

        const mat = new THREE.MeshStandardMaterial({
          color: pal.color,
          roughness: pal.roughness,
          metalness: pal.metalness,
          transparent: pal.opacity !== undefined,
          opacity: pal.opacity ?? 0.88,
          side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geom, mat);
        scene.add(mesh);

        // Add edge wireframe lines for buildings with moderate polycounts
        if (m.faces && m.faces.length < 25000) {
          const edges = new THREE.EdgesGeometry(geom, 35);
          const wireMat = new THREE.LineBasicMaterial({
            color: 0x94a3b8,
            transparent: true,
            opacity: 0.35,
          });
          const wire = new THREE.LineSegments(edges, wireMat);
          scene.add(wire);
        }
      });
    } else {
      // Fallback schematic geometry while loading or if offline
      const addBuilding = (
        x: number,
        y: number,
        z: number,
        w: number,
        h: number,
        d: number,
        color = 0x223040,
        wireColor = 0x38bdf8
      ) => {
        const geom = new THREE.BoxGeometry(w, h, d);
        const mat = new THREE.MeshStandardMaterial({
          color,
          roughness: 0.5,
          metalness: 0.4,
          transparent: true,
          opacity: 0.85,
        });
        const mesh = new THREE.Mesh(geom, mat);
        mesh.position.set(x, y + h / 2, z);
        scene.add(mesh);

        const edges = new THREE.EdgesGeometry(geom);
        const lMat = new THREE.LineBasicMaterial({ color: wireColor, linewidth: 1 });
        const wire = new THREE.LineSegments(edges, lMat);
        wire.position.copy(mesh.position);
        scene.add(wire);
      };

      if (sceneName === "munich") {
        addBuilding(20, 0, -40, 16, 50, 16, 0x2d3748, 0xf6ad55);
        addBuilding(-10, 0, -40, 16, 50, 16, 0x2d3748, 0xf6ad55);
        addBuilding(5, 0, -55, 30, 28, 45, 0x1f2937, 0x64748b);
        addBuilding(-45, 0, -10, 25, 20, 25, 0x1e293b, 0x38bdf8);
      } else if (sceneName === "san_francisco") {
        addBuilding(0, 0, 0, 100, 30, 100, 0x2d3748, 0x38bdf8);
        addBuilding(50, 0, -50, 60, 45, 60, 0x1f2937, 0xf6ad55);
        addBuilding(-60, 0, 40, 70, 35, 70, 0x1e293b, 0x64748b);
      } else if (sceneName === "simple_street_canyon") {
        addBuilding(0, 0, -18, 90, 25, 12, 0x1e293b, 0x38bdf8);
        addBuilding(0, 0, 18, 90, 25, 12, 0x1e293b, 0x38bdf8);
      } else {
        addBuilding(0, 0, -planeY, 30, 8, 0.4, 0x223040, 0x38bdf8);
      }
    }

    // 7. Transmitter Marker (Red/Orange Sphere)
    const txGeom = new THREE.SphereGeometry(Math.max(0.7, span * 0.02), 16, 16);
    const txMat = new THREE.MeshStandardMaterial({
      color: 0xea580c,
      emissive: 0xc84b31,
      emissiveIntensity: 0.7,
    });
    const txMesh = new THREE.Mesh(txGeom, txMat);
    txMesh.position.copy(threeTx);
    scene.add(txMesh);

    // 8. Receiver Marker (Cyan Box)
    const rxBoxSize = Math.max(1.2, span * 0.035);
    const rxGeom = new THREE.BoxGeometry(rxBoxSize, rxBoxSize, rxBoxSize);
    const rxMat = new THREE.MeshStandardMaterial({
      color: 0x0284c7,
      emissive: 0x0ea5e9,
      emissiveIntensity: 0.7,
    });
    const rxMesh = new THREE.Mesh(rxGeom, rxMat);
    rxMesh.position.copy(threeRx);
    scene.add(rxMesh);

    // 9. Reflection Point Marker
    const reflGeom = new THREE.SphereGeometry(Math.max(0.4, span * 0.015), 12, 12);
    const reflMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
    const reflMesh = new THREE.Mesh(reflGeom, reflMat);
    reflMesh.position.copy(threeRefl);
    scene.add(reflMesh);

    // 10. Line of Sight (LOS) Ray (Orange Solid Line)
    const losPoints = [threeTx, threeRx];
    const losGeom = new THREE.BufferGeometry().setFromPoints(losPoints);
    const losMat = new THREE.LineBasicMaterial({ color: 0xea580c, linewidth: 3 });
    const losLine = new THREE.Line(losGeom, losMat);
    scene.add(losLine);

    // 11. Specular Reflected Ray (Cyan Dashed Line)
    const reflPoints = [threeTx, threeRefl, threeRx];
    const reflLineGeom = new THREE.BufferGeometry().setFromPoints(reflPoints);
    const reflLineMat = new THREE.LineDashedMaterial({
      color: 0x0ea5e9,
      dashSize: Math.max(0.8, span * 0.02),
      gapSize: Math.max(0.4, span * 0.01),
      linewidth: 2,
    });
    const reflLine = new THREE.Line(reflLineGeom, reflLineMat);
    reflLine.computeLineDistances();
    scene.add(reflLine);

    // 12. OrbitControls for Interactive Pan, Rotate, and Zoom
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;
    controls.target.set(threeMid.x, threeMid.y, threeMid.z);
    controlsRef.current = controls;

    // Position Camera initially
    setCameraPosition("iso", camera, controls);

    // Animation Loop
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
      const newHeight = mountRef.current.clientHeight || 340;
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
  }, [txPosition, rxPosition, sceneName, geomData]);

  const setCameraPosition = (
    mode: "iso" | "top" | "side",
    cam?: THREE.PerspectiveCamera,
    ctrls?: OrbitControls
  ) => {
    const c = cam || cameraRef.current;
    const ctrl = ctrls || controlsRef.current;
    if (!c) return;

    const threeTx = toThree(txPosition);
    const threeRx = toThree(rxPosition);
    const midX = (threeTx.x + threeRx.x) / 2;
    const midY = (threeTx.y + threeRx.y) / 2;
    const midZ = (threeTx.z + threeRx.z) / 2;
    const span = Math.max(threeTx.distanceTo(threeRx), 30);

    if (mode === "iso") {
      c.position.set(midX + span * 1.1, midY + span * 0.9, midZ + span * 1.2);
    } else if (mode === "top") {
      c.position.set(midX, midY + span * 1.8, midZ);
    } else if (mode === "side") {
      c.position.set(midX + span * 1.8, midY + span * 0.3, midZ);
    }
    c.lookAt(midX, midY, midZ);
    if (ctrl) {
      ctrl.target.set(midX, midY, midZ);
      ctrl.update();
    }
    setViewMode(mode);
  };

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
          ) : geomData ? (
            <span className="text-[10px] font-mono text-teal-400 bg-teal-950/60 border border-teal-800/80 px-1.5 py-0.5 rounded flex items-center gap-1">
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
            onClick={() => setCameraPosition("iso")}
            className={`px-2 py-0.5 rounded text-[10px] border transition-colors ${
              viewMode === "iso"
                ? "bg-slate-700 text-white border-slate-500 font-bold"
                : "border-slate-700 text-slate-400 hover:text-white"
            }`}
          >
            Reset Camera
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
      <div ref={mountRef} className="w-full h-[320px] cursor-grab active:cursor-grabbing" />

      {/* Floating Coordinate Labels & Overlays */}
      <div className="absolute top-12 left-3 z-10 space-y-1 pointer-events-none text-[10px] font-mono text-slate-400">
        <div className="bg-slate-900/80 px-2 py-0.5 rounded border border-slate-700/60 inline-block text-slate-300">
          +X [East] → +Y [North] ↑ +Z [Up]
        </div>
      </div>

      {/* In-Canvas Nodes Telemetry Badges */}
      <div className="absolute top-20 left-6 z-10 pointer-events-none text-[10px] font-mono">
        <div className="bg-slate-900/90 border border-orange-500/50 text-orange-400 px-2 py-0.5 rounded shadow">
          TX: [{txPosition.join(", ")}]m
        </div>
      </div>

      <div className="absolute top-20 right-6 z-10 pointer-events-none text-[10px] font-mono">
        <div className="bg-slate-900/90 border border-sky-500/50 text-sky-400 px-2 py-0.5 rounded shadow">
          RX: [{rxPosition.join(", ")}]m
        </div>
      </div>

      {/* Bottom In-Canvas Legend */}
      <div className="absolute bottom-2 left-3 right-3 z-10 px-3 py-1.5 bg-terminal-surface/90 backdrop-blur rounded border border-terminal-border flex items-center justify-between text-[11px] font-mono text-slate-300">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-orange-500 inline-block" />
            <span className="text-orange-400">Direct LOS ({losDistance.toFixed(2)} m)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 border-b border-dashed border-sky-400 inline-block" />
            <span className="text-sky-400">Specular Refl ({reflDistance.toFixed(2)} m)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 bg-slate-600 rounded-sm inline-block" />
            <span className="text-slate-400">
              {sceneName === "munich"
                ? "Munich Urban Macro (Frauenkirche, St. Peter, 38k Faces)"
                : sceneName === "san_francisco"
                ? "San Francisco Coastal & Urban Terrain (268k Faces)"
                : sceneName === "simple_street_canyon"
                ? "3GPP Urban Micro Canyon Facades"
                : "Real 3D Mesh Geometry"}
            </span>
          </div>
        </div>

        <div className="text-[10px] text-slate-500">
          Left-Drag: Rotate • Right-Drag: Pan • Scroll: Zoom
        </div>
      </div>
    </div>
  );
}
