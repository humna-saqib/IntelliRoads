import { useTraffic } from '../../context/TrafficContext';
import { Siren } from 'lucide-react';

const JUNCTION_NAMES: Record<string, string> = {
  junctionA: 'Northwest Square',
  junctionB: 'Northeast Plaza',
  junctionC: 'Southeast Gateway',
  junctionD: 'Southwest Crossing',
};

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();

export default function EmergencyPriorityBanner() {
  const { emergency } = useTraffic();

  if (!emergency || !emergency.active_vehicles || emergency.active_vehicles.length === 0) {
    return null;
  }

  const vehicle = emergency.active_vehicles[0];
  const location = vehicle.junction_id ? JUNCTION_NAMES[vehicle.junction_id] || vehicle.junction_id : 'a monitored junction';
  const lane = vehicle.lane_id.replace('lane_', '').replace('_in', '');

  return (
    <div role="status" className="mb-4 flex items-start gap-3 rounded-lg border border-l-2 border-line border-l-bad bg-surface px-4 py-3">
      <Siren size={16} strokeWidth={1.75} className="mt-0.5 flex-shrink-0 text-bad" />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium">
          Priority override: {sentence(vehicle.vehicle_type)} {vehicle.vehicle_id} approaching {location}
        </p>
        <p className="mt-0.5 text-xs text-muted">Signals are holding a green corridor along {lane}.</p>
      </div>
      <span className="flex-shrink-0 font-mono text-xs tabular-nums text-muted">{(vehicle.speed * 3.6).toFixed(0)} km/h</span>
    </div>
  );
}
