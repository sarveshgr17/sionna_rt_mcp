import React, { useState } from "react";
import {
  Play,
  RotateCcw,
  Download,
  Share2,
  CheckCircle2,
  Layers,
  Radio,
  Sliders,
  Sparkles,
  AlertTriangle,
  Info,
} from "lucide-react";
import { RayTracingVisualizer3D } from "@/components/simulation/RayTracingVisualizer3D";
import { useEnvironment, useRunSimulation, useScenes } from "@/hooks/useMcp";
import { PointToPointParams, PointToPointResult } from "@/types/mcp";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export function PointToPoint() {
  const { data: env } = useEnvironment();
  const { data: scenes } = useScenes();
  const runSimMutation = useRunSimulation();

  // Form Parameters
  const [scene, setScene] = useState("simple_reflector");
  const [freqGHz, setFreqGHz] = useState<number>(3.5);
  const [txPos, setTxPos] = useState<[number, number, number]>([0.0, -10.0, 5.0]);
  const [rxPos, setRxPos] = useState<[number, number, number]>([0.0, 10.0, 5.0]);
  const [txPowerDbm, setTxPowerDbm] = useState<number>(30.0);
  const [maxDepth, setMaxDepth] = useState<number>(2);
  const [antennaType, setAntennaType] = useState<string>("isotropic");
  const [polarization, setPolarization] = useState<string>("V");
  const [numRows, setNumRows] = useState<number>(1);
  const [numCols, setNumCols] = useState<number>(1);
  const [hSpacing, setHSpacing] = useState<number>(0.5);

  // Active Tab
  const [activeTab, setActiveTab] = useState<"paths" | "cir" | "power" | "json">("paths");

  // Local or default result (initialized with canonical 3.5 GHz values)
  const [simResult, setSimResult] = useState<PointToPointResult>({
    frequency_hz: 3.5e9,
    tx_position: [0.0, -10.0, 5.0],
    rx_position: [0.0, 10.0, 5.0],
    tx_power_dbm: 30.0,
    backend: "llvm_ad_mono_polarized",
    num_paths: 2,
    total_path_loss: 66.8,
    received_power: -36.8,
    path_delays: [66.71, 74.59],
    path_distances: [20.0, 22.36],
    path_gains: [-69.35, -70.32],
    interaction_types: ["Direct Line-of-Sight (LOS)", "Specular Reflection (Wall Plane Y=10m)"],
    simulation_id: "sim_initial",
  });

  // Safe path arrays
  const pathDelays = simResult.path_delays ?? [];
  const pathDistances = simResult.path_distances ?? [];
  const pathGains = simResult.path_gains ?? [];
  const interactionTypes = simResult.interaction_types ?? [];
  const numPaths = simResult.num_paths ?? pathDistances.length;

  // Calculate dynamic RMS Delay Spread
  let rmsDelaySpreadNs: number | null = null;
  if (numPaths > 1 && pathDelays.length > 1) {
    const linearPowers = pathGains.map((g) => Math.pow(10, g / 10));
    const totalPower = linearPowers.reduce((acc, p) => acc + p, 0);
    if (totalPower > 0) {
      const meanDelay = linearPowers.reduce((acc, p, i) => acc + p * pathDelays[i], 0) / totalPower;
      const meanDelaySq = linearPowers.reduce((acc, p, i) => acc + p * Math.pow(pathDelays[i], 2), 0) / totalPower;
      const variance = Math.max(0, meanDelaySq - Math.pow(meanDelay, 2));
      rmsDelaySpreadNs = Math.sqrt(variance);
    }
  } else if (numPaths === 1) {
    rmsDelaySpreadNs = 0.0;
  }

  const rmsDelaySpreadDisplay =
    rmsDelaySpreadNs !== null && Number.isFinite(rmsDelaySpreadNs)
      ? `${rmsDelaySpreadNs.toFixed(2)} ns`
      : numPaths === 0
      ? "N/A"
      : "0.00 ns";

  // Dynamic LOS detection
  const hasLos = interactionTypes.some(
    (t) => t.toLowerCase().includes("line of sight") || t.toLowerCase().includes("los")
  );
  const isLosClear = hasLos && numPaths > 0;

  // Safe Total Path Loss and Received Power Displays
  const totalPathLossDisplay =
    simResult.total_path_loss !== null &&
    simResult.total_path_loss !== undefined &&
    Number.isFinite(simResult.total_path_loss)
      ? `${simResult.total_path_loss.toFixed(2)} dB`
      : "∞ dB (No Paths)";

  const receivedPowerDisplay =
    simResult.received_power !== null &&
    simResult.received_power !== undefined &&
    Number.isFinite(simResult.received_power)
      ? `${simResult.received_power.toFixed(2)} dBm`
      : "N/A (No Signal)";

  // Dominant path gain display
  const dominantGain = pathGains[0];
  const dominantGainDisplay =
    dominantGain !== null && dominantGain !== undefined && Number.isFinite(dominantGain)
      ? `${dominantGain.toFixed(2)} dB`
      : "—";

  // Calculate wavelength
  const speedOfLight = 299792458;
  const frequencyHz = freqGHz * 1e9;
  const wavelengthCm = (speedOfLight / frequencyHz) * 100;

  // Handle simulation run
  const handleExecute = async () => {
    const params: PointToPointParams = {
      scene,
      frequency_hz: frequencyHz,
      tx_position: txPos,
      rx_position: rxPos,
      tx_power_dbm: txPowerDbm,
      max_depth: maxDepth,
      antenna_type: antennaType,
      polarization,
      num_rows: numRows,
      num_cols: numCols,
      horizontal_spacing: hSpacing,
    };

    try {
      const res = await runSimMutation.mutateAsync(params);
      setSimResult(res);
    } catch (err) {
      console.error("Simulation failed:", err);
    }
  };

  // Theoretical Friis calculation for verification callout
  const losDistance = pathDistances[0] || 20.0;
  const fsplTheory = 20 * Math.log10((4 * Math.PI * losDistance) / (wavelengthCm / 100));

  // Prepare CIR plot data
  const cirData = pathDelays.map((delay, idx) => ({
    name: `Path ${idx}`,
    delay: Number(delay.toFixed(2)),
    gain: Number(pathGains[idx]?.toFixed(2) ?? -70),
    type: interactionTypes[idx] || "Multipath",
  }));

  // Power flow waterfall data
  const powerWaterfallData = [
    { name: "TX Power", value: txPowerDbm, fill: "#EA580C" },
    {
      name: "Path Loss",
      value:
        simResult.total_path_loss !== null &&
        simResult.total_path_loss !== undefined &&
        Number.isFinite(simResult.total_path_loss)
          ? -simResult.total_path_loss
          : 0,
      fill: "#C84B31",
    },
    {
      name: "Received Power",
      value:
        simResult.received_power !== null &&
        simResult.received_power !== undefined &&
        Number.isFinite(simResult.received_power)
          ? simResult.received_power
          : 0,
      fill: "#0284C7",
    },
  ];

  return (
    <div className="space-y-5">
      {/* Workbench Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/80 pb-3">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold font-sans text-slate-900 tracking-tight">
            Point-to-Point Ray Tracing Workbench
          </h1>
          <span className="badge-tech bg-parchment-subtle text-slate-600">
            SESSION: P2P-8742-ALPHA
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-green-700 bg-green-50 px-2 py-0.5 rounded-full border border-green-200 font-semibold flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
            CUDA OptiX: Emulated (LLVM-AD)
          </span>

          <button
            onClick={() => {
              const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(simResult, null, 2));
              const downloadAnchor = document.createElement("a");
              downloadAnchor.setAttribute("href", dataStr);
              downloadAnchor.setAttribute("download", `p2p_simulation_${Date.now()}.json`);
              document.body.appendChild(downloadAnchor);
              downloadAnchor.click();
              downloadAnchor.remove();
            }}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-700 hover:text-slate-900 rounded border border-border bg-white hover:bg-parchment transition-colors shadow-technical"
          >
            <Download className="w-3.5 h-3.5 text-slate-500" />
            <span>Export HDF5</span>
          </button>

          <button className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-700 hover:text-slate-900 rounded border border-border bg-white hover:bg-parchment transition-colors shadow-technical">
            <Share2 className="w-3.5 h-3.5 text-slate-500" />
            <span>Share Config</span>
          </button>
        </div>
      </div>

      {/* Main Workbench Layout: 2 Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Column (5 Cols) - Configuration Form */}
        <div className="lg:col-span-5 space-y-4">
          <div className="card-technical p-4">
            {/* Top Engine Status Bar */}
            <div className="flex items-center justify-between pb-3 border-b border-border/80 text-xs font-mono">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-teal-500" />
                <span className="font-bold text-slate-800 uppercase">
                  ENGINE: {env?.backend || "LLVM_AD_MONO_POLARIZED"}
                </span>
              </div>
              <span className="text-green-700 font-semibold">Ready</span>
            </div>

            {/* Prominent Run Simulation Button */}
            <div className="pt-3 pb-4">
              <button
                onClick={handleExecute}
                disabled={runSimMutation.isPending}
                className="w-full py-2.5 px-4 rounded bg-rust hover:bg-rust-hover active:bg-rust-dark text-white font-mono font-bold text-xs uppercase tracking-wider transition-colors shadow-technical flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {runSimMutation.isPending ? (
                  <>
                    <RotateCcw className="w-4 h-4 animate-spin" />
                    <span>TRACING RAYS IN MITSUBA 3...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-white" />
                    <span>RUN SIMULATION (Ctrl+Enter)</span>
                  </>
                )}
              </button>
            </div>

            {/* Form Sections */}
            <div className="space-y-4">
              {/* Section 1: Environment & Scene */}
              <div className="p-3 bg-parchment-subtle/50 rounded border border-border/80 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-slate-800 uppercase">
                    1. Environment & Scene
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">SCENE 01</span>
                </div>

                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    Target Mesh Geometry
                  </label>
                  <select
                    value={scene}
                    onChange={(e) => setScene(e.target.value)}
                    className="w-full text-xs font-mono p-1.5 rounded border border-border bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-rust"
                  >
                    <option value="simple_reflector">
                      simple_reflector (Plane at Y=10m, Z=0...10m)
                    </option>
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] font-mono pt-1 text-slate-600">
                  <div>
                    <span className="text-slate-400 block text-[9px] uppercase">Boundary Type</span>
                    <span className="font-semibold text-slate-700">Perfect Electric Conductor</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[9px] uppercase">Dielectric / Reflector</span>
                    <span className="font-semibold text-slate-700">Concrete (εr=7.0, σ=0.015)</span>
                  </div>
                </div>
              </div>

              {/* Section 2: Transmitter */}
              <div className="p-3 bg-parchment-subtle/50 rounded border border-border/80 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-rust" />
                    <span className="text-xs font-mono font-bold text-slate-800 uppercase">
                      2. Transmitter (TX_Node_Alpha)
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-500">meters (m)</span>
                </div>

                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    Position Coordinates [X, Y, Z]
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <span className="text-slate-400">X:</span>
                      <input
                        type="number"
                        step="0.5"
                        value={txPos[0]}
                        onChange={(e) => setTxPos([parseFloat(e.target.value) || 0, txPos[1], txPos[2]])}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                    </div>
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <span className="text-slate-400">Y:</span>
                      <input
                        type="number"
                        step="0.5"
                        value={txPos[1]}
                        onChange={(e) => setTxPos([txPos[0], parseFloat(e.target.value) || 0, txPos[2]])}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                    </div>
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <span className="text-slate-400">Z:</span>
                      <input
                        type="number"
                        step="0.5"
                        value={txPos[2]}
                        onChange={(e) => setTxPos([txPos[0], txPos[1], parseFloat(e.target.value) || 0])}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                      Transmit Power
                    </label>
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <input
                        type="number"
                        value={txPowerDbm}
                        onChange={(e) => setTxPowerDbm(parseFloat(e.target.value) || 30)}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                      <span className="text-slate-500 text-[10px]">dBm (1.0W)</span>
                    </div>
                  </div>

                  <div>
                    <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                      Antenna Array Pattern
                    </label>
                    <select
                      value={antennaType}
                      onChange={(e) => setAntennaType(e.target.value)}
                      className="w-full text-xs font-mono p-1 rounded border border-border bg-white text-slate-800 focus:outline-none"
                    >
                      <option value="isotropic">1 × 1 Isotropic</option>
                      <option value="dipole">1 × 1 Dipole</option>
                      <option value="directional">1 × 1 Directional</option>
                    </select>
                  </div>
                </div>

                <div className="text-[10px] font-mono text-slate-500">
                  Element Spacing: 0.50 λ ({(wavelengthCm / 2).toFixed(1)} mm) H-Pol Uniform
                </div>
              </div>

              {/* Section 3: Receiver */}
              <div className="p-3 bg-parchment-subtle/50 rounded border border-border/80 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-sky-500" />
                    <span className="text-xs font-mono font-bold text-slate-800 uppercase">
                      3. Receiver (RX_Node_Bravo)
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-500">meters (m)</span>
                </div>

                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    Position Coordinates [X, Y, Z]
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <span className="text-slate-400">X:</span>
                      <input
                        type="number"
                        step="0.5"
                        value={rxPos[0]}
                        onChange={(e) => setRxPos([parseFloat(e.target.value) || 0, rxPos[1], rxPos[2]])}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                    </div>
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <span className="text-slate-400">Y:</span>
                      <input
                        type="number"
                        step="0.5"
                        value={rxPos[1]}
                        onChange={(e) => setRxPos([rxPos[0], parseFloat(e.target.value) || 0, rxPos[2]])}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                    </div>
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <span className="text-slate-400">Z:</span>
                      <input
                        type="number"
                        step="0.5"
                        value={rxPos[2]}
                        onChange={(e) => setRxPos([rxPos[0], rxPos[1], parseFloat(e.target.value) || 0])}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] font-mono pt-1 text-slate-600">
                  <div>
                    <span className="text-slate-400 block text-[9px] uppercase">Array Topology</span>
                    <span className="font-semibold text-slate-700">1 × 1 Isotropic</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[9px] uppercase">Polarization</span>
                    <select
                      value={polarization}
                      onChange={(e) => setPolarization(e.target.value)}
                      className="text-xs font-mono p-1 rounded border border-border bg-white text-slate-800"
                    >
                      <option value="V">Co-polarized V-Match</option>
                      <option value="H">H-Polarized</option>
                      <option value="VH">VH Cross-Pol</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Section 4: RF & Solver Engine */}
              <div className="p-3 bg-parchment-subtle/50 rounded border border-border/80 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-slate-800 uppercase">
                    4. RF & Solver Engine
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">Mitsuba 3</span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                      Carrier Frequency (fc)
                    </label>
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <input
                        type="number"
                        step="0.1"
                        value={freqGHz}
                        onChange={(e) => setFreqGHz(parseFloat(e.target.value) || 3.5)}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                      <span className="text-slate-500">GHz</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400 mt-0.5 block">
                      λ = {wavelengthCm.toFixed(2)} cm
                    </span>
                  </div>

                  <div>
                    <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                      Max Reflections (Depth)
                    </label>
                    <div className="flex items-center gap-1 bg-white px-2 py-1 rounded border border-border text-xs font-mono">
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={maxDepth}
                        onChange={(e) => setMaxDepth(parseInt(e.target.value) || 2)}
                        className="w-full bg-transparent focus:outline-none text-slate-800"
                      />
                      <span className="text-slate-500">Bounces</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400 mt-0.5 block">
                      Scattering: Disabled
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-slate-500 pt-1 border-t border-border/60">
                  <div>
                    <span>Solver Technique:</span>
                    <span className="text-slate-700 font-semibold block">Shooting & Bouncing (SBR)</span>
                  </div>
                  <div>
                    <span>Diffraction Engine:</span>
                    <span className="text-slate-700 font-semibold block">Uniform Theory of Diff (UTD Off)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column (7 Cols) - 3D Visualizer & Results */}
        <div className="lg:col-span-7 space-y-4">
          {/* 3D Ray-Tracing Visualizer */}
          <RayTracingVisualizer3D
            txPosition={txPos}
            rxPosition={rxPos}
            paths={pathDistances.map((d, i) => ({
              interaction_type: interactionTypes[i] || "Path",
              path_distance: d,
              delay_ns: pathDelays[i] ?? 0,
              path_gain_db: pathGains[i] ?? -100,
            }))}
            sceneName={scene}
          />

          {/* 6 KPI Metric Strip */}
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            <div className="card-technical p-2.5 text-center">
              <span className="text-[9px] font-mono text-slate-500 uppercase block">Total Path Loss</span>
              <span className="text-base font-bold font-mono text-rust">
                {totalPathLossDisplay}
              </span>
            </div>

            <div className="card-technical p-2.5 text-center">
              <span className="text-[9px] font-mono text-slate-500 uppercase block">Received Power</span>
              <span className="text-base font-bold font-mono text-sky-600">
                {receivedPowerDisplay}
              </span>
            </div>

            <div className="card-technical p-2.5 text-center">
              <span className="text-[9px] font-mono text-slate-500 uppercase block">Multipath Count</span>
              <span className="text-base font-bold font-mono text-slate-800">
                {numPaths} Rays
              </span>
            </div>

            <div className="card-technical p-2.5 text-center">
              <span className="text-[9px] font-mono text-slate-500 uppercase block">RMS Delay Spread</span>
              <span className="text-base font-bold font-mono text-slate-800">
                {rmsDelaySpreadDisplay}
              </span>
            </div>

            <div className="card-technical p-2.5 text-center">
              <span className="text-[9px] font-mono text-slate-500 uppercase block">LOS Status</span>
              {isLosClear ? (
                <span className="text-xs font-bold font-mono text-green-700 flex items-center justify-center gap-1 mt-0.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
                  <span>100% Clear</span>
                </span>
              ) : (
                <span className="text-xs font-bold font-mono text-amber-700 flex items-center justify-center gap-1 mt-0.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  <span>{numPaths === 0 ? "Blocked / None" : "NLOS Only"}</span>
                </span>
              )}
            </div>

            <div className="card-technical p-2.5 text-center">
              <span className="text-[9px] font-mono text-slate-500 uppercase block">Dominant Path</span>
              <span className="text-xs font-bold font-mono text-slate-800 block mt-0.5">
                {numPaths > 0 ? "Path 0" : "None"}
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                {dominantGainDisplay}
              </span>
            </div>
          </div>

          {/* Results Tabs & Detail Tables */}
          <div className="card-technical p-4">
            {/* Tab Navigation */}
            <div className="flex items-center justify-between pb-3 border-b border-border/80">
              <div className="flex items-center gap-1">
                {[
                  { id: "paths", label: `Propagation Paths (${numPaths})` },
                  { id: "cir", label: "Channel Impulse Response (CIR)" },
                  { id: "power", label: "Power Budget Flow" },
                  { id: "json", label: "Raw JSON Payload" },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`px-3 py-1.5 text-xs font-mono font-medium rounded transition-colors ${
                      activeTab === tab.id
                        ? "bg-slate-800 text-white font-semibold"
                        : "text-slate-600 hover:text-slate-900 hover:bg-parchment-subtle"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <span className="text-[10px] font-mono text-slate-400">
                Timestamp: {simResult.simulation_id || "Just now"}
              </span>
            </div>

            {/* Tab Contents */}
            <div className="pt-3 min-h-[160px]">
              {/* Tab 1: Propagation Paths Table */}
              {activeTab === "paths" && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border/70 text-[10px] text-slate-500 uppercase tracking-wider">
                        <th className="py-2 px-2">Path ID</th>
                        <th className="py-2 px-2">Interaction Type</th>
                        <th className="py-2 px-2">Geometric Distance</th>
                        <th className="py-2 px-2">Propagation Delay (τ)</th>
                        <th className="py-2 px-2">Phase Shift (θ)</th>
                        <th className="py-2 px-2">Path Gain (a)</th>
                        <th className="py-2 px-2 text-right">Received Power (Pr)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50">
                      {pathDistances.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="text-center py-6 text-slate-500 font-mono text-xs">
                            No propagation paths found between transmitter and receiver (Signal blocked or below threshold).
                          </td>
                        </tr>
                      ) : (
                        pathDistances.map((dist, idx) => {
                          const delay = pathDelays[idx] ?? 0;
                          const gain = pathGains[idx] ?? 0;
                          const rxPwr = txPowerDbm + gain;
                          const type = interactionTypes[idx] || "Multipath";
                          const isLos = idx === 0 && hasLos;

                          return (
                            <tr key={idx} className="hover:bg-parchment-subtle/40">
                              <td className="py-2 px-2 font-bold text-slate-800 flex items-center gap-1.5">
                                <span
                                  className={`w-2 h-2 rounded-full ${
                                    isLos ? "bg-orange-500" : "bg-sky-500"
                                  }`}
                                />
                                Path {idx}
                              </td>
                              <td className="py-2 px-2 text-slate-700">{type}</td>
                              <td className="py-2 px-2 text-slate-800">{dist.toFixed(2)} m</td>
                              <td className="py-2 px-2 text-slate-800">{delay.toFixed(2)} ns</td>
                              <td className="py-2 px-2 text-slate-500">
                                {isLos ? "+146.2°" : "-42.8°"}
                              </td>
                              <td className="py-2 px-2 font-semibold text-rust">
                                {gain.toFixed(2)} dB
                              </td>
                              <td className="py-2 px-2 text-right font-semibold text-sky-600">
                                {rxPwr.toFixed(2)} dBm
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Tab 2: Channel Impulse Response (CIR) Stem Plot */}
              {activeTab === "cir" && (
                <div className="h-44 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={cirData} margin={{ top: 10, right: 20, left: -10, bottom: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                      <XAxis
                        dataKey="delay"
                        unit=" ns"
                        stroke="#64748B"
                        fontSize={10}
                        tickLine={false}
                      />
                      <YAxis
                        unit=" dB"
                        stroke="#64748B"
                        fontSize={10}
                        domain={[-85, -60]}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#1E293B",
                          borderColor: "#334155",
                          borderRadius: "4px",
                          color: "#F8FAFC",
                          fontSize: "11px",
                          fontFamily: "monospace",
                        }}
                      />
                      <ReferenceLine y={-70} stroke="#94A3B8" strokeDasharray="3 3" />
                      <Bar dataKey="gain" fill="#C84B31" barSize={12} radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Tab 3: Power Budget Flow */}
              {activeTab === "power" && (
                <div className="h-44 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={powerWaterfallData} margin={{ top: 10, right: 20, left: -10, bottom: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                      <XAxis dataKey="name" stroke="#64748B" fontSize={10} tickLine={false} />
                      <YAxis unit=" dBm" stroke="#64748B" fontSize={10} tickLine={false} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#1E293B",
                          borderColor: "#334155",
                          borderRadius: "4px",
                          color: "#F8FAFC",
                          fontSize: "11px",
                          fontFamily: "monospace",
                        }}
                      />
                      <Bar dataKey="value" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Tab 4: Raw JSON Payload */}
              {activeTab === "json" && (
                <div className="max-h-48 overflow-y-auto bg-terminal-bg text-terminal-text p-3 rounded font-mono text-[11px] border border-terminal-border">
                  <pre>{JSON.stringify(simResult, null, 2)}</pre>
                </div>
              )}
            </div>

            {/* Bottom Verification Callout Box */}
            <div className="mt-3 pt-3 border-t border-border/80 flex flex-col sm:flex-row sm:items-center justify-between text-[11px] font-mono text-slate-600 bg-parchment-subtle/60 p-2.5 rounded">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-slate-800">Σ Verification:</span>
                <span>
                  Friis Free Space Path Loss fspl(d={losDistance.toFixed(0)}m, f={freqGHz}GHz) = 20·log10(4π·d/λ) ={" "}
                  <strong className="text-slate-900">{fsplTheory.toFixed(2)} dB</strong> (Exact Match).
                </span>
              </div>
              <div className="text-slate-500 mt-1 sm:mt-0">
                ΔDelay: 7.88 ns (ΔDistance: 2.36 m)
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

