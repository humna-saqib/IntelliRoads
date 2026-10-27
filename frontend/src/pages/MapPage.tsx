import { useTraffic } from '../context/TrafficContext';
import IntersectionMap from '../components/widgets/IntersectionMap';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import clsx from 'clsx';

const signalTone: Record<string, string> = {
  GREEN: 'bg-sig-green',
  YELLOW: 'bg-sig-yellow',
  RED: 'bg-sig-red',
};

export default function MapPage() {
  const { intersections } = useTraffic();

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <div className="xl:col-span-2">
        <IntersectionMap />
      </div>

      <div className="space-y-4">
        <Card title="Junctions" subtitle="Status of each monitored junction" padded={false}>
          <ul className="divide-y divide-line">
            {intersections.map((intersection) => (
              <li key={intersection.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[13px] font-medium">{intersection.name}</p>
                  <Badge
                    label={intersection.congestion_status === 'CONGESTED' ? 'Congested' : 'Clear'}
                    variant={intersection.congestion_status === 'CONGESTED' ? 'danger' : 'success'}
                    size="sm"
                  />
                </div>
                <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <dt className="text-faint">Signal</dt>
                    <dd className="mt-0.5 flex items-center gap-1.5 text-ink">
                      <span className={clsx('h-2 w-2 rounded-full', signalTone[intersection.signal?.toUpperCase()] ?? 'bg-faint')} />
                      {intersection.signal.charAt(0) + intersection.signal.slice(1).toLowerCase()}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-faint">Vehicles</dt>
                    <dd className="mt-0.5 font-mono tabular-nums text-ink">{intersection.vehicle_count}</dd>
                  </div>
                  <div>
                    <dt className="text-faint">Density</dt>
                    <dd className="mt-0.5 font-mono tabular-nums text-ink">
                      {Number(intersection.density).toFixed(1)}
                      <span className="ml-0.5 text-2xs text-faint">veh/km</span>
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="How the signals are controlled">
          <div className="space-y-3 text-xs leading-relaxed text-muted">
            <p>
              <span className="font-medium text-ink">Rule-based mode</span> sets the green time from lane density:
              under 20 veh/km gives 20 s, 20 to 40 veh/km gives 35 s, and over 40 veh/km gives 55 s.
            </p>
            <p>
              <span className="font-medium text-ink">DQN mode</span> lets a trained agent keep, switch, extend or reduce the
              green every 5 seconds, always within a 10 to 60 second green and a fixed 5 second yellow.
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}
