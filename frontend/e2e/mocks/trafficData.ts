/**
 * Reusable mock data for Playwright E2E tests.
 * Allows all tests to run completely isolated without needing SUMO or a backend.
 */

export const MOCK_LOGIN_SUCCESS = {
  access_token: 'mock-valid-e2e-token-xyz',
  token_type: 'bearer',
};

export const MOCK_INTERSECTIONS = [
  { id: 'junctionA', name: 'Northwest Square', signal: 'GREEN', congestion_status: 'CLEAR', vehicle_count: 5, density: 12.0 },
  { id: 'junctionB', name: 'Northeast Plaza', signal: 'RED', congestion_status: 'CLEAR', vehicle_count: 3, density: 8.5 },
  { id: 'junctionC', name: 'Southeast Gateway', signal: 'GREEN', congestion_status: 'CLEAR', vehicle_count: 4, density: 10.2 },
  { id: 'junctionD', name: 'Southwest Crossing', signal: 'RED', congestion_status: 'CLEAR', vehicle_count: 2, density: 6.8 },
];

export const MOCK_KPIS = {
  total_vehicles: 14,
  average_speed: 11.5,
  average_wait_time: 3.8,
  congestion_percentage: 6.5,
  active_alerts: 0,
  emergency_vehicles_active: 0,
};

export const MOCK_SIGNALS = {
  junctions: {
    junctionA: { junction_id: 'junctionA', phase: 'GREEN', duration_seconds: 25, time_in_phase: 5, reason: 'obs-v2 DQN action: EXTEND_GREEN' },
    junctionB: { junction_id: 'junctionB', phase: 'RED', duration_seconds: 30, time_in_phase: 10, reason: 'LOW density on North approach -> 15s green phase' },
    junctionC: { junction_id: 'junctionC', phase: 'GREEN', duration_seconds: 25, time_in_phase: 6, reason: 'obs-v2 DQN action: EXTEND_GREEN' },
    junctionD: { junction_id: 'junctionD', phase: 'RED', duration_seconds: 30, time_in_phase: 11, reason: 'LOW density on South approach -> 15s green phase' },
  },
};

export const MOCK_DENSITY = {
  lane_densities: {
    lane_A_west_in: 12.0,
    lane_B_north_in: 8.5,
    lane_C_east_in: 10.2,
    lane_D_south_in: 6.8,
  },
};

export const MOCK_OCCUPANCY = {
  occupancies: {
    junctionA: 15.0,
    junctionB: 10.0,
    junctionC: 12.0,
    junctionD: 8.0,
  },
};

export const MOCK_EMERGENCY = {
  active_emergencies: [],
};

export const MOCK_CONTROLLER_MODE = {
  mode: 'RULE_BASED',
  file: null,
  obs_version: 'obs-v2',
  selected_episode: null,
  available_checkpoints: [],
};

export const MOCK_VEHICLES = {
  vehicles: [
    { id: 'veh_01', type: 'car', speed: 11.2, waiting_time: 2.1, lane_id: 'lane_A_west_in', route_id: 'route_01', distance: 150.0 },
    { id: 'veh_02', type: 'bus', speed: 9.4, waiting_time: 4.5, lane_id: 'lane_B_north_in', route_id: 'route_02', distance: 120.0 },
    { id: 'veh_03', type: 'motorcycle', speed: 13.0, waiting_time: 1.0, lane_id: 'lane_C_east_in', route_id: 'route_03', distance: 90.0 },
  ],
};

export const MOCK_CLASSIFICATION = {
  counts: { car: 10, bus: 2, motorcycle: 2, emergency: 0 },
};

export const MOCK_CONGESTION = {
  total_congested: 0,
  congested_lanes: [],
};

export const MOCK_CONGESTION_HISTORY = [
  {
    id: 1,
    timestamp: 1700000000,
    junction_id: 'junctionA',
    lane_id: 'lane_A_west_in',
    density: 48.2,
    vehicle_count: 18,
    congestion_threshold: 40.0,
    severity: 'HIGH',
    resolved: true,
    duration_seconds: 240,
  },
];

export const MOCK_PERFORMANCE = {
  current: {
    avg_waiting_time: 2.5,
    avg_queue_length: 1.1,
    avg_occupancy: 6.8,
    throughput_total: 1220,
    congestion_event_count: 1,
    emergency_priority_activations: 1,
    signal_decision_frequency: 45,
    controller_response_time_ms: 1.2,
  },
  simulation_summary: {
    avg_waiting_time: 2.5,
    avg_queue_length: 1.1,
    avg_occupancy: 6.8,
    total_throughput: 1220,
    total_congestion_events: 1,
    total_emergency_activations: 1,
    total_signal_decisions: 45,
  },
  per_minute: [
    {
      period_label: 'minute_1',
      sample_count: 60,
      avg_waiting_time: 2.5,
      avg_queue_length: 1.1,
      avg_occupancy: 6.8,
      total_throughput: 40,
      total_congestion_events: 0,
      total_emergency_activations: 0,
      total_signal_decisions: 10,
      avg_controller_response_time_ms: 1.1,
      avg_tick_processing_time_ms: 0.8,
    },
  ],
};

export const MOCK_PERFORMANCE_HISTORY = [
  {
    timestamp: 1700000000,
    sim_time: 120.0,
    avg_waiting_time: 2.5,
    avg_queue_length: 1.1,
    avg_occupancy: 6.8,
    throughput_total: 1220,
    congestion_event_count: 1,
    emergency_activations: 1,
    controller_response_time_ms: 1.2,
  },
];

export const MOCK_DENSITY_HISTORY = [
  {
    timestamp: 1700000000,
    sim_time: 120.0,
    lane_id: 'lane_A_west_in',
    density: 12.0,
    vehicle_count: 5,
    density_level: 'LOW',
    queue_length: 1.0,
    avg_waiting_time: 2.0,
  },
];

export const MOCK_SETTINGS = {
  low_threshold: 15,
  medium_threshold: 30,
  congestion_threshold: 45,
  poll_interval_seconds: 2,
};

