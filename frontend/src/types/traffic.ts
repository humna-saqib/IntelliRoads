export type VehicleType = 'car' | 'motorcycle' | 'bus' | 'truck' | 'unknown';
export type DensityLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type CongestionStatus = 'CLEAR' | 'CONGESTED';
export type SignalPhase = 'GREEN' | 'YELLOW' | 'RED';

export interface VehicleData {
  vehicle_id: string;
  speed: number;
  lane_id: string;
  position_x: number;
  position_y: number;
  vehicle_type: VehicleType;
  road_id: string;
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
  truck: number;
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

export interface TrafficSnapshot {
  vehicles: VehicleData[];
  classification: ClassificationData;
  density: DensityResponse;
  congestion: CongestionResponse;
  signals: SignalResponse;
  kpis: KPIData;
  intersections: IntersectionData[];
  timestamp: number;
}
