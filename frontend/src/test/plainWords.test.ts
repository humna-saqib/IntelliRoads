import { describe, it, expect } from 'vitest';
import {
  msToKmh,
  getJunctionName,
  formatSignalReason,
  formatSpeedKmh,
  getControllerModeName,
  formatRoadFullness,
} from '../constants/plainWords';

describe('plainWords helpers', () => {
  describe('msToKmh', () => {
    it('converts meters per second to kilometers per hour accurately', () => {
      // 10 m/s * 3.6 = 36 km/h
      expect(msToKmh(10)).toBe(36);
      // 0 m/s = 0 km/h
      expect(msToKmh(0)).toBe(0);
      // 13.89 m/s ~ 50 km/h
      expect(msToKmh(13.88889)).toBe(50);
      // 5 m/s = 18 km/h
      expect(msToKmh(5)).toBe(18);
    });

    it('returns 0 for invalid or NaN inputs', () => {
      expect(msToKmh(NaN)).toBe(0);
      expect(msToKmh(undefined as any)).toBe(0);
      expect(msToKmh('invalid' as any)).toBe(0);
    });

    it('formatSpeedKmh formats speed with km/h unit', () => {
      expect(formatSpeedKmh(10)).toBe('36 km/h');
      expect(formatSpeedKmh(0)).toBe('0 km/h');
    });
  });

  describe('getJunctionName fallback', () => {
    it('returns real junction names for known IDs', () => {
      expect(getJunctionName('junctionA')).toBe('Northwest Square');
      expect(getJunctionName('junctionB')).toBe('Northeast Plaza');
      expect(getJunctionName('junctionC')).toBe('Southeast Gateway');
      expect(getJunctionName('junctionD')).toBe('Southwest Crossing');
    });

    it('matches embedded junction IDs in lane or detector strings', () => {
      expect(getJunctionName('lane_A_west_in')).toBe('Northwest Square');
      expect(getJunctionName('detector_B_east')).toBe('Northeast Plaza');
      expect(getJunctionName('lane_C_south_in')).toBe('Southeast Gateway');
      expect(getJunctionName('junction_D')).toBe('Southwest Crossing');
    });

    it('returns fallback for empty, null, or undefined IDs', () => {
      expect(getJunctionName('')).toBe('Unknown junction');
      expect(getJunctionName(null as any)).toBe('Unknown junction');
      expect(getJunctionName(undefined as any)).toBe('Unknown junction');
    });

    it('returns the input ID cleanly if unknown and no pattern matches', () => {
      expect(getJunctionName('customJunction99')).toBe('customJunction99');
    });
  });

  describe('formatSignalReason', () => {
    it('never returns raw code for completely unknown input', () => {
      const unknownCodes = [
        'UNKNOWN_SIGNAL_CODE_9999',
        'ERR_CONTROLLER_FAIL_32',
        'SIG_TIMING_ACTION_RAW_XYZ',
        'FOO_BAR_BAZ_CODE',
      ];

      for (const code of unknownCodes) {
        const result = formatSignalReason(code);
        // Must never return the raw code
        expect(result).not.toBe(code);
        expect(result).not.toContain('UNKNOWN');
        expect(result).not.toContain('ERR_');
        // Returns safe plain-language sentence
        expect(result).toBe('Signal timing is running normally.');
      }
    });

    it('provides friendly defaults when reason is null, undefined, or empty', () => {
      expect(formatSignalReason(null, 'RULE_BASED')).toBe(
        'Standard timing is running its fixed schedule.'
      );
      expect(formatSignalReason('', 'DQN')).toBe(
        'Smart AI is monitoring traffic and choosing the best signal timing.'
      );
      expect(formatSignalReason(undefined, null)).toBe(
        'Standard timing is running its fixed schedule.'
      );
    });

    it('formats emergency priority override cleanly', () => {
      const reason = "Emergency priority override for ambulance 'ev_001'";
      const formatted = formatSignalReason(reason);
      expect(formatted).toBe('Held green for an approaching ambulance.');
    });

    it('formats rule-based density reasoning in plain language', () => {
      expect(
        formatSignalReason('HIGH density on West approach -> 40s green phase')
      ).toBe('Kept green longer — cars are still queuing on the west side.');

      expect(
        formatSignalReason('LOW density on North approach -> 15s green phase')
      ).toBe('Short green phase — traffic is light on the north side.');
    });

    it('formats DQN action reasoning in plain language without raw Q values', () => {
      const reason = 'obs-v2 DQN action: EXTEND_GREEN at t=150s (Q: 0.92)';
      const formatted = formatSignalReason(reason);
      expect(formatted).toBe(
        'Smart AI kept the green light longer to clear the queue.'
      );
      expect(formatted).not.toContain('obs-v2');
      expect(formatted).not.toContain('0.92');
    });
  });
});

