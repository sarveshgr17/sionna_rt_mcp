import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  FolderGit2,
  Search,
  Filter,
  RefreshCw,
  ArrowUpDown,
  ExternalLink,
  Layers,
  MapPin,
  Calendar,
  X,
  GitCompare,
  Download,
  Play,
  Box,
} from "lucide-react";
import { useExperimentDetails, useExperiments } from "@/hooks/useMcp";
import { useActiveScene } from "@/context/SceneContext";
import { ExperimentSummary } from "@/types/mcp";
import { mcpClient } from "@/services/mcp/client";

export function Experiments() {
  const navigate = useNavigate();
  const { data: expData, isLoading, refetch } = useExperiments();
  const { activeScene, setActiveScene, currentSceneConfig, allScenes } = useActiveScene();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterBand, setFilterBand] = useState<"all" | "sub6" | "mmwave">("all");
  const [sceneScope, setSceneScope] = useState<"active" | "all">("active");

  const { data: details, isLoading: detailsLoading } = useExperimentDetails(selectedId || undefined);

  const experiments = expData?.experiments || [];

  const filteredExperiments = experiments.filter((exp) => {
    // 1. Scene scoping (defaults to active scene selected in navbar)
    if (sceneScope === "active" && exp.scene_name.toLowerCase() !== activeScene.toLowerCase()) {
      return false;
    }

    const matchesSearch =
      exp.experiment_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (exp.experiment_name && exp.experiment_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      exp.scene_name.toLowerCase().includes(searchTerm.toLowerCase());

    if (!matchesSearch) return false;

    if (filterBand === "sub6") {
      return exp.frequency_hz < 6e9;
    } else if (filterBand === "mmwave") {
      return exp.frequency_hz >= 6e9;
    }
    return true;
  });

  const activeSceneExpCount = experiments.filter(
    (e) => e.scene_name.toLowerCase() === activeScene.toLowerCase()
  ).length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/80 pb-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold font-sans text-slate-900 tracking-tight">
              Experiment Storage Library
            </h1>
            <span className="badge-tech bg-parchment-subtle text-slate-600">
              {experiments.length} EXPERIMENTS ARCHIVED
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Numerical radio maps and coverage grids synchronized with active scene: <strong className="text-rust">{currentSceneConfig.label}</strong>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to="/radio-maps"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-rust hover:bg-rust-hover rounded transition-colors shadow-technical"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>+ New Experiment in {activeScene}</span>
          </Link>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-700 hover:text-slate-900 rounded border border-border bg-white hover:bg-parchment transition-colors shadow-technical"
          >
            <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
            <span>Reload Library</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 card-technical p-3">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder={`Search ${activeScene} experiments, IDs, or bands...`}
            className="w-full pl-9 pr-3 py-1.5 text-xs font-mono rounded border border-border bg-parchment-subtle/50 text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-rust"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
          {/* Scene Scope Filter */}
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500 text-[11px] uppercase">Scene:</span>
            <button
              onClick={() => setSceneScope("active")}
              className={`px-2.5 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
                sceneScope === "active"
                  ? "bg-rust text-white font-bold"
                  : "bg-parchment-subtle text-slate-600 hover:bg-parchment"
              }`}
            >
              <Box className="w-3 h-3" />
              <span>Active: {activeScene} ({activeSceneExpCount})</span>
            </button>
            <button
              onClick={() => setSceneScope("all")}
              className={`px-2.5 py-1 rounded text-xs transition-colors ${
                sceneScope === "all"
                  ? "bg-rust text-white font-bold"
                  : "bg-parchment-subtle text-slate-600 hover:bg-parchment"
              }`}
            >
              All Scenes ({experiments.length})
            </button>
          </div>

          <div className="h-4 w-[1px] bg-border hidden sm:block" />

          {/* Spectrum Filter */}
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500 text-[11px] uppercase">Spectrum:</span>
            <button
              onClick={() => setFilterBand("all")}
              className={`px-2.5 py-1 rounded text-xs transition-colors ${
                filterBand === "all" ? "bg-slate-800 text-white font-bold" : "bg-parchment-subtle text-slate-600"
              }`}
            >
              All
            </button>
            <button
              onClick={() => setFilterBand("sub6")}
              className={`px-2.5 py-1 rounded text-xs transition-colors ${
                filterBand === "sub6" ? "bg-slate-800 text-white font-bold" : "bg-parchment-subtle text-slate-600"
              }`}
            >
              Sub-6 GHz
            </button>
            <button
              onClick={() => setFilterBand("mmwave")}
              className={`px-2.5 py-1 rounded text-xs transition-colors ${
                filterBand === "mmwave" ? "bg-slate-800 text-white font-bold" : "bg-parchment-subtle text-slate-600"
              }`}
            >
              mmWave
            </button>
          </div>
        </div>
      </div>

      {/* Experiment Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredExperiments.length === 0 ? (
          <div className="col-span-full card-technical p-8 text-center text-slate-500 text-xs font-mono space-y-3">
            <div>
              {isLoading
                ? "Querying MCP experiment store..."
                : `No experiments found for scene "${activeScene}".`}
            </div>
            {!isLoading && (
              <div className="pt-2">
                <Link
                  to="/radio-maps"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-rust hover:bg-rust-hover text-white text-xs font-semibold tracking-wide transition-colors shadow-technical"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Execute First Radio Map Simulation in {activeScene}</span>
                </Link>
              </div>
            )}
          </div>
        ) : (
          filteredExperiments.map((exp) => (
            <div
              key={exp.experiment_id}
              className="card-technical p-4 flex flex-col justify-between hover:border-border-dark transition-all group"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div>
                    <h3 className="text-xs font-bold font-mono text-rust group-hover:underline truncate max-w-[220px]">
                      {exp.experiment_name || exp.experiment_id}
                    </h3>
                    <span className="text-[10px] font-mono text-slate-400 block truncate">
                      {exp.experiment_id}
                    </span>
                  </div>
                  <span className="badge-tech bg-parchment-subtle text-slate-700">
                    {(exp.frequency_hz / 1e9).toFixed(2)} GHz
                  </span>
                </div>

                <div className="space-y-1.5 text-[11px] font-mono text-slate-600 bg-parchment-subtle/60 p-2.5 rounded border border-border/70 my-3">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Scene:</span>
                    <span className="font-semibold text-slate-800">{exp.scene_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Grid Dim:</span>
                    <span className="font-semibold text-slate-800">
                      {exp.grid_dimensions?.join("×")} ({exp.total_cells} cells)
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Mean RSS:</span>
                    <span className="font-semibold text-rust">{exp.mean_rss_dbm?.toFixed(2)} dBm</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Coverage:</span>
                    <span className="font-semibold text-green-700">{exp.coverage_percentage?.toFixed(1)}%</span>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-border/80 flex items-center justify-between text-xs">
                <button
                  onClick={() => setSelectedId(exp.experiment_id)}
                  className="text-slate-800 font-semibold hover:text-rust flex items-center gap-1"
                >
                  <span>Inspect Details</span>
                  <ExternalLink className="w-3 h-3" />
                </button>

                <button
                  onClick={() => navigate("/compare")}
                  className="text-slate-500 hover:text-slate-800 flex items-center gap-1"
                >
                  <GitCompare className="w-3 h-3" />
                  <span>Compare</span>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Experiment Details Modal / Drawer */}
      {selectedId && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-2xl border border-border max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-4 border-b border-border flex items-center justify-between bg-parchment-sidebar">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-bold font-mono text-slate-900">
                    Experiment Details: {selectedId}
                  </h2>
                  <span className="badge-tech bg-white">
                    {details ? `${(details.frequency_hz / 1e9).toFixed(2)} GHz` : ""}
                  </span>
                </div>
                <span className="text-[11px] font-mono text-slate-500">
                  {details?.experiment_name || "Unnamed Experiment"}
                </span>
              </div>
              <button
                onClick={() => setSelectedId(null)}
                className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-parchment transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-5 overflow-y-auto space-y-4">
              {detailsLoading || !details ? (
                <div className="p-8 text-center text-xs font-mono text-slate-500">
                  Loading experiment metadata and heatmaps...
                </div>
              ) : (
                <>
                  {/* Generated Heatmaps */}
                  <div>
                    <h4 className="text-xs font-mono font-bold text-slate-700 uppercase mb-2">
                      Generated Scientific Visualizations
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {details.artifact_paths?.rss_heatmap ? (
                        <div className="card-technical p-2 bg-slate-900 border-slate-800 text-center">
                          <span className="text-[10px] font-mono text-slate-400 block mb-1">
                            Received Signal Strength (RSS dBm)
                          </span>
                          <img
                            src={mcpClient.getArtifactUrl(details.artifact_paths.rss_heatmap)}
                            alt="RSS Heatmap"
                            className="max-h-52 w-auto mx-auto object-contain rounded"
                          />
                        </div>
                      ) : null}

                      {details.artifact_paths?.path_gain_heatmap ? (
                        <div className="card-technical p-2 bg-slate-900 border-slate-800 text-center">
                          <span className="text-[10px] font-mono text-slate-400 block mb-1">
                            Path Gain (dB)
                          </span>
                          <img
                            src={mcpClient.getArtifactUrl(details.artifact_paths.path_gain_heatmap)}
                            alt="Path Gain Heatmap"
                            className="max-h-52 w-auto mx-auto object-contain rounded"
                          />
                        </div>
                      ) : null}
                    </div>
                  </div>

                  {/* Metadata Specification Table */}
                  <div className="grid grid-cols-2 gap-4 text-xs font-mono">
                    <div className="p-3 bg-parchment-subtle/70 rounded border border-border/80 space-y-1">
                      <span className="text-[10px] font-bold text-slate-500 uppercase block mb-1">
                        Transmitter & RF Specs
                      </span>
                      <div className="flex justify-between">
                        <span className="text-slate-500">TX Position:</span>
                        <span className="text-slate-800 font-semibold">[{details.tx_position?.join(", ")}]m</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">TX Power:</span>
                        <span className="text-slate-800 font-semibold">{details.tx_power_dbm} dBm</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Antenna:</span>
                        <span className="text-slate-800 font-semibold">{details.antenna_type} ({details.polarization})</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Height (Z):</span>
                        <span className="text-slate-800 font-semibold">{details.measurement_height} m</span>
                      </div>
                    </div>

                    <div className="p-3 bg-parchment-subtle/70 rounded border border-border/80 space-y-1">
                      <span className="text-[10px] font-bold text-slate-500 uppercase block mb-1">
                        Grid & Coverage Metrics
                      </span>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Total Cells:</span>
                        <span className="text-slate-800 font-semibold">{details.total_cells}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Valid Cells:</span>
                        <span className="text-slate-800 font-semibold">{details.valid_cells}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Coverage:</span>
                        <span className="text-green-700 font-semibold">{details.coverage_percentage?.toFixed(1)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Mean RSS:</span>
                        <span className="text-rust font-semibold">{details.mean_rss_dbm?.toFixed(2)} dBm</span>
                      </div>
                    </div>
                  </div>

                  {/* Array Shapes in NPZ */}
                  <div className="p-3 bg-parchment-subtle/40 rounded border border-border/80 text-[11px] font-mono">
                    <span className="text-[10px] font-bold text-slate-500 uppercase block mb-1">
                      Archived Numerical Array Shapes (NPZ)
                    </span>
                    <div className="grid grid-cols-3 gap-2">
                      {details.array_shapes &&
                        Object.entries(details.array_shapes).map(([name, shape]) => (
                          <div key={name} className="flex justify-between bg-white px-2 py-1 rounded border border-border">
                            <span className="text-slate-600 truncate">{name}:</span>
                            <span className="text-slate-900 font-bold">[{shape.join("×")}]</span>
                          </div>
                        ))}
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-border flex items-center justify-between bg-parchment-sidebar">
              <span className="text-[11px] font-mono text-slate-500">
                Persistence Format: IEEE-754 Compressed NPZ + JSON
              </span>
              <button
                onClick={() => {
                  setSelectedId(null);
                  navigate("/compare");
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-rust hover:bg-rust-hover text-white text-xs font-semibold tracking-wide transition-colors"
              >
                <GitCompare className="w-3.5 h-3.5" />
                <span>Select for Comparison</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

