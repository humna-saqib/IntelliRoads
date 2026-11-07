import { fetchIntersections } from '../services/api';
import type { IntersectionData } from '../types/traffic';

/**
 * Plain-language terminology and formatting helpers for non-technical users.
 * Replaces academic/technical terms (DQN, veh/km, occupancy, junctionA)
 * with intuitive, human-friendly phrases and standard units (km/h, minutes).
 */

export const PLAIN_TERMS = {
  // Controller modes
  dqn: 'Smart AI',
  doubleDqn: 'Smart AI',
  ruleBased: 'Standard timing',

  // Junction names (real names from /api/intersections backend: Northwest Square, Northeast Plaza, Southeast Gateway, Southwest Crossing)
  junctionA: 'Northwest Square',
  junctionB: 'Northeast Plaza',
  junctionC: 'Southeast Gateway',
  junctionD: 'Southwest Crossing',

  // Traffic metrics
  occupancy: 'how full the road is',
  occupancyLabel: 'Road fullness',
  densityUnit: 'cars per km',
  densityShortUnit: 'cars/km',
  speedUnit: 'km/h',
  waitTimeUnit: 'minutes',

  // Traffic states
  lowDensity: 'Light traffic',
  mediumDensity: 'Moderate traffic',
  highDensity: 'Heavy traffic',
  clear: 'Flowing smoothly',
  congested: 'Traffic jam',
} as const;

/**
 * Fallback map of real intersection names matching backend/app/core/state_store.py
 * and GET /api/intersections.
 */
export const JUNCTION_REAL_NAMES: Record<string, string> = {
  junctionA: 'Northwest Square',
  junctionB: 'Northeast Plaza',
  junctionC: 'Southeast Gateway',
  junctionD: 'Southwest Crossing',
};

// Dynamic runtime cache populated from /api/intersections or WebSocket snapshots
const runtimeJunctionNames: Record<string, string> = {};
let fetchPromise: Promise<Record<string, string>> | null = null;

/**
 * Register intersection names at runtime (e.g. from /api/intersections or live WS snapshots).
 */
export function registerIntersectionNames(
  intersections: Array<{ id: string; name?: string } | IntersectionData> | Record<string, string>
): void {
  if (!intersections) return;
  if (Array.isArray(intersections)) {
    for (const item of intersections) {
      if (item && item.id && item.name) {
        runtimeJunctionNames[item.id] = item.name;
      }
    }
  } else if (typeof intersections === 'object') {
    for (const [id, name] of Object.entries(intersections)) {
      if (id && name && typeof name === 'string') {
        runtimeJunctionNames[id] = name;
      }
    }
  }
}

/**
 * Fetch intersection names from the backend API at runtime.
 * Falls back to the static map if the API is offline or unreachable.
 */
export async function loadIntersectionNamesFromApi(): Promise<Record<string, string>> {
  if (fetchPromise) return fetchPromise;
  fetchPromise = (async () => {
    try {
      const data = await fetchIntersections();
      registerIntersectionNames(data);
    } catch {
      // Offline fallback: JUNCTION_REAL_NAMES is retained
    }
    return { ...JUNCTION_REAL_NAMES, ...runtimeJunctionNames };
  })();
  return fetchPromise;
}

// Kick off background fetch in browser environments
if (typeof window !== 'undefined') {
  loadIntersectionNamesFromApi().catch(() => {});
}

/**
 * Get the human-friendly name for a junction ID.
 * Reads from the live API cache first, falling back to JUNCTION_REAL_NAMES.
 */
export function getJunctionName(id: string): string {
  if (!id) return 'Unknown junction';

  // 1. Direct runtime match from API
  if (runtimeJunctionNames[id]) return runtimeJunctionNames[id];

  // 2. Direct static fallback match
  if (JUNCTION_REAL_NAMES[id]) return JUNCTION_REAL_NAMES[id];

  // 3. Pattern match for embedded IDs (e.g. lane_A_west_in, junction_A)
  const lookup = (key: string) => runtimeJunctionNames[key] || JUNCTION_REAL_NAMES[key];
  if (/junction[_-]?A\b/i.test(id) || /_A_/i.test(id)) return lookup('junctionA');
  if (/junction[_-]?B\b/i.test(id) || /_B_/i.test(id)) return lookup('junctionB');
  if (/junction[_-]?C\b/i.test(id) || /_C_/i.test(id)) return lookup('junctionC');
  if (/junction[_-]?D\b/i.test(id) || /_D_/i.test(id)) return lookup('junctionD');

  return id;
}

/** Convert controller mode to a friendly user-facing label. */
export function getControllerModeName(mode: string | null | undefined): string {
  if (!mode) return 'Standard timing';
  const upper = mode.toUpperCase();
  if (upper.includes('DQN')) return PLAIN_TERMS.dqn;
  if (upper.includes('RULE')) return PLAIN_TERMS.ruleBased;
  return mode;
}

/** Convert m/s to km/h (number). */
export function msToKmh(ms: number): number {
  if (typeof ms !== 'number' || isNaN(ms)) return 0;
  return Math.round(ms * 3.6 * 10) / 10;
}

/** Format speed in km/h with unit. */
export function formatSpeedKmh(ms: number): string {
  const kmh = msToKmh(ms);
  return `${Math.round(kmh)} km/h`;
}

/** Format duration in seconds into human-friendly minutes or seconds. */
export function secondsToMinutes(seconds: number): string {
  if (typeof seconds !== 'number' || isNaN(seconds) || seconds < 0) return '0 min';
  if (seconds < 60) return `${Math.round(seconds)} sec`;
  const mins = seconds / 60;
  return `${mins >= 10 ? Math.round(mins) : mins.toFixed(1)} min`;
}

/** Format a raw duration always in minutes (for wait times, averages). */
export function formatMinutesOnly(seconds: number): string {
  if (typeof seconds !== 'number' || isNaN(seconds) || seconds <= 0) return '0 min';
  const mins = seconds / 60;
  return `${mins.toFixed(1)} min`;
}

/** Format density into cars per km. */
export function formatDensity(density: number): string {
  if (typeof density !== 'number' || isNaN(density)) return '0 cars/km';
  return `${density.toFixed(1)} cars/km`;
}

/** Format road fullness percentage. */
export function formatRoadFullness(occupancyPercent: number): string {
  if (typeof occupancyPercent !== 'number' || isNaN(occupancyPercent)) return '0%';
  return `${occupancyPercent.toFixed(0)}% full`;
}
