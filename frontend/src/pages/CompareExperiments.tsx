import React, { useState } from "react";
import {
  GitCompare,
  Play,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  TrendingDown,
  TrendingUp,
  Minus,
} from "lucide-react";
import { useCompareExperiments, useExperiments } from "@/hooks/useMcp";
import { ComparisonResult } from "@/types/mcp";
import { mcpClient } from "@/services/mcp/client";

export function CompareExperiments() {
  const { data: expData } = useExperiments();
  const compareMutation = useCompareExperiments();

  const experiments = expData?.experiments || [];

  const [expA, setExpA] = useState<string>(experiments[0]?.experiment_id || "");
  const [expB, setExpB] = useState<string>(experiments[1]?.experiment_id || "");
  const [activeDiffMetric, setActiveDiffMetric] = useState<"rss" | "path_gain">("rss");

  const [comparisonResult, setComparisonResult] = useState<ComparisonResult | null>(null);

  const selectedExpA = experiments.find((e) => e.experiment_id === expA);
  const selectedExpB = experiments.find((e) => e.experiment_id === expB);

  const handleRunComparison = async () => {
    if (!expA || !expB) return;
    try {
      const res = await compareMutation.mutateAsync({
        experimentIdA: expA,
        experimentIdB: expB,
        generateHeatmaps: true,
      });
      setComparisonResult(res);
    } catch (err) {
      console.error("Comparison failed:", err);
    }
  };

  const diffHeatmapPath =
    activeDiffMetric === "rss"
      ? comparisonResult?.artifacts?.rss_diff || comparisonResult?.heatmaps?.rss_diff
      : comparisonResult?.artifacts?.path_gain_diff || comparisonResult?.heatmaps?.path_gain_diff;

  const diffHeatmapUrl = diffHeatmapPath ? mcpClient.getArtifactUrl(diffHeatmapPath) : null;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/80 pb-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold font-sans text-slate-900 tracking-tight">
              Spatial Difference & Comparison Suite
            </h1>
            <span className="badge-tech bg-parchment-subtle text-slate-600">
              MODULE: 03
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Calculate cell-by-cell electromagnetic delta (Δ = Experiment B − Experiment A) across identical spatial bounding grids.
          </p>
        </div>

        <div className="text-[11px] font-mono text-slate-600 bg-parchment-subtle px-2.5 py-1 rounded border border-border">
          CONVENTION: <strong className="text-rust">Δ = B − A</strong> (dB)
        </div>
      </div>

      {/* A / B Selection Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Experiment A (Baseline) */}
        <div className="card-technical p-4 border-l-4 border-l-orange-500 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold text-slate-800 uppercase">
              Experiment A (Baseline Reference)
            </span>
            <span className="badge-tech bg-orange-50 text-orange-700 border-orange-200">
              BASELINE
            </span>
          </div>

          <div>
            <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
              Select Experiment
            </label>
            <select
              value={expA}
              onChange={(e) => setExpA(e.target.value)}
              className="w-full text-xs font-mono p-1.5 rounded border border-border bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-rust"
            >
              {experiments.map((e) => (
                <option key={e.experiment_id} value={e.experiment_id}>
                  {e.experiment_name ? `${e.experiment_name} (${e.experiment_id})` : e.experiment_id} — {(e.frequency_hz / 1e9).toFixed(2)} GHz
                </option>
              ))}
            </select>
          </div>

          {selectedExpA && (
            <div className="text-[11px] font-mono text-slate-600 bg-parchment-subtle/60 p-2.5 rounded border border-border/70 space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-500">Carrier:</span>
                <span className="font-semibold text-slate-800">{(selectedExpA.frequency_hz / 1e9).toFixed(2)} GHz</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Grid Dim:</span>
                <span className="font-semibold text-slate-800">{selectedExpA.grid_dimensions?.join("×")}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Mean RSS:</span>
                <span className="font-semibold text-rust">{selectedExpA.mean_rss_dbm?.toFixed(2)} dBm</span>
              </div>
            </div>
          )}
        </div>

        {/* Experiment B (Modified) */}
        <div className="card-technical p-4 border-l-4 border-l-sky-500 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold text-slate-800 uppercase">
              Experiment B (Modified / Comparison)
            </span>
            <span className="badge-tech bg-sky-50 text-sky-700 border-sky-200">
              MODIFIED
            </span>
          </div>

          <div>
            <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
              Select Experiment
            </label>
            <select
              value={expB}
              onChange={(e) => setExpB(e.target.value)}
              className="w-full text-xs font-mono p-1.5 rounded border border-border bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-rust"
            >
              {experiments.map((e) => (
                <option key={e.experiment_id} value={e.experiment_id}>
                  {e.experiment_name ? `${e.experiment_name} (${e.experiment_id})` : e.experiment_id} — {(e.frequency_hz / 1e9).toFixed(2)} GHz
                </option>
              ))}
            </select>
          </div>

          {selectedExpB && (
            <div className="text-[11px] font-mono text-slate-600 bg-parchment-subtle/60 p-2.5 rounded border border-border/70 space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-500">Carrier:</span>
                <span className="font-semibold text-slate-800">{(selectedExpB.frequency_hz / 1e9).toFixed(2)} GHz</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Grid Dim:</span>
                <span className="font-semibold text-slate-800">{selectedExpB.grid_dimensions?.join("×")}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Mean RSS:</span>
                <span className="font-semibold text-sky-600">{selectedExpB.mean_rss_dbm?.toFixed(2)} dBm</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Compare Action Button */}
      <div className="text-center">
        <button
          onClick={handleRunComparison}
          disabled={!expA || !expB || compareMutation.isPending}
          className="py-2.5 px-6 rounded bg-rust hover:bg-rust-hover active:bg-rust-dark text-white font-mono font-bold text-xs uppercase tracking-wider transition-colors shadow-technical inline-flex items-center gap-2 disabled:opacity-50"
        >
          {compareMutation.isPending ? (
            <>
              <RotateCcw className="w-4 h-4 animate-spin" />
              <span>COMPUTING SPATIAL DELTA & DIVERGING HEATMAP...</span>
            </>
          ) : (
            <>
              <GitCompare className="w-4 h-4" />
              <span>EXECUTE SPATIAL COMPARISON (EXP B − EXP A)</span>
            </>
          )}
        </button>
      </div>

      {/* Comparison Results & Diverging Heatmap */}
      {comparisonResult && (
        <div className="space-y-4 animate-in fade-in duration-200">
          {/* Statistical Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="card-technical p-3 text-center font-mono">
              <span className="text-[10px] text-slate-500 uppercase block">Mean Delta</span>
              {(() => {
                const meanVal = comparisonResult.rss_difference_metrics?.mean_difference ?? comparisonResult.rss_difference_metrics?.mean_diff_db ?? 0;
                return (
                  <span className={`text-base font-bold ${meanVal >= 0 ? "text-sky-600" : "text-rust"}`}>
                    {meanVal > 0 ? "+" : ""}{meanVal.toFixed(2)} dB
                  </span>
                );
              })()}
            </div>

            <div className="card-technical p-3 text-center font-mono">
              <span className="text-[10px] text-slate-500 uppercase block">Standard Deviation</span>
              <span className="text-base font-bold text-slate-800">
                ±{(comparisonResult.rss_difference_metrics?.std_difference ?? comparisonResult.rss_difference_metrics?.std_diff_db ?? 0).toFixed(2)} dB
              </span>
            </div>

            <div className="card-technical p-3 text-center font-mono">
              <span className="text-[10px] text-slate-500 uppercase block">Delta Range</span>
              <span className="text-xs font-bold text-slate-800 block mt-1">
                {(comparisonResult.rss_difference_metrics?.min_difference ?? comparisonResult.rss_difference_metrics?.min_diff_db ?? 0).toFixed(1)} to{" "}
                {(comparisonResult.rss_difference_metrics?.max_difference ?? comparisonResult.rss_difference_metrics?.max_diff_db ?? 0).toFixed(1)} dB
              </span>
            </div>

            <div className="card-technical p-3 text-center font-mono">
              <span className="text-[10px] text-slate-500 uppercase block">Spatial Compatibility</span>
              <span className="text-xs font-bold text-green-700 flex items-center justify-center gap-1 mt-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
                <span>100% Grid Match</span>
              </span>
            </div>
          </div>

          {/* Diverging Difference Heatmap Viewer */}
          <div className="card-technical p-4">
            <div className="flex items-center justify-between pb-3 border-b border-border/80 text-xs font-mono">
              <span className="font-bold text-slate-800 uppercase">
                Diverging Difference Heatmap (Center = 0 dB)
              </span>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setActiveDiffMetric("rss")}
                  className={`px-2.5 py-1 rounded text-xs transition-colors ${
                    activeDiffMetric === "rss"
                      ? "bg-rust text-white font-bold"
                      : "bg-parchment-subtle text-slate-600"
                  }`}
                >
                  Δ RSS (dBm)
                </button>
                <button
                  onClick={() => setActiveDiffMetric("path_gain")}
                  className={`px-2.5 py-1 rounded text-xs transition-colors ${
                    activeDiffMetric === "path_gain"
                      ? "bg-rust text-white font-bold"
                      : "bg-parchment-subtle text-slate-600"
                  }`}
                >
                  Δ Path Gain (dB)
                </button>
              </div>
            </div>

            {/* Heatmap Image */}
            <div className="my-3 min-h-[360px] bg-slate-900 rounded-md border border-slate-800 flex items-center justify-center p-3 overflow-hidden">
              {diffHeatmapUrl ? (
                <img
                  src={diffHeatmapUrl}
                  alt="Diverging Difference Heatmap"
                  className="max-h-[380px] w-auto object-contain rounded"
                />
              ) : (
                <div className="text-xs font-mono text-slate-400">
                  Heatmap artifact generated and saved to filesystem.
                </div>
              )}
            </div>

            {/* Physical Interpretation Callout */}
            <div className="p-3 bg-parchment-subtle/70 rounded border border-border/80 text-xs font-mono text-slate-600 space-y-1">
              <span className="font-bold text-slate-800 block uppercase text-[10px]">
                Scientific Interpretation:
              </span>
              <p>
                Blue areas (&gt; 0 dB) indicate regions where Experiment B achieved higher received power or lower propagation attenuation. Red areas (&lt; 0 dB) indicate where Experiment B suffered severe attenuation or free-space propagation loss (e.g. Friis frequency scaling).
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
