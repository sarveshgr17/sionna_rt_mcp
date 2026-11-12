import React from "react";
import { Link, useLocation } from "react-router-dom";
import { 
  Box, 
  ChevronDown, 
  Code2, 
  FileText, 
  ExternalLink,
  Cpu,
  User
} from "lucide-react";
import { useEnvironment, useMcpHealth, useScenes } from "@/hooks/useMcp";

export function Header() {
  const location = useLocation();
  const { data: health } = useMcpHealth();
  const { data: env } = useEnvironment();
  const { data: scenes } = useScenes();

  // Page titles
  const getBreadcrumb = () => {
    switch (location.pathname) {
      case "/":
        return "Workstation";
      case "/p2p":
        return "Point-to-Point Simulation";
      case "/radio-maps":
        return "Radio Maps";
      case "/experiments":
        return "Experiments Archive";
      case "/compare":
        return "Compare Experiments";
      case "/system":
        return "System / Environment Diagnostics";
      default:
        return "Workstation";
    }
  };

  const isConnected = health?.mcp_connected ?? false;
  const backendName = env?.backend || "llvm_ad_mono_polarized";
  const defaultScene = scenes?.default_scene || "simple_reflector";

  return (
    <header className="h-12 border-b border-border bg-white px-4 flex items-center justify-between select-none">
      {/* Left: Breadcrumbs & Engine Indicators */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium">
          <Link to="/" className="hover:text-slate-800 transition-colors">Sionna Lab</Link>
          <span>/</span>
          <span className="text-slate-800 font-semibold">{getBreadcrumb()}</span>
        </div>

        <div className="h-4 w-[1px] bg-border mx-1" />

        {/* Scene Selector Dropdown Pill */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-parchment-subtle rounded border border-border text-xs font-mono text-slate-700 cursor-pointer hover:bg-parchment transition-colors">
          <Box className="w-3.5 h-3.5 text-rust" />
          <span className="font-medium">Scene: {defaultScene}</span>
          <ChevronDown className="w-3 h-3 text-slate-400 ml-0.5" />
        </div>

        {/* Engine Variant Pill */}
        <div className="flex items-center gap-1.5 px-2 py-1 bg-parchment-subtle rounded border border-border text-xs font-mono text-slate-600">
          <Code2 className="w-3 h-3 text-slate-500" />
          <span>{backendName}</span>
        </div>
      </div>

      {/* Right: Simulator Status & Actions */}
      <div className="flex items-center gap-3">
        {/* Status indicator */}
        <div className={`px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold flex items-center gap-1.5 border ${
          isConnected 
            ? "bg-green-50 text-green-700 border-green-200" 
            : "bg-red-50 text-red-700 border-red-200"
        }`}>
          <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
          {isConnected ? "SIMULATOR READY" : "SIMULATOR OFFLINE"}
        </div>

        {/* Documentation link */}
        <a 
          href="https://nvlabs.github.io/sionna/" 
          target="_blank" 
          rel="noreferrer"
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-600 hover:text-slate-900 rounded border border-border bg-white hover:bg-parchment transition-colors"
        >
          <FileText className="w-3.5 h-3.5 text-slate-500" />
          <span>Docs</span>
        </a>

        {/* MCP Inspector button */}
        <Link 
          to="/system"
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-600 hover:text-slate-900 rounded border border-border bg-white hover:bg-parchment transition-colors"
        >
          <Cpu className="w-3.5 h-3.5 text-rust" />
          <span>MCP Inspector</span>
        </Link>

        {/* User avatar */}
        <div className="w-7 h-7 rounded-full bg-rust flex items-center justify-center text-white shadow-sm ring-1 ring-rust/20">
          <User className="w-4 h-4" />
        </div>
      </div>
    </header>
  );
}

