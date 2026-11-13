import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { mcpClient } from "@/services/mcp/client";
import {
  PointToPointParams,
  PointToPointResult,
  RadioMapParams,
  RadioMapResult,
} from "@/types/mcp";

export function useMcpHealth() {
  return useQuery({
    queryKey: ["mcp", "health"],
    queryFn: () => mcpClient.getHealth(),
    refetchInterval: 10000,
    retry: 2,
  });
}

export function useEnvironment() {
  return useQuery({
    queryKey: ["mcp", "environment"],
    queryFn: () => mcpClient.checkEnvironment(),
    staleTime: 30000,
    retry: 2,
  });
}

export function useScenes() {
  return useQuery({
    queryKey: ["mcp", "scenes"],
    queryFn: () => mcpClient.listScenes(),
    staleTime: 60000,
  });
}

export function useSceneGeometry(sceneName: string) {
  return useQuery({
    queryKey: ["mcp", "scene-geometry", sceneName],
    queryFn: () => mcpClient.getSceneGeometry(sceneName),
    staleTime: Infinity,
    enabled: Boolean(sceneName),
  });
}

export function useTelemetryRecent() {
  return useQuery({
    queryKey: ["mcp", "telemetry", "recent"],
    queryFn: () => mcpClient.getTelemetryRecent(),
    refetchInterval: 15000,
  });
}

export function useExperiments() {
  return useQuery({
    queryKey: ["mcp", "experiments"],
    queryFn: () => mcpClient.listExperiments(),
  });
}

export function useExperimentDetails(experimentId?: string) {
  return useQuery({
    queryKey: ["mcp", "experiment", experimentId],
    queryFn: () => mcpClient.getExperimentDetails(experimentId!),
    enabled: !!experimentId,
  });
}

export function useRunSimulation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: PointToPointParams) => mcpClient.runSimulation(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mcp", "telemetry"] });
    },
  });
}

export function useGenerateRadioMap() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: RadioMapParams) => mcpClient.generateRadioMap(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mcp", "experiments"] });
      queryClient.invalidateQueries({ queryKey: ["mcp", "telemetry"] });
    },
  });
}

export function useCompareExperiments() {
  return useMutation({
    mutationFn: ({
      experimentIdA,
      experimentIdB,
      generateHeatmaps = true,
    }: {
      experimentIdA: string;
      experimentIdB: string;
      generateHeatmaps?: boolean;
    }) => mcpClient.compareExperiments(experimentIdA, experimentIdB, generateHeatmaps),
  });
}

