import type {
  VehicleListResponse,
  ClassificationData,
  DensityResponse,
  DensityReading,
  DensityHistoryParams,
  CongestionResponse,
  CongestionEvent,
  CongestionHistoryParams,
  PerformanceHistoryParams,
  SignalResponse,
  KPIData,
  IntersectionData,
  TrafficSnapshot,
  OccupancyResponse,
  PerformanceResponse,
  PerformanceSnapshot,
  EmergencyResponse,
} from '../types/traffic';

const BASE_URL = '/api';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('intelliroads_token');
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

function handleAuthError(response: Response) {
  if (response.status === 401) {
    localStorage.removeItem('intelliroads_token');
    window.dispatchEvent(new Event('intelliroads:unauthorized'));
  }
}


async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    handleAuthError(response);
    throw new Error(`API error ${response.status}: ${response.statusText} at ${path}`);
  }
  return response.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    handleAuthError(response);
    throw new Error(`API error ${response.status}: ${response.statusText} at ${path}`);
  }
  return response.json() as Promise<T>;
}

async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'PUT',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    handleAuthError(response);
    throw new Error(`API error ${response.status}: ${response.statusText} at ${path}`);
  }
  return response.json() as Promise<T>;
}


export async function loginApi(username: string, password: string): Promise<{ access_token: string; token_type: string }> {
  const response = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(errorData.detail || `Login error ${response.status}`);
  }
  return response.json();
}

export async function fetchVehicles(): Promise<VehicleListResponse> {
  return apiFetch<VehicleListResponse>('/vehicles');
}

export async function fetchClassification(): Promise<ClassificationData> {
  return apiFetch<ClassificationData>('/classification');
}

export async function fetchDensity(): Promise<DensityResponse> {
  return apiFetch<DensityResponse>('/density');
}

export async function fetchCongestion(): Promise<CongestionResponse> {
  return apiFetch<CongestionResponse>('/congestion');
}

export async function resolveCongestionAlert(eventId: string): Promise<CongestionEvent> {
  return apiPost<CongestionEvent>('/congestion/resolve', { event_id: eventId });
}

export async function fetchCongestionHistory(params: CongestionHistoryParams = {}): Promise<CongestionEvent[]> {
  const searchParams = new URLSearchParams();
  if (params.start_time) searchParams.append('start_time', params.start_time.toString());
  if (params.end_time) searchParams.append('end_time', params.end_time.toString());
  if (params.status) searchParams.append('status', params.status);
  if (params.intersection_id) searchParams.append('intersection_id', params.intersection_id);
  if (params.limit) searchParams.append('limit', params.limit.toString());

  const queryString = searchParams.toString();
  const path = `/congestion/history${queryString ? `?${queryString}` : ''}`;
  return apiFetch<CongestionEvent[]>(path);
}

export async function fetchDensityHistory(params: DensityHistoryParams = {}): Promise<DensityReading[]> {
  const searchParams = new URLSearchParams();
  if (params.lane_id) searchParams.append('lane_id', params.lane_id);
  if (params.start_time) searchParams.append('start_time', params.start_time.toString());
  if (params.end_time) searchParams.append('end_time', params.end_time.toString());
  if (params.level) searchParams.append('level', params.level);
  if (params.limit) searchParams.append('limit', params.limit.toString());

  const queryString = searchParams.toString();
  const path = `/density/history${queryString ? `?${queryString}` : ''}`;
  return apiFetch<DensityReading[]>(path);
}

export async function fetchPerformanceHistory(params: PerformanceHistoryParams = {}): Promise<PerformanceSnapshot[]> {
  const searchParams = new URLSearchParams();
  if (params.start_time) searchParams.append('start_time', params.start_time.toString());
  if (params.end_time) searchParams.append('end_time', params.end_time.toString());
  if (params.limit) searchParams.append('limit', params.limit.toString());

  const queryString = searchParams.toString();
  const path = `/performance/history${queryString ? `?${queryString}` : ''}`;
  return apiFetch<PerformanceSnapshot[]>(path);
}

export async function fetchSignals(): Promise<SignalResponse> {
  return apiFetch<SignalResponse>('/signals');
}

export async function fetchKPIs(): Promise<KPIData> {
  return apiFetch<KPIData>('/kpis');
}

export async function fetchIntersections(): Promise<IntersectionData[]> {
  return apiFetch<IntersectionData[]>('/intersections');
}

export async function fetchOccupancy(): Promise<OccupancyResponse> {
  return apiFetch<OccupancyResponse>('/occupancy');
}

export async function fetchPerformance(minutes: number = 10): Promise<PerformanceResponse> {
  return apiFetch<PerformanceResponse>(`/performance?minutes=${minutes}`);
}

export async function fetchEmergency(): Promise<EmergencyResponse> {
  return apiFetch<EmergencyResponse>('/emergency');
}

export type ControllerMode = 'RULE_BASED' | 'DQN';

export async function fetchControllerMode(): Promise<{ mode: ControllerMode }> {
  return apiFetch<{ mode: ControllerMode }>('/rl/mode');
}

export async function setControllerMode(mode: ControllerMode): Promise<{ status: string; mode: ControllerMode }> {
  return apiPost<{ status: string; mode: ControllerMode }>('/rl/mode', { mode });
}

export interface JunctionThresholds {
  low_threshold: number;
  medium_threshold: number;
  congestion_threshold: number;
}

export async function fetchAllThresholds(): Promise<Record<string, JunctionThresholds>> {
  return apiFetch<Record<string, JunctionThresholds>>('/settings/thresholds');
}

export async function updateJunctionThresholds(
  junctionId: string,
  thresholds: JunctionThresholds,
): Promise<JunctionThresholds> {
  return apiPut<JunctionThresholds>(`/settings/thresholds/${junctionId}`, thresholds);
}

export async function fetchAllData(): Promise<Omit<TrafficSnapshot, 'vehicles' | 'timestamp'> & { vehicles: VehicleListResponse; timestamp: number }> {
  const [vehiclesRes, classification, density, congestion, signals, kpis, intersections, occupancy, emergency] =
    await Promise.all([
      fetchVehicles(),
      fetchClassification(),
      fetchDensity(),
      fetchCongestion(),
      fetchSignals(),
      fetchKPIs(),
      fetchIntersections(),
      fetchOccupancy(),
      fetchEmergency(),
    ]);

  return {
    vehicles: vehiclesRes,
    classification,
    density,
    congestion,
    signals,
    kpis,
    intersections,
    occupancy,
    emergency,
    timestamp: Date.now(),
  };
}
