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

  // Junction names (real names from /api/intersections)
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

export const JUNCTION_REAL_NAMES: Record<string, string> = {
  junctionA: 'Northwest Square',
  junctionB: 'Northeast Plaza',
  junctionC: 'Southeast Gateway',
  junctionD: 'Southwest Crossing',
};

/** Get the human-friendly name for a junction ID. */
export function getJunctionName(id: string): string {
  if (!id) return 'Unknown junction';
  if (JUNCTION_REAL_NAMES[id]) return JUNCTION_REAL_NAMES[id];
  // Check for embedded letters (e.g. junction_A, lane_A)
  if (/junction[_-]?A/i.test(id) || /_A_/i.test(id)) return JUNCTION_REAL_NAMES.junctionA;
  if (/junction[_-]?B/i.test(id) || /_B_/i.test(id)) return JUNCTION_REAL_NAMES.junctionB;
  if (/junction[_-]?C/i.test(id) || /_C_/i.test(id)) return JUNCTION_REAL_NAMES.junctionC;
  if (/junction[_-]?D/i.test(id) || /_D_/i.test(id)) return JUNCTION_REAL_NAMES.junctionD;
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
