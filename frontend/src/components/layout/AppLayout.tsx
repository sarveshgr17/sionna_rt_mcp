import React from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-parchment text-slate-900 font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 p-6 overflow-y-auto max-w-[1700px] w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

