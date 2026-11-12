import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Grid, Eye, RefreshCw, ZoomIn } from "lucide-react";

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

export function RayTracingVisualizer3D({
  txPosition,
  rxPosition,
  paths = [],
  sceneName = "simple_reflector",
}: RayTracingVisualizer3DProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [viewMode, setViewMode] = useState<"iso" | "top" | "side">("iso");

  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);

  // Compute specular reflection point for the reflector plane (Plane at Y=10)
  // For canonical simple_reflector with plane at Y=10:
  // Virtual TX reflected across Y=10: tx_y' = 10 + (10 - tx_y)
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
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    cameraRef.current = camera;
    setCameraPosition("iso", camera);

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mountRef.current.replaceChildren(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
    scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(20, 40, 20);
    scene.add(dirLight);

    // 5. Grid Helper (Ground)
    const grid = new THREE.GridHelper(50, 50, 0x334155, 0x1e293b);
    grid.position.y = 0;
    scene.add(grid);
    gridHelperRef.current = grid;

    // 6. Draw Reflector Plane (at Y = 10)
    // In Three.js: X is East/West, Y is Up/Down, Z is North/South.
    // Sionna RT coordinates: X is East, Y is North, Z is Height (Up).
    // Mapping: Sionna [X, Y, Z] -> Three.js [X, Z, -Y]
    const toThree = (p: [number, number, number]): THREE.Vector3 => {
      return new THREE.Vector3(p[0], p[2], -p[1]);
    };

    const threeTx = toThree(txPosition);
    const threeRx = toThree(rxPosition);
    const threeRefl = toThree([reflX, reflY, reflZ]);

    // Reflector Wall Mesh (representing the planar reflector)
    const wallGeometry = new THREE.BoxGeometry(30, 8, 0.4);
    const wallMaterial = new THREE.MeshStandardMaterial({
      color: 0x223040,
      roughness: 0.4,
      metalness: 0.6,
      transparent: true,
      opacity: 0.85,
    });
    const wall = new THREE.Mesh(wallGeometry, wallMaterial);
    wall.position.set(0, 4, -planeY);
    scene.add(wall);

    // Wireframe for wall
    const wallEdges = new THREE.EdgesGeometry(wallGeometry);
    const lineMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, linewidth: 1 });
    const wallWire = new THREE.LineSegments(wallEdges, lineMat);
    wallWire.position.copy(wall.position);
    scene.add(wallWire);

    // 7. Transmitter Marker (Red/Orange Sphere)
    const txGeom = new THREE.SphereGeometry(0.7, 16, 16);
    const txMat = new THREE.MeshStandardMaterial({
      color: 0xea580c,
      emissive: 0xc84b31,
      emissiveIntensity: 0.6,
    });
    const txMesh = new THREE.Mesh(txGeom, txMat);
    txMesh.position.copy(threeTx);
    scene.add(txMesh);

    // 8. Receiver Marker (Cyan Box)
    const rxGeom = new THREE.BoxGeometry(1.2, 1.2, 1.2);
    const rxMat = new THREE.MeshStandardMaterial({
      color: 0x0284c7,
      emissive: 0x0ea5e9,
      emissiveIntensity: 0.6,
    });
    const rxMesh = new THREE.Mesh(rxGeom, rxMat);
    rxMesh.position.copy(threeRx);
    scene.add(rxMesh);

    // 9. Reflection Point Marker
    const reflGeom = new THREE.SphereGeometry(0.4, 12, 12);
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
      dashSize: 0.8,
      gapSize: 0.4,
      linewidth: 2,
    });
    const reflLine = new THREE.Line(reflLineGeom, reflLineMat);
    reflLine.computeLineDistances();
    scene.add(reflLine);

    // Animation Loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
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
      renderer.dispose();
    };
  }, [txPosition, rxPosition, sceneName]);

  const setCameraPosition = (mode: "iso" | "top" | "side", cam?: THREE.PerspectiveCamera) => {
    const c = cam || cameraRef.current;
    if (!c) return;

    if (mode === "iso") {
      c.position.set(22, 24, 30);
      c.lookAt(0, 3, 0);
    } else if (mode === "top") {
      c.position.set(0, 45, 0);
      c.lookAt(0, 0, 0);
    } else if (mode === "side") {
      c.position.set(45, 8, 0);
      c.lookAt(0, 4, 0);
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
          <span className="text-[10px] text-slate-400">Cartesian Isometric View</span>
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
            <span className="text-slate-400">PEC Reflector Plane (Y=10m)</span>
          </div>
        </div>

        <div className="text-[10px] text-slate-500">
          FOV: 45° • Projection: Isometric
        </div>
      </div>
    </div>
  );
}
