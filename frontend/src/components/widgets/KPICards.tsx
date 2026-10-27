import { useTraffic } from '../../context/TrafficContext';
import type { KPIData } from '../../types/traffic';
import clsx from 'clsx';

interface Metric {
  key: keyof KPIData;
  label: string;
  format: (v: number) => string;
  detail: (k: KPIData) => string;
  alert?: boolean;
}

const METRICS: Metric[] = [
  {
    key: 'total_vehicles',
    label: 'Vehicles',
    format: (v) => v.toLocaleString(),
    detail: (k) => `${k.congestion_percentage.toFixed(0)}% of lanes congested`,
  },
  {
    key: 'active_intersections',
    label: 'Active junctions',
    format: (v) => v.toString(),
    detail: () => 'reporting data',
  },
  {
    key: 'average_wait_time',
    label: 'Average wait',
    format: (v) => `${v.toFixed(1)} s`,
    detail: (k) => `mean speed ${k.average_speed.toFixed(1)} m/s`,
  },
  {
    key: 'active_alerts',
    label: 'Active alerts',
    format: (v) => v.toString(),
    detail: (k) => (k.active_alerts > 0 ? 'congestion detected' : 'all clear'),
    alert: true,
  },
];

/** The four headline numbers as one divided strip rather than four separate tiles. */
export default function KPICards() {
  const { kpis } = useTraffic();

  return (
    <section className="grid grid-cols-2 overflow-hidden rounded-lg border border-line bg-surface lg:grid-cols-4" aria-label="Key figures">
      {METRICS.map(({ key, label, format, detail, alert }, i) => {
        const value = kpis ? (kpis[key] as number) : 0;
        const raised = alert && value > 0;
        return (
          <div
            key={key}
            className={clsx(
              'px-4 py-3.5',
              i % 2 === 1 && 'border-l border-line',
              i >= 2 && 'border-t border-line lg:border-t-0',
              i === 2 && 'lg:border-l',
            )}
          >
            <p className="text-xs text-faint">{label}</p>
            <p className={clsx('mt-1 text-2xl font-medium tabular-nums tracking-tight', raised ? 'text-bad' : 'text-ink')}>
              {kpis ? format(value) : '–'}
            </p>
            <p className="mt-0.5 text-xs text-faint">{kpis ? detail(kpis) : ' '}</p>
          </div>
        );
      })}
    </section>
  );
}
