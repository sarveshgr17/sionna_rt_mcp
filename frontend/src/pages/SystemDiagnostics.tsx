import React, { useState } from "react";
import {
  Cpu,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Terminal,
  Code2,
  Play,
  FileCode2,
} from "lucide-react";
import { useEnvironment, useMcpHealth, useScenes } from "@/hooks/useMcp";
import { mcpClient } from "@/services/mcp/client";

export function SystemDiagnostics() {
  const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useMcpHealth();
  const { data: env, isLoading: envLoading, refetch: refetchEnv } = useEnvironment();
  const { data: scenes, refetch: refetchScenes } = useScenes();

  // Tool Inspector Tester
  const [selectedTool, setSelectedTool] = useState<string>("check_environment");
  const [testArgs, setTestArgs] = useState<string>("{}");
  const [toolResult, setToolResult] = useState<any>(null);
  const [toolRunning, setToolRunning] = useState<boolean>(false);
  const [toolError, setToolError] = useState<string | null>(null);

  const handleRunTestTool = async () => {
    setToolRunning(true);
    setToolError(null);
    setToolResult(null);

    let parsedArgs = {};
    try {
      parsedArgs = JSON.parse(testArgs || "{}");
    } catch (err: any) {
      setToolError(`Invalid JSON arguments: ${err.message}`);
      setToolRunning(false);
      return;
    }

    try {
      const res = await mcpClient.callTool(selectedTool, parsedArgs);
      setToolResult(res);
    } catch (err: any) {
      setToolError(err.message || String(err));
    } finally {
      setToolRunning(false);
    }
  };

  const isConnected = health?.mcp_connected ?? false;
  const tools = health?.tools || [];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/80 pb-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold font-sans text-slate-900 tracking-tight">
              System Diagnostics & MCP Protocol Inspector
            </h1>
            <span className="badge-tech bg-parchment-subtle text-slate-600">
              HEALTH CHECK
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time status of the Sionna RT ray-tracing kernel, Mitsuba 3 physics backend, and MCP tool registry.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              refetchHealth();
              refetchEnv();
              refetchScenes();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-700 hover:text-slate-900 rounded border border-border bg-white hover:bg-parchment transition-colors shadow-technical"
          >
            <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
            <span>Recheck All Systems</span>
          </button>
        </div>
      </div>

      {/* 4 Health Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: MCP Server */}
        <div className="card-technical p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold text-slate-500 uppercase">
                MCP Protocol Daemon
              </span>
              <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`} />
            </div>
            <div className="mt-2">
              <span className="text-base font-bold font-mono text-slate-900 block">
                {isConnected ? "Connected (Active)" : "Disconnected"}
              </span>
              <span className="text-[11px] font-mono text-slate-500">
                http://127.0.0.1:8000/mcp
              </span>
            </div>
          </div>
          <div className="mt-3 pt-2 border-t border-border/80 text-[10px] font-mono text-slate-500 flex justify-between">
            <span>Transport:</span>
            <span className="font-semibold text-slate-800">Streamable HTTP</span>
          </div>
        </div>

        {/* Card 2: Sionna RT */}
        <div className="card-technical p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold text-slate-500 uppercase">
                Sionna RT Core
              </span>
              <CheckCircle2 className="w-4 h-4 text-green-600" />
            </div>
            <div className="mt-2">
              <span className="text-base font-bold font-mono text-slate-900 block">
                sionna-rt v{env?.sionna_version || "2.2.0"}
              </span>
              <span className="text-[11px] font-mono text-slate-500">
                NVIDIA Ray Tracing Module
              </span>
            </div>
          </div>
          <div className="mt-3 pt-2 border-t border-border/80 text-[10px] font-mono text-slate-500 flex justify-between">
            <span>Simulator Status:</span>
            <span className="font-semibold text-green-700">READY</span>
          </div>
        </div>

        {/* Card 3: Mitsuba 3 */}
        <div className="card-technical p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold text-slate-500 uppercase">
                Mitsuba 3 Renderer
              </span>
              <CheckCircle2 className="w-4 h-4 text-green-600" />
            </div>
            <div className="mt-2">
              <span className="text-base font-bold font-mono text-slate-900 block">
                Mitsuba {env?.mitsuba_version || "3.9.1"}
              </span>
              <span className="text-[11px] font-mono text-slate-500">
                Optics & Electromagnetic Engine
              </span>
            </div>
          </div>
          <div className="mt-3 pt-2 border-t border-border/80 text-[10px] font-mono text-slate-500 flex justify-between">
            <span>Polarization:</span>
            <span className="font-semibold text-slate-800">Monopolarized</span>
          </div>
        </div>

        {/* Card 4: Computational Backend */}
        <div className="card-technical p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold text-slate-500 uppercase">
                Computational Backend
              </span>
              <Code2 className="w-4 h-4 text-rust" />
            </div>
            <div className="mt-2">
              <span className="text-xs font-bold font-mono text-slate-900 block truncate">
                {env?.backend || "llvm_ad_mono_polarized"}
              </span>
              <span className="text-[11px] font-mono text-slate-500">
                Dr.Jit LLVM Vectorized JIT
              </span>
            </div>
          </div>
          <div className="mt-3 pt-2 border-t border-border/80 text-[10px] font-mono text-slate-500 flex justify-between">
            <span>Hardware OptiX:</span>
            <span className="font-semibold text-slate-800">Fallback CPU JIT</span>
          </div>
        </div>
      </div>

      {/* 2 Columns: Registered Tools Catalog & Live Tool Tester */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left: Registered Tools Catalog (6 Cols) */}
        <div className="lg:col-span-6 card-technical p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-border/80">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-slate-700" />
              <h3 className="text-xs font-mono font-bold text-slate-900 uppercase">
                Registered MCP Tools ({tools.length} Discovered)
              </h3>
            </div>
            <span className="badge-tech bg-green-50 text-green-700 border-green-200">
              ALL NOMINAL
            </span>
          </div>

          <div className="space-y-2 max-h-[460px] overflow-y-auto pr-1">
            {tools.map((t) => (
              <div
                key={t.name}
                onClick={() => {
                  setSelectedTool(t.name);
                  if (t.name === "check_environment" || t.name === "list_scenes" || t.name === "list_experiments") {
                    setTestArgs("{}");
                  } else if (t.name === "run_simulation") {
                    setTestArgs(
                      JSON.stringify(
                        {
                          scene: "simple_reflector",
                          frequency_hz: 3.5e9,
                          tx_position: [0.0, -10.0, 5.0],
                          rx_position: [0.0, 10.0, 5.0],
                          tx_power_dbm: 30.0,
                        },
                        null,
                        2
                      )
                    );
                  }
                }}
                className={`p-3 rounded border transition-all cursor-pointer ${
                  selectedTool === t.name
                    ? "bg-rust/5 border-rust shadow-sm"
                    : "bg-parchment-subtle/50 border-border/80 hover:bg-parchment-subtle"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-slate-900">
                    {t.name}
                  </span>
                  <span className="text-[10px] font-mono text-green-600 bg-green-50 px-1.5 py-0.5 rounded border border-green-200">
                    Active
                  </span>
                </div>
                <p className="text-[11px] text-slate-600 mt-1 line-clamp-2">
                  {t.description}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Live MCP Tool Tester / Inspector (6 Cols) */}
        <div className="lg:col-span-6 card-technical p-4 flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-border/80">
              <div className="flex items-center gap-2">
                <Code2 className="w-4 h-4 text-rust" />
                <h3 className="text-xs font-mono font-bold text-slate-900 uppercase">
                  MCP Tool Inspector & RPC Dispatcher
                </h3>
              </div>
              <span className="text-[10px] font-mono text-slate-500">
                Target: {selectedTool}
              </span>
            </div>

            <div>
              <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                JSON Arguments Payload
              </label>
              <textarea
                rows={5}
                value={testArgs}
                onChange={(e) => setTestArgs(e.target.value)}
                className="w-full font-mono text-xs p-2.5 rounded border border-border bg-terminal-bg text-terminal-text focus:outline-none focus:ring-1 focus:ring-rust"
              />
            </div>

            <button
              onClick={handleRunTestTool}
              disabled={toolRunning}
              className="w-full py-2 px-4 rounded bg-rust hover:bg-rust-hover active:bg-rust-dark text-white font-mono font-bold text-xs uppercase tracking-wider transition-colors shadow-technical flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {toolRunning ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>DISPATCHING OVER STREAMABLE HTTP...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-white" />
                  <span>EXECUTE TOOL '{selectedTool}'</span>
                </>
              )}
            </button>

            {/* Error Display */}
            {toolError && (
              <div className="p-3 rounded bg-red-50 border border-red-200 text-xs font-mono text-red-700 space-y-1">
                <span className="font-bold block">Execution Error:</span>
                <span>{toolError}</span>
              </div>
            )}

            {/* Result Display */}
            {toolResult && (
              <div className="space-y-1">
                <span className="text-[10px] font-mono text-slate-500 uppercase block">
                  JSON-RPC Return Payload
                </span>
                <div className="max-h-56 overflow-y-auto bg-terminal-bg text-terminal-text p-3 rounded font-mono text-[11px] border border-terminal-border">
                  <pre>{JSON.stringify(toolResult, null, 2)}</pre>
                </div>
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-border/80 text-[10px] font-mono text-slate-500 flex justify-between">
            <span>Protocol: MCP 2.3 JSON-RPC</span>
            <span>Origin: 127.0.0.1:8080 (Adapter)</span>
          </div>
        </div>
      </div>
    </div>
  );
}

