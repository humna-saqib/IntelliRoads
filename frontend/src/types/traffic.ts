export type VehicleType = 'car' | 'motorcycle' | 'bus' | 'emergency' | 'unknown';
export type DensityLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type CongestionStatus = 'CLEAR' | 'CONGESTED';
export type SignalPhase = 'GREEN' | 'YELLOW' | 'RED';

export interface VehicleData {
  vehicle_id: string;
  speed: number;
  lane_id: string;
  lane_position: number;
  position_x: number;
  position_y: number;
  vehicle_type: VehicleType;
  road_id: string;
  waiting_time: number;
  timestamp: number;
}

export interface VehicleListResponse {
  vehicles: VehicleData[];
  total: number;
  timestamp: number;
}

export interface ClassificationData {
  car: number;
  motorcycle: number;
  bus: number;
  emergency?: number;
  percentages: Record<string, number>;
  most_common_type: string;
}

export interface LaneDensity {
  lane_id: string;
  vehicle_count: number;
  lane_length_km: number;
  density: number;
  level: DensityLevel;
  timestamp: number;
}

export interface DensityResponse {
  lanes: LaneDensity[];
  average_density: number;
  timestamp: number;
}

export interface CongestionEvent {
  intersection_id: string;
  status: CongestionStatus;
  density_value: number;
  threshold: number;
  timestamp: string;
  resolved_at?: string;
  direction?: 'N' | 'S' | 'E' | 'W';
}

export interface CongestionResponse {
  events: CongestionEvent[];
  total_congested: number;
  timestamp: number;
}

export interface SignalTiming {
  junction_id: string;
  phase: SignalPhase;
  duration_seconds: number;
  density_level: DensityLevel;
  triggered_at: string;
  reason: string;
}

export interface SignalResponse {
  signals: SignalTiming[];
  timestamp: number;
}

export interface KPIData {
  total_vehicles: number;
  active_intersections: number;
  average_speed: number;
  average_wait_time: number;
  active_alerts: number;
  congestion_percentage: number;
  simulation_time: number;
  data_source: 'LIVE' | 'MOCK';
  fetch_latency_ms: number;
  timestamp: number;
}

export interface IntersectionData {
  id: string;
  name: string;
  signal: SignalPhase;
  congestion_status: CongestionStatus;
  vehicle_count: number;
  density: number;
}

export interface LaneOccupancy {
  lane_id: string;
  occupancy_percent: number;
  occupancy_level: DensityLevel;
  timestamp: number;
}

export interface OccupancyResponse {
  lanes: LaneOccupancy[];
  average_occupancy: number;
  timestamp: number;
}

export interface PerformanceSnapshot {
  sim_time: number;
  avg_waiting_time: number;
  avg_queue_length: number;
  avg_occupancy: number;
  throughput_total: number;
  throughput_tick: number;
  congestion_event_count: number;
  emergency_priority_activations: number;
  signal_decision_frequency: number;
  controller_response_time_ms: number;
  tick_processing_time_ms: number;
  timestamp: number;
}

export interface PerformanceSummary {
  period_label: string;
  sample_count: number;
  avg_waiting_time: number;
  avg_queue_length: number;
  avg_occupancy: number;
  total_throughput: number;
  total_congestion_events: number;
  total_emergency_activations: number;
  total_signal_decisions: number;
  avg_controller_response_time_ms: number;
  avg_tick_processing_time_ms: number;
  start_sim_time: number;
  end_sim_time: number;
}

export interface PerformanceResponse {
  current: PerformanceSnapshot | null;
  per_minute: PerformanceSummary[];
  simulation_summary: PerformanceSummary | null;
  timestamp: number;
}

export type EmergencyVehicleType = 'AMBULANCE' | 'POLICE' | 'FIRETRUCK' | 'UNKNOWN';

export interface EmergencyVehicleState {
  vehicle_id: string;
  vehicle_type: EmergencyVehicleType;
  lane_id: string;
  junction_id?: string;
  speed: number;
  first_detected_at: number;
  last_seen_at: number;
  sim_time: number;
}

export interface EmergencyEvent {
  vehicle_id: string;
  vehicle_type: EmergencyVehicleType;
  lane_id: string;
  junction_id?: string;
  event_type: 'DETECTED' | 'INTERSECTION_CHANGE' | 'CLEARED';
  timestamp: number;
  sim_time: number;
}

export interface EmergencyResponse {
  active_vehicles: EmergencyVehicleState[];
  recent_events: EmergencyEvent[];
  timestamp: number;
}

export interface TrafficSnapshot {
  vehicles: VehicleData[];
  classification: ClassificationData;
  density: DensityResponse;
  congestion: CongestionResponse;
  signals: SignalResponse;
  kpis: KPIData;
  intersections: IntersectionData[];
  occupancy?: OccupancyResponse;
  performance?: PerformanceSnapshot;
  emergency?: EmergencyResponse;
  timestamp: number;
}
