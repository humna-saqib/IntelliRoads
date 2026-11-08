import { useEffect, useState } from 'react';
import { useTraffic } from '../context/TrafficContext';
import IntersectionMap from '../components/widgets/IntersectionMap';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import { getJunctionName } from '../constants/plainWords';
import clsx from 'clsx';

const signalTone: Record<string, string> = {
  GREEN: 'bg-sig-green',
  YELLOW: 'bg-sig-yellow',
  RED: 'bg-sig-red',
};

export default function MapPage() {
  const { intersections, isLoading, isBackendOffline, retryConnection } = useTraffic();
  const [selectedJunctionId, setSelectedJunctionId] = useState<string | null>(null);

  useEffect(() => {
    document.title = 'Traffic Map · IntelliRoads';
  }, []);

  if (isBackendOffline && intersections.length === 0) {
    return (
      <div className="py-12">
        <ErrorState
          title="Traffic map unavailable"
          message="We can't connect to the traffic server right now to display the junction map."
          onRetry={retryConnection}
        />
      </div>
    );
  }

  if (isLoading && intersections.length === 0) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <LoadingSpinner size="lg" label="Loading traffic network…" />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <div className="xl:col-span-2">
        <IntersectionMap
          selectedJunctionId={selectedJunctionId}
          onSelectJunction={setSelectedJunctionId}
        />
      </div>

      <div className="space-y-4">
        <Card title="Junctions" subtitle="Click any junction on the map or list to inspect" padded={false}>
          <ul className="divide-y divide-line">
            {intersections.map((intersection) => (
              <li
                key={intersection.id}
                onClick={() => setSelectedJunctionId(intersection.id)}
                className={clsx(
                  'cursor-pointer px-4 py-3 transition-colors hover:bg-subtle',
                  selectedJunctionId === intersection.id && 'bg-brand/5 border-l-2 border-brand',
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[13px] font-medium">{getJunctionName(intersection.id)}</p>
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
                    <dt className="text-faint">How crowded</dt>
                    <dd className="mt-0.5 font-mono tabular-nums text-ink">
                      {Number(intersection.density).toFixed(1)}
                      <span className="ml-0.5 text-2xs text-faint">cars/km</span>
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
              <span className="font-medium text-ink">Standard timing</span> sets the green light duration based on how crowded the road is:
              light traffic (under 20 cars per km) gives 20 seconds, moderate traffic (20 to 40 cars per km) gives 35 seconds, and heavy traffic (over 40 cars per km) gives 55 seconds.
            </p>
            <p>
              <span className="font-medium text-ink">Smart AI</span> continuously monitors live vehicle queues and automatically extends or changes green lights every 5 seconds to clear bottlenecks.
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}
