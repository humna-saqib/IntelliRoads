import { Car, AlertTriangle, Crosshair, Timer } from 'lucide-react';
import { useTraffic } from '../../context/TrafficContext';
import Card from '../ui/Card';
import clsx from 'clsx';

interface KPICard {
  key:        keyof import('../../types/traffic').KPIData;
  label:      string;
  icon:       React.ReactNode;
  color:      string;
  bgColor:    string;
  format:     (v: number) => string;
  subtitle?:  string;
}

const CARDS: KPICard[] = [
  {
    key:     'total_vehicles',
    label:   'Total Vehicles',
    icon:    <Car size={20} />,
    color:   'text-accent-400',
    bgColor: 'from-accent-600/20 to-accent-500/5 border-accent-500/20',
    format:  (v) => v.toLocaleString(),
  },
  {
    key:     'active_intersections',
    label:   'Active Junctions',
    icon:    <Crosshair size={20} />,
    color:   'text-primary-400',
    bgColor: 'from-primary-600/20 to-primary-500/5 border-primary-500/20',
    format:  (v) => v.toString(),
  },
  {
    key:     'average_wait_time',
    label:   'Avg Wait Time',
    icon:    <Timer size={20} />,
    color:   'text-success-400',
    bgColor: 'from-success-600/20 to-success-500/5 border-success-500/20',
    format:  (v) => `${v.toFixed(1)}s`,
  },
  {
    key:     'active_alerts',
    label:   'Active Alerts',
    icon:    <AlertTriangle size={20} />,
    color:   'text-danger-400',
    bgColor: 'from-danger-600/20 to-danger-500/5 border-danger-500/20',
    format:  (v) => v.toString(),
  },
];

function AnimatedNumber({ value, format }: { value: number; format: (v: number) => string }) {
  // Renders the live value directly (with a CSS transition for polish)
  // rather than driving a requestAnimationFrame count-up loop: rAF is
  // throttled/suspended by the browser whenever the tab isn't visible or
  // focused, which would otherwise freeze this KPI on a stale number for
  // as long as the dashboard tab stays in the background — unacceptable
  // for a live monitoring display.
  return <span className="tabular-nums transition-opacity duration-300">{format(value)}</span>;
}

export default function KPICards() {
  const { kpis } = useTraffic();

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {CARDS.map(({ key, label, icon, color, bgColor, format }) => {
        const value = kpis ? (kpis[key] as number) : 0;
        return (
          <div
            key={key}
            className={clsx(
              'relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5',
              'transition-all duration-300 hover:scale-[1.02] hover:shadow-card-hover',
              bgColor,
            )}
          >
            {/* Background decorative circle */}
            <div className={clsx('absolute -right-4 -top-4 w-20 h-20 rounded-full opacity-10 blur-xl', color.replace('text-', 'bg-'))} />

            <div className="flex items-start justify-between mb-3">
              <div className={clsx('flex h-9 w-9 items-center justify-center rounded-xl', color, 'bg-white/5')}>
                {icon}
              </div>
              {/* Trend dot */}
              <div className="w-2 h-2 rounded-full bg-current animate-pulse" style={{ color: color.replace('text-', '') }} />
            </div>

            <div className={clsx('text-3xl font-bold tracking-tight', color)}>
              <AnimatedNumber value={value} format={format} />
            </div>
            <p className="text-xs text-slate-400 mt-1 font-medium">{label}</p>

            {/* Extra metrics */}
            {key === 'average_wait_time' && kpis && (
              <p className="text-[10px] text-slate-600 mt-1">
                Speed: {kpis.average_speed.toFixed(1)} m/s avg
              </p>
            )}
            {key === 'total_vehicles' && kpis && (
              <p className="text-[10px] text-slate-600 mt-1">
                Congestion: {kpis.congestion_percentage.toFixed(0)}%
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
