/**
 * TypeScript definitions strictly aligned with the 7 canonical MCP tools
 * registered on the NVIDIA Sionna RT MCP Server.
 */

// 1. check_environment
export interface EnvironmentReport {
  python_version: string;
  sionna_version: string;
  mitsuba_version: string;
  backend: string;
  is_usable: boolean;
}

// 2. list_scenes
export interface SceneItem {
  name: string;
  description: string;
  is_default: boolean;
}

export interface SceneCatalog {
  scenes: SceneItem[];
  default_scene: string;
  count: number;
}

// 3. run_simulation (Point-to-Point)
export interface PointToPointParams {
  scene: string;
  frequency_hz: number;
  tx_position: [number, number, number];
  rx_position: [number, number, number];
  tx_power_dbm: number;
  max_depth?: number;
  antenna_type?: string;
  polarization?: string;
  num_rows?: number;
  num_cols?: number;
  horizontal_spacing?: number;
  vertical_spacing?: number;
  tx_antenna_type?: string;
  rx_antenna_type?: string;
  tx_orientation_deg?: [number, number, number];
  rx_orientation_deg?: [number, number, number];
}

export interface PointToPointResult {
  frequency_hz: number;
  tx_position: [number, number, number];
  rx_position: [number, number, number];
  tx_power_dbm: number;
  backend: string;
  num_paths: number;
  total_path_loss: number | null;
  received_power: number | null;
  path_delays: number[];
  path_distances: number[];
  path_gains: number[];
  interaction_types: string[];
  simulation_id?: string;
  rms_delay_spread_ns?: number | null;
  created_at?: string;
}

// 4. generate_radio_map
export interface RadioMapParams {
  scene_name: string;
  frequency_hz: number;
  tx_name?: string;
  tx_position: [number, number, number];
  tx_power_dbm: number;
  tx_orientation_deg?: [number, number, number];
  antenna_type?: string;
  polarization?: string;
  num_rows?: number;
  num_cols?: number;
  horizontal_spacing?: number;
  vertical_spacing?: number;
  region_mode?: "auto" | "manual";
  auto_margin?: number;
  auto_include_tx?: boolean;
  x_min?: number | null;
  x_max?: number | null;
  y_min?: number | null;
  y_max?: number | null;
  receiver_height?: number;
  cell_size?: number | [number, number];
  samples_per_tx?: number;
  max_depth?: number;
  seed?: number | null;
  los?: boolean;
  specular_reflection?: boolean;
  diffraction?: boolean;
  scattering?: boolean;
  experiment_name?: string | null;
}

export interface RadioMapArtifactPaths {
  rss_heatmap?: string;
  path_gain_heatmap?: string;
  radio_map_data?: string;
  metadata?: string;
}

export interface RadioMapResult {
  status: string;
  experiment_id: string;
  experiment_name?: string | null;
  scene_name: string;
  frequency_hz: number;
  tx_position: [number, number, number];
  tx_power_dbm: number;
  measurement_height: number;
  grid_dimensions: [number, number];
  cell_size: [number, number] | number;
  region_bounds: [number, number, number, number]; // [x_min, x_max, y_min, y_max]
  total_cells: number;
  valid_cells: number;
  zero_power_cells: number;
  coverage_percentage: number;
  min_rss_dbm: number;
  mean_rss_dbm: number;
  max_rss_dbm: number;
  heatmaps_available: {
    rss: boolean;
    path_gain: boolean;
  };
  artifact_paths: RadioMapArtifactPaths;
  simulation_timestamp: string;
  backend_variant: string;
}

// 5. list_experiments
export interface ExperimentSummary {
  experiment_id: string;
  experiment_name?: string | null;
  scene_name: string;
  frequency_hz: number;
  tx_position: [number, number, number];
  tx_power_dbm: number;
  measurement_height: number;
  grid_dimensions: [number, number];
  cell_size: [number, number];
  total_cells: number;
  valid_cells: number;
  coverage_percentage: number;
  mean_rss_dbm: number;
  min_rss_dbm: number;
  max_rss_dbm: number;
  simulation_timestamp: string;
  heatmaps_available: {
    rss: boolean;
    path_gain: boolean;
  };
}

export interface ListExperimentsResponse {
  status: string;
  experiments: ExperimentSummary[];
  count: number;
}

// 6. get_experiment_details
export interface ExperimentDetails extends ExperimentSummary {
  antenna_type: string;
  polarization: string;
  region_bounds: [number, number, number, number];
  solver_parameters: {
    samples_per_tx: number;
    max_depth: number;
    seed?: number | null;
    los: boolean;
    specular_reflection: boolean;
    diffraction: boolean;
    scattering: boolean;
  };
  backend_variant: string;
  array_shapes: Record<string, number[]>;
  array_names: string[];
  artifact_paths: RadioMapArtifactPaths;
}

// 7. compare_experiments
export interface MetricStats {
  mean_diff_db?: number;
  min_diff_db?: number;
  max_diff_db?: number;
  std_diff_db?: number;
  mean_difference?: number;
  min_difference?: number;
  max_difference?: number;
  std_difference?: number;
  total_cells: number;
  valid_cells: number;
  invalid_cells: number;
  valid_cells_percentage: number;
}

export interface ComparisonResult {
  status: string;
  difference_convention: string; // "B - A"
  experiment_a_id: string;
  experiment_b_id: string;
  scene_name: string;
  measurement_height: number;
  frequency_a_hz: number;
  frequency_b_hz: number;
  frequency_match: boolean;
  grid_dimensions: [number, number];
  cell_size: [number, number];
  region_bounds: [number, number, number, number];
  total_cells: number;
  valid_cells: number;
  invalid_cells: number;
  valid_cells_percentage: number;
  rss_difference_metrics: MetricStats;
  path_gain_difference_metrics: MetricStats;
  heatmaps?: {
    rss_diff?: string;
    path_gain_diff?: string;
  };
  artifacts?: {
    rss_diff?: string;
    path_gain_diff?: string;
    comparison_data?: string;
    metadata?: string;
  };
  heatmaps_available?: {
    rss_diff: boolean;
    path_gain_diff: boolean;
  };
  comparison_timestamp: string;
}

// Dashboard Recent Runs Telemetry
export interface RecentRunItem {
  id: string;
  type: "p2p" | "radio_map";
  scene: string;
  carrier: string;
  received_power?: number;
  mean_rss?: number;
  num_paths?: number;
  total_cells?: number;
  created_at: string;
  status: "SUCCESS" | "FAILED" | "RUNNING";
  metrics?: any;
  metadata?: any;
}

export interface TelemetryRecentResponse {
  status: string;
  total_runs: number;
  p2p_runs: number;
  radio_map_runs: number;
  latest_execution?: RecentRunItem | null;
  recent_runs: RecentRunItem[];
}
