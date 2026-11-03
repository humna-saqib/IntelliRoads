import { Car, GitFork, Timer, BellRing, type LucideIcon } from 'lucide-react';
import clsx from 'clsx';
import { useTraffic } from '../../context/TrafficContext';
import type { KPIData } from '../../types/traffic';

interface Metric {
  key: keyof KPIData;
  label: string;
  icon: LucideIcon;
  format: (v: number) => string;
  detail: (k: KPIData) => string;
  alert?: boolean;
}

const METRICS: Metric[] = [
  {
    key: 'total_vehicles',
    label: 'Vehicles on the road',
    icon: Car,
    format: (v) => v.toLocaleString(),
    detail: (k) => `${k.congestion_percentage.toFixed(0)}% of lanes congested`,
  },
  {
    key: 'active_intersections',
    label: 'Active junctions',
    icon: GitFork,
    format: (v) => v.toString(),
    detail: () => 'all reporting data',
  },
  {
    key: 'average_wait_time',
    label: 'Average wait',
    icon: Timer,
    format: (v) => `${v.toFixed(1)}s`,
    detail: (k) => `average speed ${k.average_speed.toFixed(1)} m/s`,
  },
  {
    key: 'active_alerts',
    label: 'Active alerts',
    icon: BellRing,
    format: (v) => v.toString(),
    detail: (k) => (k.active_alerts > 0 ? 'congestion detected' : 'all clear'),
    alert: true,
  },
];

/** The four headline numbers, each in its own tile with an icon chip. */
export default function KPICards() {
  const { kpis } = useTraffic();

  return (
    <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Key figures">
      {METRICS.map(({ key, label, icon: Icon, format, detail, alert }) => {
        const value = kpis ? (kpis[key] as number) : 0;
        const raised = alert && value > 0;
        return (
          <div key={key} className="rounded-xl border border-line bg-surface p-4 shadow-card">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted">{label}</p>
              <span
                className={clsx(
                  'flex h-7 w-7 items-center justify-center rounded-lg',
                  raised ? 'bg-bad/10 text-bad' : 'bg-brand/10 text-brand',
                )}
              >
                <Icon size={15} strokeWidth={1.9} />
              </span>
            </div>
            <p className={clsx('mt-3 text-[28px] font-semibold leading-8 tabular-nums tracking-tight', raised ? 'text-bad' : 'text-ink')}>
              {kpis ? format(value) : '–'}
            </p>
            <p className="mt-1 text-xs text-faint">{kpis ? detail(kpis) : ' '}</p>
          </div>
        );
      })}
    </section>
  );
}
