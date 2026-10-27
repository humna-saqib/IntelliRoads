import { useEffect, useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import type { IntersectionData, SignalPhase } from '../../types/traffic';
import Badge from '../ui/Badge';
import Card from '../ui/Card';
import clsx from 'clsx';

const LAMPS: { phase: SignalPhase; on: string }[] = [
  { phase: 'RED', on: 'bg-sig-red' },
  { phase: 'YELLOW', on: 'bg-sig-yellow' },
  { phase: 'GREEN', on: 'bg-sig-green' },
];

/** Three flat lamps in a row; only the active one is coloured. */
function SignalLamps({ phase }: { phase: SignalPhase }) {
  return (
    <div className="flex items-center gap-1 rounded-full bg-subtle px-1.5 py-1.5" aria-label={`Signal ${phase.toLowerCase()}`}>
      {LAMPS.map((lamp) => (
        <span key={lamp.phase} className={clsx('h-2.5 w-2.5 rounded-full', phase === lamp.phase ? lamp.on : 'bg-strong/60')} />
      ))}
    </div>
  );
}

function Countdown({ seconds }: { seconds: number }) {
  const [remaining, setRemaining] = useState(seconds);

  useEffect(() => {
    setRemaining(seconds);
    const id = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(id);
  }, [seconds]);

  return (
    <span className="font-mono text-[15px] font-medium tabular-nums text-ink">
      {Math.round(remaining)}
      <span className="ml-0.5 text-xs font-normal text-faint">s</span>
    </span>
  );
}

const phaseVariant = (phase: SignalPhase) => (phase === 'GREEN' ? 'success' : phase === 'RED' ? 'danger' : 'warning');
const phaseLabel = (phase: SignalPhase) => phase.charAt(0) + phase.slice(1).toLowerCase();

export default function SignalStatusGrid() {
  const { intersections, signals } = useTraffic();
  const displayed = intersections.slice(0, 4);
  const getSignal = (id: string) => signals?.signals.find((s) => s.junction_id === id);

  return (
    <Card title="Signal control" subtitle="Current phase and time left at each junction" padded={false}>
      {displayed.length === 0 ? (
        <p className="px-4 py-10 text-center text-[13px] text-faint">No intersections found</p>
      ) : (
        <ul className="divide-y divide-line">
          {displayed.map((intersection: IntersectionData) => {
            const sig = getSignal(intersection.id);
            const congested = intersection.congestion_status === 'CONGESTED';
            return (
              <li key={intersection.id} className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 px-4 py-3 sm:grid-cols-[auto_1fr_auto]">
                <SignalLamps phase={intersection.signal} />

                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium">
                    {intersection.name}
                    <span className="ml-2 font-mono text-2xs font-normal text-faint">{intersection.id}</span>
                  </p>
                  <p className="mt-0.5 text-xs text-faint">
                    <span className="tabular-nums">{intersection.vehicle_count}</span> vehicles
                    <span className="mx-1.5 text-line-strong">·</span>
                    <span className="tabular-nums">{intersection.density.toFixed(1)}</span> veh/km
                  </p>
                  {sig?.reason && (
                    <p className="mt-0.5 truncate text-2xs text-faint" title={sig.reason}>
                      {sig.reason}
                    </p>
                  )}
                </div>

                <div className="col-span-2 flex flex-shrink-0 items-center justify-between gap-1 sm:col-span-1 sm:flex-col sm:items-end sm:justify-start">
                  <div className="flex items-center gap-2">
                    {congested && <Badge label="Congested" variant="danger" size="sm" />}
                    <Badge label={phaseLabel(intersection.signal)} variant={phaseVariant(intersection.signal)} size="sm" />
                  </div>
                  {sig && <Countdown seconds={sig.duration_seconds} />}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
