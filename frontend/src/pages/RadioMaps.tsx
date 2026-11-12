import React, { useState } from "react";
import {
  Map,
  Play,
  RotateCcw,
  Download,
  CheckCircle2,
  Sliders,
  Layers,
  Sparkles,
  ArrowRight,
  Eye,
  Info,
} from "lucide-react";
import { useGenerateRadioMap, useScenes } from "@/hooks/useMcp";
import { RadioMapParams, RadioMapResult } from "@/types/mcp";
import { mcpClient } from "@/services/mcp/client";

export function RadioMaps() {
  const { data: scenes } = useScenes();
  const generateMutation = useGenerateRadioMap();

  // Form State
  const [sceneName, setSceneName] = useState("simple_reflector");
  const [freqGHz, setFreqGHz] = useState<number>(3.5);
  const [txPos, setTxPos] = useState<[number, number, number]>([0.0, -10.0, 5.0]);
  const [txPowerDbm, setTxPowerDbm] = useState<number>(30.0);
  const [antennaType, setAntennaType] = useState<string>("isotropic");
  const [polarization, setPolarization] = useState<string>("V");

  // Region & Grid Resolution
  const [regionMode, setRegionMode] = useState<"auto" | "manual">("auto");
  const [autoMargin, setAutoMargin] = useState<number>(5.0);
  const [receiverHeight, setReceiverHeight] = useState<number>(1.5);
  const [cellSize, setCellSize] = useState<number>(2.0); // 2m default for snappy response

  // Ray Solver
  const [samplesPerTx, setSamplesPerTx] = useState<number>(50000); // 50k for smooth interactive execution
  const [maxDepth, setMaxDepth] = useState<number>(3);
  const [enableLos, setEnableLos] = useState<boolean>(true);
  const [enableSpecular, setEnableSpecular] = useState<boolean>(true);
  const [enableDiffraction, setEnableDiffraction] = useState<boolean>(true);
  const [enableScattering, setEnableScattering] = useState<boolean>(false);
  const [experimentName, setExperimentName] = useState<string>("Coverage Study 3.5GHz");

  // Active Heatmap View
  const [activeMetric, setActiveMetric] = useState<"rss" | "path_gain">("rss");

  // Simulation Result State
  const [result, setResult] = useState<RadioMapResult | null>(null);

  const handleGenerate = async () => {
    const params: RadioMapParams = {
      scene_name: sceneName,
      frequency_hz: freqGHz * 1e9,
      tx_position: txPos,
      tx_power_dbm: txPowerDbm,
      antenna_type: antennaType,
      polarization,
      region_mode: regionMode,
      auto_margin: autoMargin,
      auto_include_tx: true,
      receiver_height: receiverHeight,
      cell_size: cellSize,
      samples_per_tx: samplesPerTx,
      max_depth: maxDepth,
      los: enableLos,
      specular_reflection: enableSpecular,
      diffraction: enableDiffraction,
      scattering: enableScattering,
      experiment_name: experimentName,
    };

    try {
      const res = await generateMutation.mutateAsync(params);
      setResult(res);
    } catch (err) {
      console.error("Radio map generation failed:", err);
    }
  };

  const currentHeatmapPath =
    activeMetric === "rss"
      ? result?.artifact_paths?.rss_heatmap
      : result?.artifact_paths?.path_gain_heatmap;

  const heatmapUrl = currentHeatmapPath ? mcpClient.getArtifactUrl(currentHeatmapPath) : null;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/80 pb-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold font-sans text-slate-900 tracking-tight">
              2D Radio Coverage Map Generator
            </h1>
            <span className="badge-tech bg-parchment-subtle text-slate-600">
              MODULE: 02
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Execute Monte Carlo ray tracing over a 2D planar observation grid at specified receiver height.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-teal-700 bg-teal-50 px-2 py-0.5 rounded-full border border-teal-200 font-semibold flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-teal-500" />
            Grid Solver: RadioMapSolver
          </span>
        </div>
      </div>

      {/* Main 2-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Column (5 Cols) - Configuration Form */}
        <div className="lg:col-span-5 space-y-4">
          <div className="card-technical p-4 space-y-4">
            {/* Run Button */}
            <button
              onClick={handleGenerate}
              disabled={generateMutation.isPending}
              className="w-full py-2.5 px-4 rounded bg-rust hover:bg-rust-hover active:bg-rust-dark text-white font-mono font-bold text-xs uppercase tracking-wider transition-colors shadow-technical flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {generateMutation.isPending ? (
                <>
                  <RotateCcw className="w-4 h-4 animate-spin" />
                  <span>SOLVING RADIO COVERAGE MAP...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-white" />
                  <span>GENERATE RADIO MAP</span>
                </>
              )}
            </button>

            {/* Experiment Name */}
            <div>
              <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                Experiment Label / Name
              </label>
              <input
                type="text"
                value={experimentName}
                onChange={(e) => setExperimentName(e.target.value)}
                placeholder="e.g. Coverage Study 3.5GHz"
                className="w-full text-xs font-mono p-1.5 rounded border border-border bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-rust"
              />
            </div>

            {/* Transmitter & Frequency */}
            <div className="p-3 bg-parchment-subtle/50 rounded border border-border/80 space-y-2.5">
              <span className="text-xs font-mono font-bold text-slate-800 uppercase block">
                Transmitter & RF Configuration
              </span>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    Frequency (GHz)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={freqGHz}
                    onChange={(e) => setFreqGHz(parseFloat(e.target.value) || 3.5)}
                    className="w-full text-xs font-mono p-1 rounded border border-border bg-white text-slate-800"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    TX Power (dBm)
                  </label>
                  <input
                    type="number"
                    value={txPowerDbm}
                    onChange={(e) => setTxPowerDbm(parseFloat(e.target.value) || 30)}
                    className="w-full text-xs font-mono p-1 rounded border border-border bg-white text-slate-800"
                  />
                </div>
              </div>

              <div>
                <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                  TX Position [X, Y, Z] (m)
                </label>
                <div className="grid grid-cols-3 gap-2">
                  <input
                    type="number"
                    value={txPos[0]}
                    onChange={(e) => setTxPos([parseFloat(e.target.value) || 0, txPos[1], txPos[2]])}
                    className="p-1 rounded border border-border bg-white text-xs font-mono text-slate-800"
                  />
                  <input
                    type="number"
                    value={txPos[1]}
                    onChange={(e) => setTxPos([txPos[0], parseFloat(e.target.value) || 0, txPos[2]])}
                    className="p-1 rounded border border-border bg-white text-xs font-mono text-slate-800"
                  />
                  <input
                    type="number"
                    value={txPos[2]}
                    onChange={(e) => setTxPos([txPos[0], txPos[1], parseFloat(e.target.value) || 0])}
                    className="p-1 rounded border border-border bg-white text-xs font-mono text-slate-800"
                  />
                </div>
              </div>
            </div>

            {/* Measurement Grid & Resolution */}
            <div className="p-3 bg-parchment-subtle/50 rounded border border-border/80 space-y-2.5">
              <span className="text-xs font-mono font-bold text-slate-800 uppercase block">
                Measurement Region & Grid Plane
              </span>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    Plane Height Z (m)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={receiverHeight}
                    onChange={(e) => setReceiverHeight(parseFloat(e.target.value) || 1.5)}
                    className="w-full text-xs font-mono p-1 rounded border border-border bg-white text-slate-800"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    Cell Size / Res (m)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={cellSize}
                    onChange={(e) => setCellSize(parseFloat(e.target.value) || 2.0)}
                    className="w-full text-xs font-mono p-1 rounded border border-border bg-white text-slate-800"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between text-xs font-mono pt-1 text-slate-600">
                <span>Region Mode: Derived Bounds</span>
                <span className="badge-tech bg-white">Auto +5.0m buffer</span>
              </div>
            </div>

            {/* Ray Solver Parameters */}
            <div className="p-3 bg-parchment-subtle/50 rounded border border-border/80 space-y-2.5">
              <span className="text-xs font-mono font-bold text-slate-800 uppercase block">
                Multipath & Ray Solver Flags
              </span>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    Samples Per TX
                  </label>
                  <input
                    type="number"
                    step="10000"
                    value={samplesPerTx}
                    onChange={(e) => setSamplesPerTx(parseInt(e.target.value) || 50000)}
                    className="w-full text-xs font-mono p-1 rounded border border-border bg-white text-slate-800"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                    Max Depth
                  </label>
                  <input
                    type="number"
                    value={maxDepth}
                    onChange={(e) => setMaxDepth(parseInt(e.target.value) || 3)}
                    className="w-full text-xs font-mono p-1 rounded border border-border bg-white text-slate-800"
                  />
                </div>
              </div>

              {/* Toggles */}
              <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enableLos}
                    onChange={(e) => setEnableLos(e.target.checked)}
                    className="accent-rust"
                  />
                  <span>Line of Sight</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enableSpecular}
                    onChange={(e) => setEnableSpecular(e.target.checked)}
                    className="accent-rust"
                  />
                  <span>Specular Refl</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enableDiffraction}
                    onChange={(e) => setEnableDiffraction(e.target.checked)}
                    className="accent-rust"
                  />
                  <span>Diffraction</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enableScattering}
                    onChange={(e) => setEnableScattering(e.target.checked)}
                    className="accent-rust"
                  />
                  <span>Scattering</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column (7 Cols) - Heatmap Visualizer & Statistics */}
        <div className="lg:col-span-7 space-y-4">
          {/* Heatmap Viewer Card */}
          <div className="card-technical p-4">
            {/* Viewport Top Bar */}
            <div className="flex items-center justify-between pb-3 border-b border-border/80 text-xs font-mono">
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-800 uppercase">
                  Spatial Coverage Raster Heatmap
                </span>
                {result?.experiment_id && (
                  <span className="text-[10px] text-slate-500 font-medium">
                    {result.experiment_id}
                  </span>
                )}
              </div>

              {/* Metric Toggle */}
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setActiveMetric("rss")}
                  className={`px-2.5 py-1 rounded text-xs transition-colors ${
                    activeMetric === "rss"
                      ? "bg-rust text-white font-bold"
                      : "bg-parchment-subtle text-slate-600 hover:text-slate-900"
                  }`}
                >
                  RSS (dBm)
                </button>
                <button
                  onClick={() => setActiveMetric("path_gain")}
                  className={`px-2.5 py-1 rounded text-xs transition-colors ${
                    activeMetric === "path_gain"
                      ? "bg-rust text-white font-bold"
                      : "bg-parchment-subtle text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Path Gain (dB)
                </button>
              </div>
            </div>

            {/* Heatmap Canvas Area */}
            <div className="my-3 min-h-[360px] bg-slate-900 rounded-md border border-slate-800 flex items-center justify-center p-3 overflow-hidden relative">
              {heatmapUrl ? (
                <img
                  src={heatmapUrl}
                  alt="Radio Coverage Heatmap"
                  className="max-h-[380px] w-auto object-contain rounded"
                />
              ) : (
                <div className="text-center p-8 space-y-3">
                  <div className="w-12 h-12 rounded-full bg-slate-800 border border-slate-700 mx-auto flex items-center justify-center text-slate-400">
                    <Map className="w-6 h-6" />
                  </div>
                  <h4 className="text-sm font-mono font-bold text-slate-300">
                    No Radio Map Computed Yet
                  </h4>
                  <p className="text-xs text-slate-500 max-w-sm">
                    Configure your carrier frequency and measurement parameters on the left, then click "Generate Radio Map".
                  </p>
                </div>
              )}
            </div>

            {/* Coverage Statistics Strip */}
            {result && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-border/80">
                <div className="p-2 rounded bg-parchment-subtle/70 text-center font-mono">
                  <span className="text-[9px] text-slate-500 uppercase block">Total Cells</span>
                  <span className="text-sm font-bold text-slate-800">
                    {result.total_cells} ({result.grid_dimensions?.join("×")})
                  </span>
                </div>

                <div className="p-2 rounded bg-parchment-subtle/70 text-center font-mono">
                  <span className="text-[9px] text-slate-500 uppercase block">Coverage %</span>
                  <span className="text-sm font-bold text-green-700">
                    {result.coverage_percentage?.toFixed(1)}%
                  </span>
                </div>

                <div className="p-2 rounded bg-parchment-subtle/70 text-center font-mono">
                  <span className="text-[9px] text-slate-500 uppercase block">Mean RSS</span>
                  <span className="text-sm font-bold text-rust">
                    {result.mean_rss_dbm?.toFixed(2)} dBm
                  </span>
                </div>

                <div className="p-2 rounded bg-parchment-subtle/70 text-center font-mono">
                  <span className="text-[9px] text-slate-500 uppercase block">RSS Range</span>
                  <span className="text-sm font-bold text-slate-800">
                    {result.min_rss_dbm?.toFixed(0)} to {result.max_rss_dbm?.toFixed(0)} dBm
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

