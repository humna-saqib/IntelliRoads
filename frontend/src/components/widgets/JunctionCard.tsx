import { useEffect, useState } from 'react';
import type { IntersectionData, SignalTiming, SignalPhase } from '../../types/traffic';
import { getJunctionName } from '../../constants/plainWords';
import Card from '../ui/Card';
import Badge from '../ui/Badge';
import clsx from 'clsx';
import { Activity, Car, Sparkles, Clock } from 'lucide-react';

interface JunctionCardProps {
  intersection: IntersectionData;
  signal?: SignalTiming;
  controllerMode?: string | null;
}

/** Translate technical density level to plain language */
function getTrafficLevelInWords(status: string, density: number): { label: string; variant: 'success' | 'warning' | 'danger' | 'neutral' } {
  if (status === 'CONGESTED') {
    return { label: 'Traffic jam', variant: 'danger' };
  }
  if (density >= 40) {
    return { label: 'Heavy traffic', variant: 'danger' };
  }
  if (density >= 20) {
    return { label: 'Moderate traffic', variant: 'warning' };
  }
  return { label: 'Light traffic', variant: 'success' };
}

/** Format light color in words */
function getLightColorLabel(phase: SignalPhase): string {
  switch (phase) {
    case 'GREEN':
      return 'Green';
    case 'YELLOW':
      return 'Yellow';
    case 'RED':
      return 'Red';
    default:
      return 'Active';
  }
}

/** Format "What the AI just did" in non-technical terms from real backend signal data */
function formatAiAction(reason: string | undefined, controllerMode: string | null | undefined): string {
  if (!reason) {
    if (controllerMode === 'DQN') {
      return 'Smart AI is actively observing lane queues to select optimal phase.';
    }
    return 'Standard timing: running fixed threshold cycle.';
  }

  // Parse RL action reasons
  if (/obs-v2 DQN action:/i.test(reason)) {
    const actionPart = reason.replace(/obs-v2 DQN action:\s*/i, '').replace(/\(Q:.*?\)/i, '').trim();
    return `Smart AI chose: ${actionPart}`;
  }
  if (/DQN Action:/i.test(reason)) {
    const actionMatch = reason.match(/DQN Action:\s*([A-Za-z0-9_]+)/i);
    const actionName = actionMatch ? actionMatch[1].replace(/_/g, ' ').toLowerCase() : 'adjust phase';
    return `Smart AI switched phase to ${actionName} based on vehicle queues.`;
  }
  if (/priority/i.test(reason)) {
    return 'Held green light for approaching emergency vehicle corridor.';
  }
  if (/density on .* approach/i.test(reason)) {
    return `Standard timing adjusted green light duration based on approach queue.`;
  }

  return reason;
}

export default function JunctionCard({ intersection, signal, controllerMode }: JunctionCardProps) {
  const [secondsRemaining, setSecondsRemaining] = useState<number>(signal?.duration_seconds ?? 0);

  // Sync and tick countdown timer
  useEffect(() => {
    setSecondsRemaining(signal?.duration_seconds ?? 0);
    if (!signal?.duration_seconds) return;

    const timer = setInterval(() => {
      setSecondsRemaining((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    return () => clearInterval(timer);
  }, [signal?.duration_seconds, signal?.phase]);

  const displayName = getJunctionName(intersection.id);
  const trafficLevel = getTrafficLevelInWords(intersection.congestion_status, intersection.density);
  const lightColor = getLightColorLabel(intersection.signal);
  const aiExplanation = formatAiAction(signal?.reason, controllerMode);

  const phaseColorClasses =
    intersection.signal === 'GREEN'
      ? 'text-sig-green bg-sig-green/10 border-sig-green/20'
      : intersection.signal === 'YELLOW'
      ? 'text-sig-yellow bg-sig-yellow/10 border-sig-yellow/20'
      : 'text-sig-red bg-sig-red/10 border-sig-red/20';

  const lampDotColor =
    intersection.signal === 'GREEN'
      ? 'bg-sig-green shadow-[0_0_8px_rgba(34,197,94,0.6)]'
      : intersection.signal === 'YELLOW'
      ? 'bg-sig-yellow shadow-[0_0_8px_rgba(234,179,8,0.6)]'
      : 'bg-sig-red shadow-[0_0_8px_rgba(239,68,68,0.6)]';

  return (
    <Card className="flex flex-col justify-between transition-shadow hover:shadow-md">
      <div>
        {/* Header: Real Junction Name and Traffic Level */}
        <div className="flex items-start justify-between gap-2 border-b border-line pb-3">
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-ink sm:text-[15px]">
              {displayName}
            </h2>
            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
              <Car size={13} className="text-faint" />
              <span>{intersection.vehicle_count} cars right now</span>
            </p>
          </div>
          <Badge label={trafficLevel.label} variant={trafficLevel.variant} size="sm" />
        </div>

        {/* Signal state with live countdown in plain words */}
        <div className="mt-4 flex items-center justify-between rounded-lg border border-line bg-subtle p-3">
          <div className="flex items-center gap-2.5">
            <span className={clsx('h-3.5 w-3.5 rounded-full transition-colors', lampDotColor)} />
            <div>
              <p className="text-xs text-muted">Current light</p>
              <p className="text-sm font-medium text-ink">
                {lightColor} for {Math.round(secondsRemaining)} more seconds
              </p>
            </div>
          </div>
          <div
            className={clsx(
              'flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium tabular-nums',
              phaseColorClasses,
            )}
          >
            <Clock size={12} />
            <span>{Math.round(secondsRemaining)}s</span>
          </div>
        </div>

        {/* What the AI / Controller just did */}
        <div className="mt-3.5 rounded-lg border border-line bg-surface p-3">
          <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-faint">
            <Sparkles size={12} className="text-brand" />
            <span>What the system just did</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-ink">
            {aiExplanation}
          </p>
        </div>
      </div>

      {/* Footer approach status */}
      <div className="mt-4 flex items-center justify-between border-t border-line pt-2.5 text-2xs text-faint">
        <span className="flex items-center gap-1">
          <Activity size={12} />
          <span>Flow density: {intersection.density.toFixed(1)} cars/km</span>
        </span>
        <span className="capitalize">{intersection.congestion_status.toLowerCase()}</span>
      </div>
    </Card>
  );
}
