import { useTraffic } from '../../context/TrafficContext';
import type { VehicleData } from '../../types/traffic';
import Badge from '../ui/Badge';
import Card from '../ui/Card';
import clsx from 'clsx';

function speedState(speedKmh: number) {
  if (speedKmh < 7.2) return { label: 'Crawling', variant: 'danger' as const, tone: 'text-bad' };
  if (speedKmh < 30) return { label: 'Slow', variant: 'warning' as const, tone: 'text-warn' };
  return { label: 'Moving', variant: 'success' as const, tone: 'text-ok' };
}

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export default function VehicleTable() {
  const { vehicles } = useTraffic();
  const rows = vehicles.slice(0, 15);

  return (
    <Card title="Live vehicles" subtitle={`Showing ${rows.length} of ${vehicles.length} tracked vehicles`} padded={false}>
      <div className="overflow-x-auto">
        <table className="tbl">
          <thead>
            <tr>
              {['Vehicle', 'Type', 'Speed', 'Lane', 'Road', 'State'].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-10 text-center text-faint">No vehicle data available</td>
              </tr>
            ) : (
              rows.map((v: VehicleData) => {
                const speedKmh = v.speed * 3.6;
                const state = speedState(speedKmh);
                return (
                  <tr key={v.vehicle_id}>
                    <td className="font-mono text-xs text-muted">{v.vehicle_id.slice(0, 10)}</td>
                    <td>{sentence(v.vehicle_type)}</td>
                    <td className={clsx('font-mono tabular-nums', state.tone)}>
                      {speedKmh.toFixed(1)}
                      <span className="ml-1 text-2xs text-faint">km/h</span>
                    </td>
                    <td className="font-mono text-xs text-muted">{v.lane_id}</td>
                    <td className="text-muted">{v.road_id}</td>
                    <td><Badge label={state.label} variant={state.variant} size="sm" /></td>
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
