import type {
  VehicleListResponse,
  ClassificationData,
  DensityResponse,
  CongestionResponse,
  SignalResponse,
  KPIData,
  IntersectionData,
  TrafficSnapshot,
  OccupancyResponse,
} from '../types/traffic';

const BASE_URL = '/api';

async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Accept': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${response.statusText} at ${path}`);
  }
  return response.json() as Promise<T>;
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

export async function fetchAllData(): Promise<Omit<TrafficSnapshot, 'vehicles' | 'timestamp'> & { vehicles: VehicleListResponse; timestamp: number }> {
  const [vehiclesRes, classification, density, congestion, signals, kpis, intersections, occupancy] =
    await Promise.all([
      fetchVehicles(),
      fetchClassification(),
      fetchDensity(),
      fetchCongestion(),
      fetchSignals(),
      fetchKPIs(),
      fetchIntersections(),
      fetchOccupancy(),
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
    timestamp: Date.now(),
  };
}
