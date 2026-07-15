import { useTraffic } from '../../context/TrafficContext';
import type { VehicleData, VehicleType } from '../../types/traffic';
import Badge from '../ui/Badge';
import Card from '../ui/Card';
import { Table } from 'lucide-react';
import clsx from 'clsx';

const TYPE_EMOJI: Record<VehicleType, string> = {
  car:        '🚗',
  motorcycle: '🏍️',
  bus:        '🚌',
  truck:      '🚛',
  unknown:    '🚘',
};

function speedBadge(speed: number) {
  if (speed < 2)  return { label: 'Waiting', variant: 'danger'  as const };
  if (speed < 8)  return { label: 'Slow',    variant: 'warning' as const };
  return              { label: 'Moving',   variant: 'success' as const };
}

function speedColor(speed: number): string {
  if (speed < 2)  return 'text-danger-400';
  if (speed < 8)  return 'text-warning-400';
  return 'text-success-400';
}

export default function VehicleTable() {
  const { vehicles } = useTraffic();
  const rows = vehicles.slice(0, 15);

  return (
    <Card
      title="Live Vehicle Feed"
      subtitle={`Showing ${rows.length} of ${vehicles.length} tracked vehicles`}
      icon={<Table size={16} />}
      gradient
    >
      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/8">
              {['ID', 'Type', 'Speed', 'Lane', 'Road', 'Status'].map((h) => (
                <th
                  key={h}
                  className="px-3 py-2 text-left text-[10px] text-slate-500 uppercase tracking-widest font-semibold"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-10 text-slate-600 text-sm">
                  No vehicle data available
                </td>
              </tr>
            ) : (
              rows.map((v: VehicleData, i: number) => {
                const { label, variant } = speedBadge(v.speed);
                return (
                  <tr
                    key={v.vehicle_id}
                    className={clsx(
                      'border-b border-white/4 transition-colors hover:bg-white/3 animate-fade-in',
                      i % 2 === 0 ? 'bg-white/1' : '',
                    )}
                    style={{ animationDelay: `${i * 30}ms` }}
                  >
                    <td className="px-3 py-2.5">
                      <span className="font-mono text-xs text-slate-400">{v.vehicle_id.slice(0, 8)}…</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="text-base mr-1.5">{TYPE_EMOJI[v.vehicle_type]}</span>
                      <span className="text-xs text-slate-300 capitalize">{v.vehicle_type}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={clsx('font-mono font-semibold text-sm', speedColor(v.speed))}>
                        {v.speed.toFixed(1)}
                      </span>
                      <span className="text-[10px] text-slate-600 ml-1">m/s</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="text-xs text-slate-300 font-mono">{v.lane_id}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="text-xs text-slate-400">{v.road_id}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge label={label} variant={variant} size="sm" />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
