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

/**
 * Map an action name string from the DQN controller (e.g. "EXTEND_GREEN",
 * "SWITCH_PHASE") to a plain-language description shown to the user.
 */
function mapDqnActionName(raw: string): string {
  const action = raw.toUpperCase().replace(/\s+/g, '_');
  if (action.includes('EXTEND_GREEN')) return 'kept the green light longer to clear the queue';
  if (action.includes('SWITCH') || action.includes('CHANGE')) return 'switched to the next phase to serve waiting traffic';
  if (action.includes('SKIP')) return 'skipped a short phase to prioritise heavy demand';
  if (action.includes('SHORTEN') || action.includes('REDUCE')) return 'shortened green time because traffic was light';
  if (action.includes('HOLD')) return 'held the current phase a moment longer';
  return 'made a timing adjustment based on live queue lengths';
}

/**
 * Convert a raw backend `sig.reason` string into a plain-language sentence
 * suitable for non-technical users.  Never shows raw codes.
 *
 * Covers all known backend reason formats:
 *  - Rule-based:   "{HIGH|MEDIUM|LOW} density on {direction} approach -> {N}s green phase"
 *  - Legacy DQN:   "DQN Action: EXTEND_GREEN (Reward: 0.85, Q-State: [...])"
 *  - FYP DQN (starting): "obs-v2 DQN: waiting for the first decision"
 *  - FYP DQN (action):   "obs-v2 DQN action: EXTEND_GREEN at t=150s (Q: 0.92)"
 *  - Emergency priority: "Emergency priority override for {type} '{id}'"
 */
export function formatSignalReason(
  reason: string | null | undefined,
  controllerMode?: string | null,
): string {
  if (!reason || !reason.trim()) {
    // No reason provided — give a safe generic based on mode
    if (controllerMode && controllerMode.toUpperCase().includes('DQN')) {
      return 'Smart AI is monitoring traffic and choosing the best signal timing.';
    }
    return 'Standard timing is running its fixed schedule.';
  }

  const r = reason.trim();

  // ── Emergency vehicle priority ──────────────────────────────────────────────
  if (/emergency priority override/i.test(r)) {
    // "Emergency priority override for ambulance 'ev_001'"
    const typeMatch = r.match(/override for ([^\s']+)/i);
    const vehicleType = typeMatch ? typeMatch[1].toLowerCase() : 'emergency vehicle';
    return `Held green for an approaching ${vehicleType}.`;
  }

  // ── Rule-based density controller ───────────────────────────────────────────
  // "HIGH density on West approach -> 40s green phase"
  const densityMatch = r.match(/^(HIGH|MEDIUM|LOW)\s+density\s+on\s+(\S+)\s+approach/i);
  if (densityMatch) {
    const level = densityMatch[1].toUpperCase();
    const direction = densityMatch[2].toLowerCase();
    if (level === 'HIGH') {
      return `Kept green longer — cars are still queuing on the ${direction} side.`;
    }
    if (level === 'MEDIUM') {
      return `Extended green to handle moderate traffic from the ${direction}.`;
    }
    return `Short green phase — traffic is light on the ${direction} side.`;
  }

  // ── FYP DQN: starting up ────────────────────────────────────────────────────
  if (/obs-v2\s+DQN:\s*waiting/i.test(r)) {
    return 'Smart AI is starting up and observing traffic patterns.';
  }

  // ── FYP DQN: action ─────────────────────────────────────────────────────────
  // "obs-v2 DQN action: EXTEND_GREEN at t=150s (Q: 0.92)"
  const fypMatch = r.match(/obs-v2\s+DQN\s+action:\s*([A-Za-z0-9_]+)/i);
  if (fypMatch) {
    return `Smart AI ${mapDqnActionName(fypMatch[1])}.`;
  }

  // ── Legacy DQN: action ───────────────────────────────────────────────────────
  // "DQN Action: EXTEND_GREEN (Reward: 0.85, Q-State: [...])"
  const legacyMatch = r.match(/DQN\s+Action:\s*([A-Za-z0-9_]+)/i);
  if (legacyMatch) {
    return `Smart AI ${mapDqnActionName(legacyMatch[1])}.`;
  }

  // ── Fallback ─────────────────────────────────────────────────────────────────
  return 'Signal timing is running normally.';
}
