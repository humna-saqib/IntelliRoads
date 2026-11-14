import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HomePage from '../pages/HomePage';
import * as TrafficContext from '../context/TrafficContext';
import { ToastProvider } from '../context/ToastContext';

// Mock API calls made by HomePage on mount
vi.mock('../services/api', () => ({
  fetchControllerMode: vi.fn().mockResolvedValue({ mode: 'RULE_BASED' }),
  fetchPerformance: vi.fn().mockResolvedValue({ per_minute: [] }),
  fetchIntersections: vi.fn().mockResolvedValue([]),
  setControllerMode: vi.fn().mockResolvedValue({ status: 'ok' }),
  injectVehicles: vi.fn().mockResolvedValue({ status: 'ok' }),
}));

function renderHomePage() {
  return render(
    <ToastProvider>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </ToastProvider>
  );
}

describe('Home status sentence', () => {
  const baseTrafficState = {
    isBackendOffline: false,
    isLoading: false,
    kpis: {
      total_vehicles: 12,
      average_speed: 11.2,
      average_wait_time: 4.5,
      congestion_percentage: 5.0,
      active_alerts: 0,
      emergency_vehicles_active: 0,
    },
    kpiHistory: [],
    intersections: [
      { id: 'junctionA', name: 'Northwest Square', signal: 'GREEN', congestion_status: 'CLEAR', vehicle_count: 3, density: 10 },
      { id: 'junctionB', name: 'Northeast Plaza', signal: 'GREEN', congestion_status: 'CLEAR', vehicle_count: 2, density: 8 },
      { id: 'junctionC', name: 'Southeast Gateway', signal: 'RED', congestion_status: 'CLEAR', vehicle_count: 4, density: 12 },
      { id: 'junctionD', name: 'Southwest Crossing', signal: 'RED', congestion_status: 'CLEAR', vehicle_count: 3, density: 9 },
    ],
    signals: null,
    congestion: null,
    vehicles: [],
    classification: null,
    density: null,
    occupancy: null,
    emergency: null,
    isConnected: true,
    lastUpdate: Date.now(),
    lastUpdatedAt: 'Just now',
    connectionStatus: 'connected' as const,
    retryConnection: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders flowing message and green styling when traffic is light and clear', () => {
    vi.spyOn(TrafficContext, 'useTraffic').mockReturnValue(baseTrafficState as any);

    renderHomePage();

    const statusBanner = screen.getByRole('status');
    expect(statusBanner).toBeInTheDocument();
    // Flowing message
    expect(statusBanner).toHaveTextContent(/flowing smoothly/i);
    // Green border indicator
    expect(statusBanner).toHaveClass('border-l-ok');
  });

  it('names the real junction and displays the red alert state when a junction has heavy congestion', () => {
    vi.spyOn(TrafficContext, 'useTraffic').mockReturnValue({
      ...baseTrafficState,
      intersections: [
        { id: 'junctionA', name: 'Northwest Square', signal: 'RED', congestion_status: 'CONGESTED', vehicle_count: 25, density: 45 },
        { id: 'junctionB', name: 'Northeast Plaza', signal: 'GREEN', congestion_status: 'CLEAR', vehicle_count: 4, density: 12 },
        { id: 'junctionC', name: 'Southeast Gateway', signal: 'GREEN', congestion_status: 'CLEAR', vehicle_count: 3, density: 9 },
        { id: 'junctionD', name: 'Southwest Crossing', signal: 'RED', congestion_status: 'CLEAR', vehicle_count: 2, density: 7 },
      ],
      kpis: {
        ...baseTrafficState.kpis,
        congestion_percentage: 35.0,
        active_alerts: 1,
      },
    } as any);

    renderHomePage();

    const statusBanner = screen.getByRole('status');
    expect(statusBanner).toBeInTheDocument();
    // Names the real junction (Northwest Square, not junctionA)
    expect(statusBanner).toHaveTextContent('Heavy congestion at Northwest Square');
    // Red indicator
    expect(statusBanner).toHaveClass('border-l-bad');
  });

  it('names multiple real junctions if multiple intersections are congested', () => {
    vi.spyOn(TrafficContext, 'useTraffic').mockReturnValue({
      ...baseTrafficState,
      intersections: [
        { id: 'junctionA', name: 'Northwest Square', signal: 'RED', congestion_status: 'CONGESTED', vehicle_count: 25, density: 45 },
        { id: 'junctionC', name: 'Southeast Gateway', signal: 'RED', congestion_status: 'CONGESTED', vehicle_count: 22, density: 42 },
        { id: 'junctionB', name: 'Northeast Plaza', signal: 'GREEN', congestion_status: 'CLEAR', vehicle_count: 4, density: 12 },
        { id: 'junctionD', name: 'Southwest Crossing', signal: 'GREEN', congestion_status: 'CLEAR', vehicle_count: 2, density: 7 },
      ],
      kpis: {
        ...baseTrafficState.kpis,
        congestion_percentage: 55.0,
        active_alerts: 2,
      },
    } as any);

    renderHomePage();

    const statusBanner = screen.getByRole('status');
    expect(statusBanner).toBeInTheDocument();
    expect(statusBanner).toHaveTextContent('Heavy congestion at Northwest Square and Southeast Gateway');
    expect(statusBanner).toHaveClass('border-l-bad');
  });
});
