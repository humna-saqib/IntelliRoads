import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import JunctionCard from '../components/widgets/JunctionCard';
import type { IntersectionData, SignalTiming } from '../types/traffic';

describe('JunctionCard component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const baseIntersection: IntersectionData = {
    id: 'junctionA',
    name: 'Northwest Square',
    signal: 'GREEN',
    congestion_status: 'CLEAR',
    vehicle_count: 5,
    density: 12.4,
  };

  const baseSignal: SignalTiming = {
    junction_id: 'junctionA',
    phase: 'GREEN',
    duration_seconds: 25,
    time_in_phase: 5,
    reason: 'HOLD_GREEN_AI_BUSY',
  };

  it('shows plain traffic level in words for light traffic', () => {
    render(<JunctionCard intersection={baseIntersection} signal={baseSignal} />);

    expect(screen.getByText('Light traffic')).toBeInTheDocument();
    expect(screen.getByText('Northwest Square')).toBeInTheDocument();
    expect(screen.getByText(/5 cars right now/i)).toBeInTheDocument();
  });

  it('shows moderate traffic level when density is between 20 and 39', () => {
    render(
      <JunctionCard
        intersection={{ ...baseIntersection, density: 25.5 }}
        signal={baseSignal}
      />
    );

    expect(screen.getByText('Moderate traffic')).toBeInTheDocument();
  });

  it('shows Traffic jam when status is CONGESTED', () => {
    render(
      <JunctionCard
        intersection={{ ...baseIntersection, congestion_status: 'CONGESTED', density: 48.0 }}
        signal={baseSignal}
      />
    );

    expect(screen.getByText('Traffic jam')).toBeInTheDocument();
  });

  it('shows light colour in words (Green, Yellow, Red)', () => {
    const { rerender } = render(
      <JunctionCard intersection={{ ...baseIntersection, signal: 'GREEN' }} signal={baseSignal} />
    );
    expect(screen.getByText(/Green for 25 more seconds/i)).toBeInTheDocument();

    rerender(
      <JunctionCard
        intersection={{ ...baseIntersection, signal: 'YELLOW' }}
        signal={{ ...baseSignal, phase: 'YELLOW', duration_seconds: 5 }}
      />
    );
    expect(screen.getByText(/Yellow for 5 more seconds/i)).toBeInTheDocument();

    rerender(
      <JunctionCard
        intersection={{ ...baseIntersection, signal: 'RED' }}
        signal={{ ...baseSignal, phase: 'RED', duration_seconds: 30 }}
      />
    );
    expect(screen.getByText(/Red for 30 more seconds/i)).toBeInTheDocument();
  });

  it('counts down the seconds remaining accurately', () => {
    render(
      <JunctionCard
        intersection={baseIntersection}
        signal={{ ...baseSignal, duration_seconds: 15 }}
      />
    );

    expect(screen.getByText(/Green for 15 more seconds/i)).toBeInTheDocument();
    expect(screen.getByText('15s')).toBeInTheDocument();

    // Advance timer by 5 seconds
    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(screen.getByText(/Green for 10 more seconds/i)).toBeInTheDocument();
    expect(screen.getByText('10s')).toBeInTheDocument();
  });
});
