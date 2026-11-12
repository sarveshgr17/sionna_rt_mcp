import React from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Radio,
  Map,
  FolderGit2,
  GitCompare,
  Sliders,
  Terminal,
  FileCode2,
  Settings,
  Waves,
} from "lucide-react";
import { useEnvironment, useMcpHealth } from "@/hooks/useMcp";

const NAV_ITEMS = [
  { path: "/", label: "Overview", icon: LayoutDashboard },
  { path: "/p2p", label: "Point-to-Point Simulation", icon: Radio },
  { path: "/radio-maps", label: "Radio Maps", icon: Map },
  { path: "/experiments", label: "Experiments", icon: FolderGit2 },
  { path: "/compare", label: "Compare Experiments", icon: GitCompare },
  { path: "/system", label: "System / Environment", icon: Sliders },
];

export function Sidebar() {
  const { data: health } = useMcpHealth();
  const { data: env } = useEnvironment();

  const isConnected = health?.mcp_connected ?? false;
  const sionnaVersion = env?.sionna_version || "2.2.0";
  const mitsubaVersion = env?.mitsuba_version || "3.9.1";
  const backendShort = env?.backend?.includes("llvm") ? "CPU-LLVM" : "RTX-6000";

  return (
    <aside className="w-64 border-r border-border bg-parchment-sidebar flex flex-col justify-between select-none shrink-0 h-screen sticky top-0">
      {/* Top: Branding & Navigation */}
      <div>
        {/* Brand Header */}
        <div className="p-4 border-b border-border/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded bg-rust flex items-center justify-center text-white shadow-sm">
              <Waves className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-slate-900 tracking-tight">Sionna Lab</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-parchment-subtle border border-border text-slate-600 font-semibold">
                  v0.9.4-rc2
                </span>
              </div>
              <p className="text-[11px] text-slate-500 truncate mt-0.5 font-medium">
                Explore the physics of wireless propagation
              </p>
            </div>
          </div>
        </div>

        {/* Navigation Section */}
        <div className="px-3 py-4">
          <div className="px-3 pb-2 text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase">
            Simulation Suites
          </div>
          <nav className="space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 px-3 py-2 rounded text-xs font-medium transition-all group relative ${
                      isActive
                        ? "bg-white text-rust font-semibold shadow-technical border border-border/90"
                        : "text-slate-600 hover:text-slate-900 hover:bg-parchment-subtle/80"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute left-0 top-1.5 bottom-1.5 w-1 bg-rust rounded-r" />
                      )}
                      <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-rust" : "text-slate-500 group-hover:text-slate-700"}`} />
                      <span className="truncate">{item.label}</span>
                    </>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Bottom: MCP Daemon Status & Hardware Specs */}
      <div className="p-3 border-t border-border bg-parchment-subtle/40">
        <div className="p-3 rounded-md bg-white border border-border/80 shadow-technical text-[11px] space-y-2">
          {/* Server Connection Indicator */}
          <div className="flex items-center justify-between pb-1.5 border-b border-border/60">
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`} />
              <span className="font-semibold text-slate-800">MCP Server</span>
            </div>
            <span className={`font-mono text-[10px] ${isConnected ? "text-green-600 font-bold" : "text-red-500"}`}>
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>

          {/* Endpoint IP */}
          <div className="text-[10px] font-mono text-slate-500 flex justify-between">
            <span>ENDPOINT</span>
            <span className="text-slate-700 font-medium">127.0.0.1:8000</span>
          </div>

          {/* Sionna & Mitsuba Runtime */}
          <div className="text-[10px] font-mono text-slate-500 flex justify-between">
            <span>Sionna RT</span>
            <span className="text-slate-700 font-medium">v{sionnaVersion} Ready</span>
          </div>

          <div className="text-[10px] font-mono text-slate-500 flex justify-between">
            <span>Backend</span>
            <span className="text-slate-700 font-medium">Mitsuba {mitsubaVersion}</span>
          </div>

          {/* Bottom Icons & Accelerator Badge */}
          <div className="flex items-center justify-between pt-1 border-t border-border/60 text-slate-400">
            <div className="flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5 hover:text-slate-600 cursor-pointer" />
              <FileCode2 className="w-3.5 h-3.5 hover:text-slate-600 cursor-pointer" />
              <Settings className="w-3.5 h-3.5 hover:text-slate-600 cursor-pointer" />
            </div>
            <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-parchment-subtle border border-border text-slate-600 font-bold">
              {backendShort}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}

