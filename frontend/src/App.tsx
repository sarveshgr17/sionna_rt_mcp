import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SceneProvider } from "@/context/SceneContext";
import { AppLayout } from "@/components/layout/AppLayout";
import { Overview } from "@/pages/Overview";
import { PointToPoint } from "@/pages/PointToPoint";
import { RadioMaps } from "@/pages/RadioMaps";
import { Experiments } from "@/pages/Experiments";
import { CompareExperiments } from "@/pages/CompareExperiments";
import { SystemDiagnostics } from "@/pages/SystemDiagnostics";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 5000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SceneProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Overview />} />
              <Route path="/p2p" element={<PointToPoint />} />
              <Route path="/radio-maps" element={<RadioMaps />} />
              <Route path="/experiments" element={<Experiments />} />
              <Route path="/compare" element={<CompareExperiments />} />
              <Route path="/system" element={<SystemDiagnostics />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </SceneProvider>
    </QueryClientProvider>
  );
}

export default App;

