import { useEffect, useRef, useState } from 'react';
import { Car, Bike, Bus, Truck, AlertTriangle, Activity, Crosshair } from 'lucide-react';
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
    key:     'average_speed',
    label:   'Avg Speed',
    icon:    <Activity size={20} />,
    color:   'text-success-400',
    bgColor: 'from-success-600/20 to-success-500/5 border-success-500/20',
    format:  (v) => `${v.toFixed(1)} m/s`,
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
  const [display, setDisplay] = useState(value);
  const prevRef = useRef(value);
  const animRef = useRef<ReturnType<typeof requestAnimationFrame> | null>(null);

  useEffect(() => {
    const start    = prevRef.current;
    const end      = value;
    const diff     = end - start;
    const duration = 600;
    const startTs  = performance.now();

    if (animRef.current) cancelAnimationFrame(animRef.current);

    const animate = (now: number) => {
      const progress = Math.min((now - startTs) / duration, 1);
      const eased    = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setDisplay(Math.round(start + diff * eased));
      if (progress < 1) {
        animRef.current = requestAnimationFrame(animate);
      } else {
        prevRef.current = end;
      }
    };
    animRef.current = requestAnimationFrame(animate);
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current); };
  }, [value]);

  return <span>{format(display)}</span>;
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
            {key === 'average_speed' && kpis && (
              <p className="text-[10px] text-slate-600 mt-1">
                Wait: {kpis.average_wait_time.toFixed(1)}s avg
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
