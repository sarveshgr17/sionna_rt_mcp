import {
  ComparisonResult,
  EnvironmentReport,
  ExperimentDetails,
  ListExperimentsResponse,
  PointToPointParams,
  PointToPointResult,
  RadioMapParams,
  RadioMapResult,
  SceneCatalog,
  SceneGeometry,
  TelemetryRecentResponse,
} from "@/types/mcp";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

export interface ToolCallResponse<T = any> {
  status: "success" | "error";
  data?: T;
  error?: string;
}

export interface HealthResponse {
  status: string;
  mcp_connected: boolean;
  mcp_server_url: string;
  tool_count: number;
  tools: Array<{
    name: string;
    description: string;
    inputSchema: any;
  }>;
}

export class McpClientError extends Error {
  constructor(message: string, public readonly details?: any) {
    super(message);
    this.name = "McpClientError";
  }
}

/**
 * Centralized MCP Client connecting to the Sionna Lab Backend Adapter.
 */
export const mcpClient = {
  /**
   * Check health and connection to MCP server.
   */
  async getHealth(): Promise<HealthResponse> {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) {
      throw new McpClientError(`Health check failed with HTTP ${res.status}`);
    }
    return res.json();
  },

  /**
   * Generic low-level tool invocation through MCP bridge.
   */
  async callTool<T = any>(name: string, args: Record<string, any> = {}): Promise<T> {
    const res = await fetch(`${API_BASE}/mcp/call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, arguments: args }),
    });

    const json: ToolCallResponse<T> = await res.json();
    if (!res.ok || json.status === "error") {
      throw new McpClientError(json.error || `Tool '${name}' failed`, json);
    }

    return json.data as T;
  },

  // 1. check_environment
  async checkEnvironment(): Promise<EnvironmentReport> {
    return this.callTool<EnvironmentReport>("check_environment");
  },

  // 2. list_scenes
  async listScenes(): Promise<SceneCatalog> {
    return this.callTool<SceneCatalog>("list_scenes");
  },

  // 3. run_simulation (Point-to-Point Ray Tracing)
  async runSimulation(params: PointToPointParams): Promise<PointToPointResult> {
    return this.callTool<PointToPointResult>("run_simulation", params);
  },

  // 4. generate_radio_map (Spatial 2D Coverage)
  async generateRadioMap(params: RadioMapParams): Promise<RadioMapResult> {
    return this.callTool<RadioMapResult>("generate_radio_map", params);
  },

  // 5. list_experiments
  async listExperiments(): Promise<ListExperimentsResponse> {
    return this.callTool<ListExperimentsResponse>("list_experiments");
  },

  // 6. get_experiment_details
  async getExperimentDetails(experimentId: string): Promise<ExperimentDetails> {
    return this.callTool<ExperimentDetails>("get_experiment_details", {
      experiment_id: experimentId,
    });
  },

  // 7. compare_experiments
  async compareExperiments(
    experimentIdA: string,
    experimentIdB: string,
    generateHeatmaps: boolean = true
  ): Promise<ComparisonResult> {
    return this.callTool<ComparisonResult>("compare_experiments", {
      experiment_id_a: experimentIdA,
      experiment_id_b: experimentIdB,
      generate_heatmaps: generateHeatmaps,
    });
  },

  // Telemetry: Recent Runs for Workspace Dashboard
  async getTelemetryRecent(): Promise<TelemetryRecentResponse> {
    const res = await fetch(`${API_BASE}/telemetry/recent`);
    if (!res.ok) {
      throw new McpClientError(`Telemetry fetch failed with HTTP ${res.status}`);
    }
    return res.json();
  },

  // Matrix Data: Read .npz numerical arrays
  async getMatrixData(experimentId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/matrix/${encodeURIComponent(experimentId)}`);
    if (!res.ok) {
      throw new McpClientError(`Matrix data fetch failed with HTTP ${res.status}`);
    }
    return res.json();
  },

  // 3D Scene Geometry: Read real meshes and vertices for WebGL rendering
  async getSceneGeometry(sceneName: string): Promise<SceneGeometry> {
    const res = await fetch(`${API_BASE}/scenes/${encodeURIComponent(sceneName)}/geometry`);
    if (!res.ok) {
      throw new McpClientError(`Scene geometry fetch failed with HTTP ${res.status}`);
    }
    return res.json();
  },

  // Safe Artifact URL constructor
  getArtifactUrl(path?: string): string {
    if (!path) return "";
    if (path.startsWith("http://") || path.startsWith("https://")) {
      return path;
    }
    return `${API_BASE}/artifacts/${encodeURIComponent(path)}`;
  },
};

