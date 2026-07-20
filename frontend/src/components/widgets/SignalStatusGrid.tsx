import { useEffect, useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import type { IntersectionData, SignalPhase } from '../../types/traffic';
import Badge from '../ui/Badge';
import Card from '../ui/Card';
import { TrafficCone } from 'lucide-react';
import clsx from 'clsx';

interface SignalLightProps {
  phase: SignalPhase;
}

function SignalLight({ phase }: SignalLightProps) {
  return (
    <div className="flex flex-col items-center gap-1.5 bg-black/60 rounded-xl px-2 py-3 border border-white/10">
      {(['RED', 'YELLOW', 'GREEN'] as SignalPhase[]).map((p) => {
        const isActive = phase === p;
        const colorMap: Record<SignalPhase, string> = {
          RED:    'bg-red-500',
          YELLOW: 'bg-yellow-400',
          GREEN:  'bg-green-500',
        };
        const glowMap: Record<SignalPhase, string> = {
          RED:    'shadow-[0_0_16px_6px_rgba(239,68,68,0.7)]',
          YELLOW: 'shadow-[0_0_16px_6px_rgba(250,204,21,0.7)]',
          GREEN:  'shadow-[0_0_16px_6px_rgba(34,197,94,0.7)]',
        };
        return (
          <div
            key={p}
            className={clsx(
              'w-6 h-6 rounded-full transition-all duration-500',
              isActive ? [colorMap[p], glowMap[p]] : 'bg-slate-700/50',
            )}
          />
        );
      })}
    </div>
  );
}

function Countdown({ seconds }: { seconds: number }) {
  const [remaining, setRemaining] = useState(seconds);

  useEffect(() => {
    setRemaining(seconds);
    const id = setInterval(() => {
      setRemaining((r) => Math.max(0, r - 1));
    }, 1000);
    return () => clearInterval(id);
  }, [seconds]);

  return (
    <div className="text-center">
      <span className="text-2xl font-mono font-bold text-white">{remaining}</span>
      <p className="text-[10px] text-slate-500">seconds</p>
    </div>
  );
}

export default function SignalStatusGrid() {
  const { intersections, signals } = useTraffic();

  const displayed = intersections.slice(0, 4);

  const getSignal = (id: string) =>
    signals?.signals.find((s) => s.junction_id === id);

  const densityVariant = (level: string) =>
    level === 'HIGH'   ? 'danger'  :
    level === 'MEDIUM' ? 'warning' :
    'success';

  const phaseLabel = (phase: SignalPhase) =>
    phase === 'GREEN' ? 'success' :
    phase === 'RED'   ? 'danger'  :
    'warning';

  return (
    <Card
      title="Signal Control"
      subtitle="Real-time traffic light status"
      icon={<TrafficCone size={16} />}
      gradient
    >
      <div className="grid grid-cols-2 gap-3">
        {displayed.length === 0 ? (
          <div className="col-span-2 text-center py-8 text-slate-500 text-sm">
            No intersections found
          </div>
        ) : (
          displayed.map((intersection: IntersectionData) => {
            const sig = getSignal(intersection.id);
            return (
              <div
                key={intersection.id}
                className={clsx(
                  'relative flex gap-3 p-3 rounded-xl border transition-all duration-300',
                  intersection.congestion_status === 'CONGESTED'
                    ? 'border-danger-500/40 bg-danger-500/5 animate-pulse-slow'
                    : 'border-white/8 bg-white/3 hover:bg-white/5',
                )}
              >
                {/* Traffic light visual */}
                <SignalLight phase={intersection.signal} />

                {/* Details */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-white truncate">{intersection.name}</p>
                  <p className="text-[10px] text-slate-500 mb-1.5">Junction {intersection.id}</p>

                  <div className="flex flex-wrap gap-1 mb-2">
                    <Badge label={intersection.signal} variant={phaseLabel(intersection.signal)} size="sm" />
                    <Badge
                      label={intersection.congestion_status}
                      variant={intersection.congestion_status === 'CONGESTED' ? 'danger' : 'success'}
                      size="sm"
                    />
                  </div>

                  {sig && (
                    <div className="flex items-center justify-between">
                      <div>
                        <Badge label={sig.density_level} variant={densityVariant(sig.density_level)} size="sm" />
                      </div>
                      <Countdown seconds={sig.duration_seconds} />
                    </div>
                  )}

                  <div className="mt-1.5 flex gap-3 text-[10px] text-slate-500">
                    <span>🚗 {intersection.vehicle_count}</span>
                    <span>📊 {intersection.density.toFixed(1)}/km</span>
                  </div>

                  {sig?.reason && (
                    <p className="text-[9px] text-slate-600 mt-1 truncate" title={sig.reason}>
                      {sig.reason}
                    </p>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}
