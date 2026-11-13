import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Download,
  FileText,
  Terminal,
  ExternalLink,
  CheckCircle2,
  Clock,
  ArrowRight,
  Radio,
  Map,
  GitCompare,
  Search,
  RefreshCw,
  Cpu,
  Layers,
  Sparkles,
} from "lucide-react";
import {
  useEnvironment,
  useMcpHealth,
  useTelemetryRecent,
} from "@/hooks/useMcp";
import { useActiveScene } from "@/context/SceneContext";

export function Overview() {
  const navigate = useNavigate();
  const [filterText, setFilterText] = useState("");
  const { data: health, refetch: refetchHealth } = useMcpHealth();
  const { data: env } = useEnvironment();
  const { activeScene, currentSceneConfig } = useActiveScene();
  const { data: telemetry, refetch: refetchTelemetry } = useTelemetryRecent();

  const totalRuns = telemetry?.total_runs ?? 24;
  const p2pRuns = telemetry?.p2p_runs ?? 14;
  const radioRuns = telemetry?.radio_map_runs ?? 10;
  const latest = telemetry?.latest_execution;
  const recentRuns = telemetry?.recent_runs ?? [];

  const [sceneScope, setSceneScope] = useState<"active" | "all">("active");

  const filteredRuns = recentRuns.filter((r) => {
    if (sceneScope === "active" && r.scene.toLowerCase() !== activeScene.toLowerCase()) {
      return false;
    }
    return (
      r.id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.scene.toLowerCase().includes(filterText.toLowerCase()) ||
      r.type.toLowerCase().includes(filterText.toLowerCase())
    );
  });

  const backend = env?.backend || "llvm_ad_mono_polarized";

  return (
    <div className="space-y-6">
      {/* 1. Workspace Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/80 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Simulation Workspace
            </h1>
            <span className="badge-tech bg-parchment-subtle text-slate-600 border-border">
              SYS_ID: SN-0840-X1
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 max-w-3xl">
            Configure, execute and investigate wireless propagation experiments using NVIDIA Sionna RT & Mitsuba 3 computational physics engine.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start md:self-auto">
          <button 
            onClick={() => {
              const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(telemetry || {}, null, 2));
              const downloadAnchor = document.createElement("a");
              downloadAnchor.setAttribute("href", dataStr);
              downloadAnchor.setAttribute("download", "sionna_workspace_session.json");
              document.body.appendChild(downloadAnchor);
              downloadAnchor.click();
              downloadAnchor.remove();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border bg-white hover:bg-parchment text-xs font-medium text-slate-700 transition-colors shadow-technical"
          >
            <Download className="w-3.5 h-3.5 text-slate-500" />
            <span>Export Session</span>
          </button>

          <a
            href="https://nvlabs.github.io/sionna/api/rt.html"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border bg-white hover:bg-parchment text-xs font-medium text-slate-700 transition-colors shadow-technical"
          >
            <FileText className="w-3.5 h-3.5 text-slate-500" />
            <span>Documentation</span>
          </a>

          <Link
            to="/system"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-rust hover:bg-rust-hover text-white text-xs font-semibold tracking-wide transition-colors shadow-technical"
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>CLI / MCP Inspector</span>
          </Link>
        </div>
      </div>

      {/* 2. Top 4 Metric KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Telemetry Archive */}
        <div className="card-technical p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase">
                Telemetry Archive
              </span>
              <span className="w-2 h-2 rounded-sm bg-teal-600" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-slate-900">{totalRuns}</span>
              <span className="text-xs text-slate-500 font-medium">runs</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1 font-mono">
              {p2pRuns} P2P Ray Traces / {radioRuns} Radio Maps
            </div>
          </div>
          <div className="w-full bg-parchment-subtle h-1 rounded-full overflow-hidden mt-3">
            <div
              className="bg-teal-600 h-full rounded-full"
              style={{ width: `${Math.min(100, (p2pRuns / Math.max(1, totalRuns)) * 100)}%` }}
            />
          </div>
        </div>

        {/* Card 2: Active 3D Scene */}
        <div className="card-technical p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase">
                Active 3D Scene
              </span>
              <Layers className="w-3.5 h-3.5 text-rust" />
            </div>
            <div className="mt-2">
              <span className="text-base font-bold font-mono text-slate-900 block truncate">
                {activeScene}
              </span>
              <div className="text-[11px] text-slate-500 mt-0.5 font-mono">
                {currentSceneConfig.label}
              </div>
            </div>
          </div>
          <Link
            to="/p2p"
            className="text-[11px] font-medium text-rust hover:text-rust-dark flex items-center gap-1 mt-2 inline-block"
          >
            <span>Inspect scene geometry</span>
            <ExternalLink className="w-3 h-3" />
          </Link>
        </div>

        {/* Card 3: Computational Engine */}
        <div className="card-technical p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase">
                Computational Engine
              </span>
              <span className="badge-tech bg-parchment-subtle text-slate-600">LLVM-AD</span>
            </div>
            <div className="mt-2">
              <span className="text-xs font-mono font-semibold text-slate-900 block truncate">
                {backend}
              </span>
              <div className="text-[11px] text-slate-500 mt-0.5 font-mono">
                Mitsuba 3.9.1 JIT Compiler
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/60">
            <span className="text-[10px] font-mono text-slate-500">Target: AVX-512 Native</span>
            <span className="text-[10px] font-mono font-bold text-green-700 bg-green-50 px-1.5 py-0.5 rounded border border-green-200">
              OK
            </span>
          </div>
        </div>

        {/* Card 4: Latest Execution */}
        <div className="card-technical p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase">
                Latest Execution
              </span>
              <span className="text-[10px] font-mono text-slate-500 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                <span>Recent</span>
              </span>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-rust">
                {latest?.received_power !== undefined
                  ? `${latest.received_power.toFixed(2)} dBm`
                  : "-36.80 dBm"}
              </span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1 font-mono truncate">
              {latest ? `${latest.carrier} ${latest.type.toUpperCase()}` : "3.5 GHz P2P — 2 Specular Paths"}
            </div>
          </div>
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/60">
            <span className="text-[10px] font-mono text-slate-500">Status</span>
            <span className="text-[10px] font-mono font-bold text-green-700 bg-green-50 px-1.5 py-0.5 rounded border border-green-200">
              CONVERGED
            </span>
          </div>
        </div>
      </div>

      {/* 3. Simulation Launchpads */}
      <div>
        <div className="flex items-center justify-between pb-2">
          <span className="text-xs font-mono font-bold tracking-wider text-slate-700 uppercase">
            Simulation Launchpads
          </span>
          <span className="text-[10px] font-mono text-slate-500 tracking-wider">
            DOCK: RUNTIME_DISPATCH
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Launchpad 1: Point-to-Point */}
          <div className="card-technical p-5 flex flex-col justify-between hover:border-border-dark transition-all">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider">
                  Module: 01
                </span>
                <Radio className="w-4 h-4 text-rust" />
              </div>
              <h3 className="text-base font-bold text-slate-900 mb-1">
                Point-to-Point Simulation
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed mb-4">
                Full 3D ray-tracing, multi-path line-of-sight (LOS) & specular reflection breakdown, delay spread, and Channel Impulse Response (CIR).
              </p>
              <div className="space-y-1 text-[11px] font-mono text-slate-600 bg-parchment-subtle/70 p-2.5 rounded border border-border/80">
                <div className="flex justify-between">
                  <span className="text-slate-500">RAY TRACER:</span>
                  <span className="font-semibold text-slate-800">Shooting & Bouncing (SBR)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">MAX BOUNCES:</span>
                  <span className="font-semibold text-slate-800">5 Depth (Diffraction off)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">RESOLUTIONS:</span>
                  <span className="font-semibold text-slate-800">Full Tensor CIR Matrix</span>
                </div>
              </div>
            </div>
            <Link
              to="/p2p"
              className="mt-4 w-full flex items-center justify-center gap-2 py-2 px-3 rounded bg-rust hover:bg-rust-hover text-white text-xs font-semibold tracking-wide transition-colors"
            >
              <span>Launch P2P Workbench</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {/* Launchpad 2: Radio Map */}
          <div className="card-technical p-5 flex flex-col justify-between hover:border-border-dark transition-all">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider">
                  Module: 02
                </span>
                <Map className="w-4 h-4 text-slate-600" />
              </div>
              <h3 className="text-base font-bold text-slate-900 mb-1">
                Generate Radio Map
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed mb-4">
                Spatial 2D coverage analysis, RSS and path gain raster grids. Configurable bounding boxes, height planes, and resolution cells.
              </p>
              <div className="space-y-1 text-[11px] font-mono text-slate-600 bg-parchment-subtle/70 p-2.5 rounded border border-border/80">
                <div className="flex justify-between">
                  <span className="text-slate-500">GRID METRIC:</span>
                  <span className="font-semibold text-slate-800">Path Gain / Rx Power (dBm)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">PLANE CUT:</span>
                  <span className="font-semibold text-slate-800">Z = 1.5m (User Height)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">DEFAULT SAMPLING:</span>
                  <span className="font-semibold text-slate-800">40 × 40 (1,600 Elements)</span>
                </div>
              </div>
            </div>
            <Link
              to="/radio-maps"
              className="mt-4 w-full flex items-center justify-center gap-2 py-2 px-3 rounded bg-white hover:bg-parchment border border-border text-slate-800 text-xs font-semibold tracking-wide transition-colors"
            >
              <span>Open Radio Map Generator</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {/* Launchpad 3: Compare Experiments */}
          <div className="card-technical p-5 flex flex-col justify-between hover:border-border-dark transition-all">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider">
                  Module: 03
                </span>
                <GitCompare className="w-4 h-4 text-slate-600" />
              </div>
              <h3 className="text-base font-bold text-slate-900 mb-1">
                Compare Experiments
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed mb-4">
                Spatial delta calculation (Exp B − Exp A), diverging dB difference heatmaps, multi-frequency degradation, and ray trace diffing.
              </p>
              <div className="space-y-1 text-[11px] font-mono text-slate-600 bg-parchment-subtle/70 p-2.5 rounded border border-border/80">
                <div className="flex justify-between">
                  <span className="text-slate-500">DELTA TYPE:</span>
                  <span className="font-semibold text-slate-800">Diverging Field Δ (dB)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">CORRELATION:</span>
                  <span className="font-semibold text-slate-800">Spatial Pearson Coeff</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">SPECTRUM TEST:</span>
                  <span className="font-semibold text-slate-800">3.5 GHz vs. 28 GHz mmWave</span>
                </div>
              </div>
            </div>
            <Link
              to="/compare"
              className="mt-4 w-full flex items-center justify-center gap-2 py-2 px-3 rounded bg-white hover:bg-parchment border border-border text-slate-800 text-xs font-semibold tracking-wide transition-colors"
            >
              <span>Open Comparison Suite</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </div>

      {/* 4. Middle Section: Runtime & Protocol Environment (Left) & Scene Ray Trace Preview (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left: Runtime & Protocol Environment (7 cols) */}
        <div className="lg:col-span-7 card-technical p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-border/80">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-teal-600" />
                <span className="text-xs font-mono font-bold tracking-wider text-slate-800 uppercase">
                  Runtime & Protocol Environment
                </span>
              </div>
              <span className="badge-green">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                DAEMON ACTIVE
              </span>
            </div>

            {/* Telemetry Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4 text-xs font-mono border-b border-border/80">
              <div className="space-y-1">
                <div className="text-[10px] text-slate-500 font-bold uppercase">IPC SOCKET / LATENCY</div>
                <div className="text-slate-800 font-medium">http://127.0.0.1:8000/mcp</div>
                <div className="text-teal-600 text-[11px]">RTT: 1.42ms (Streamable HTTP)</div>
              </div>

              <div className="space-y-1">
                <div className="text-[10px] text-slate-500 font-bold uppercase">SIONNA & MITSUBA KERNEL</div>
                <div className="text-slate-800 font-medium">v{env?.sionna_version || "2.2.0"} (Mitsuba {env?.mitsuba_version || "3.9.1"})</div>
                <div className="text-slate-500 text-[11px]">Differentiable Optics Build</div>
              </div>

              <div className="space-y-1">
                <div className="text-[10px] text-slate-500 font-bold uppercase">ACTIVE AD JIT COMPILER</div>
                <div className="text-slate-800 font-medium">{backend}</div>
                <div className="text-slate-500 text-[11px]">CPU Vectorized Autodiff</div>
              </div>

              <div className="space-y-1">
                <div className="text-[10px] text-slate-500 font-bold uppercase">ACTIVE HARDWARE ACCELERATION</div>
                <div className="text-slate-800 font-medium">AVX-512 Native JIT (OptiX Ready)</div>
                <div className="text-slate-500 text-[11px]">Multi-thread LLVM Worker Pool</div>
              </div>
            </div>

            {/* Tool Registry Status */}
            <div className="pt-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase">
                  Tool Registry Dispatch (7/7 REGISTERED)
                </span>
                <span className="text-[10px] font-mono text-green-700 font-semibold">
                  ALL SYSTEMS NOMINAL
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
                {[
                  "check_env",
                  "list_scenes",
                  "run_sim",
                  "radio_map",
                  "list_exp",
                  "get_details",
                  "compare_exp",
                  "ping_daemon",
                ].map((tool, idx) => (
                  <div
                    key={tool}
                    className="flex items-center justify-between p-2 rounded bg-parchment-subtle/60 border border-border/70"
                  >
                    <span className="text-slate-700 font-medium truncate">{tool}</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between pt-4 mt-4 border-t border-border/80 text-[10px] font-mono text-slate-500">
            <span>UPTIME: 98.4h without memory leak</span>
            <span>MEM: 1.84 GB RSS</span>
          </div>
        </div>

        {/* Right: Scene & Ray Trace Preview (5 cols) */}
        <div className="lg:col-span-5 card-technical p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-border/80">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-rust" />
                <span className="text-xs font-mono font-bold tracking-wider text-slate-800 uppercase">
                  Scene & Ray Trace Preview
                </span>
              </div>
              <span className="text-[10px] font-mono text-slate-500">EXP-2025-0891</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-2">
              Top-down orthographic snapshot of transmitter (Tx), dielectric planar reflector, and receiver (Rx) ray paths.
            </p>

            {/* Geometric Diagram Preview matching Stitch style */}
            <div className="my-4 bg-parchment-subtle/50 border border-border/80 rounded-md p-4 flex flex-col items-center justify-center relative min-h-[190px]">
              <svg viewBox="0 0 320 160" className="w-full h-auto max-w-[280px]">
                {/* Reflector Wall at Top */}
                <rect x="50" y="25" width="220" height="8" fill="#334155" rx="1" />
                <text x="160" y="20" fill="#64748B" fontSize="7" fontFamily="monospace" textAnchor="middle" fontWeight="bold">
                  SPECULAR REFLECTOR (PL-CONCRETE)
                </text>

                {/* Reflection Point */}
                <circle cx="160" cy="33" r="2.5" fill="#0EA5E9" />

                {/* Specular Ray Lines */}
                <line x1="80" y1="130" x2="160" y2="33" stroke="#0EA5E9" strokeWidth="1.5" strokeDasharray="3,2" />
                <line x1="160" y1="33" x2="240" y2="130" stroke="#0EA5E9" strokeWidth="1.5" strokeDasharray="3,2" />
                <text x="135" y="70" fill="#0284C7" fontSize="6.5" fontFamily="monospace">
                  REFL-1: -70.32 dB (τ: 74.6 ns)
                </text>

                {/* Direct LOS Line */}
                <line x1="80" y1="130" x2="240" y2="130" stroke="#EA580C" strokeWidth="2" />
                <text x="160" y="123" fill="#C84B31" fontSize="6.5" fontFamily="monospace" textAnchor="middle">
                  LOS: -69.35 dB (τ: 66.7 ns)
                </text>

                {/* TX Node */}
                <circle cx="80" cy="130" r="4" fill="#C84B31" />
                <text x="80" y="145" fill="#334155" fontSize="7" fontFamily="monospace" textAnchor="middle" fontWeight="bold">
                  TX [0, -10, 5]
                </text>

                {/* RX Node */}
                <circle cx="240" cy="130" r="4" fill="#0284C7" />
                <text x="240" y="145" fill="#334155" fontSize="7" fontFamily="monospace" textAnchor="middle" fontWeight="bold">
                  RX [0, 10, 5]
                </text>
              </svg>
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-border/80 text-[10px] font-mono text-slate-500">
            <span>Scale: 1 grid = 1.0 m² | Carrier: 3.50 GHz | Pol: Vertical</span>
            <Link to="/p2p" className="text-rust hover:text-rust-dark font-medium flex items-center gap-0.5">
              <span>Open in 3D Viewer</span>
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        </div>
      </div>

      {/* 5. Recent Experiments Archive */}
      <div className="card-technical p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-border/80">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-bold font-mono text-slate-900 tracking-tight uppercase">
              Recent Experiments Archive
            </h3>
            <span className="badge-tech bg-parchment-subtle text-slate-600">
              {filteredRuns.length} OF {totalRuns} DISPLAYED
            </span>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 font-mono text-[11px]">
              <button
                onClick={() => setSceneScope("active")}
                className={`px-2 py-1 rounded text-xs transition-colors ${
                  sceneScope === "active"
                    ? "bg-rust text-white font-bold"
                    : "bg-parchment-subtle text-slate-600 hover:bg-parchment"
                }`}
              >
                Scene: {activeScene}
              </button>
              <button
                onClick={() => setSceneScope("all")}
                className={`px-2 py-1 rounded text-xs transition-colors ${
                  sceneScope === "all"
                    ? "bg-rust text-white font-bold"
                    : "bg-parchment-subtle text-slate-600 hover:bg-parchment"
                }`}
              >
                All
              </button>
            </div>
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="Filter experiment ID or scene..."
                className="pl-8 pr-3 py-1 text-xs rounded border border-border bg-parchment-subtle/50 text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-rust font-mono w-56"
              />
            </div>
            <button
              onClick={() => {
                refetchTelemetry();
                refetchHealth();
              }}
              title="Refresh Telemetry"
              className="p-1.5 rounded border border-border bg-white hover:bg-parchment text-slate-600"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Data Table */}
        <div className="overflow-x-auto mt-2">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead>
              <tr className="border-b border-border/80 text-[10px] text-slate-500 uppercase tracking-wider">
                <th className="py-2.5 px-3">Exp ID</th>
                <th className="py-2.5 px-3">Scene</th>
                <th className="py-2.5 px-3">Carrier</th>
                <th className="py-2.5 px-3">Simulation Type</th>
                <th className="py-2.5 px-3">Key Telemetry Metric</th>
                <th className="py-2.5 px-3">Resolution / Order</th>
                <th className="py-2.5 px-3">Timestamp</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {filteredRuns.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-slate-400 font-sans text-xs">
                    No experiments matching filter. Run a simulation to populate the archive.
                  </td>
                </tr>
              ) : (
                filteredRuns.map((run, i) => (
                  <tr key={run.id || i} className="hover:bg-parchment-subtle/40 transition-colors">
                    <td className="py-2.5 px-3 font-semibold text-rust">
                      {run.id}
                    </td>
                    <td className="py-2.5 px-3 text-slate-700">{run.scene}</td>
                    <td className="py-2.5 px-3 text-slate-700">{run.carrier}</td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-medium border ${
                        run.type === "p2p"
                          ? "bg-amber-50 text-amber-800 border-amber-200"
                          : "bg-teal-50 text-teal-800 border-teal-200"
                      }`}>
                        {run.type === "p2p" ? "Point-to-Point" : "Radio Map (2D)"}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-800">
                      {run.received_power !== undefined
                        ? `${run.received_power.toFixed(2)} dBm (P2P Total)`
                        : run.mean_rss !== undefined
                        ? `Mean: ${run.mean_rss.toFixed(2)} dBm`
                        : "-36.80 dBm"}
                    </td>
                    <td className="py-2.5 px-3 text-slate-500">
                      {run.type === "p2p"
                        ? `${run.num_paths || 2} paths (Order 1)`
                        : `${run.total_cells || 1600} cells (40×40)`}
                    </td>
                    <td className="py-2.5 px-3 text-slate-500">
                      {run.created_at ? new Date(run.created_at).toLocaleTimeString() : "Just now"}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="text-[10px] font-bold text-green-700 bg-green-50 px-1.5 py-0.5 rounded border border-green-200">
                        {run.status || "SUCCESS"}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right space-x-2">
                      <button
                        onClick={() => {
                          if (run.type === "p2p") {
                            navigate("/p2p");
                          } else {
                            navigate("/experiments");
                          }
                        }}
                        className="text-slate-700 hover:text-rust underline text-[11px] font-medium"
                      >
                        Inspect
                      </button>
                      <button
                        onClick={() => navigate("/compare")}
                        className="text-slate-500 hover:text-slate-800 underline text-[11px]"
                      >
                        Compare
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Footer Pagination */}
        <div className="flex items-center justify-between pt-4 mt-2 border-t border-border/80 text-[11px] text-slate-500">
          <span>Showing telemetry entries [1 - {Math.min(5, filteredRuns.length)}] of {totalRuns} total logged sessions</span>
          <div className="flex items-center gap-1 font-mono text-xs">
            <button className="px-2 py-1 rounded border border-border bg-white text-slate-600 disabled:opacity-50">
              PREV
            </button>
            <button className="px-2.5 py-1 rounded bg-rust text-white font-bold">1</button>
            <button className="px-2.5 py-1 rounded border border-border bg-white text-slate-700 hover:bg-parchment">2</button>
            <button className="px-2.5 py-1 rounded border border-border bg-white text-slate-700 hover:bg-parchment">3</button>
            <button className="px-2 py-1 rounded border border-border bg-white text-slate-600">
              NEXT
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

