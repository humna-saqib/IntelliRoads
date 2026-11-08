import { useEffect, useState } from 'react';
import { useTraffic } from '../context/TrafficContext';
import SpeedDistribution from '../components/widgets/SpeedDistribution';
import DensityChart from '../components/widgets/DensityChart';
import OccupancyChart from '../components/widgets/OccupancyChart';
import VehicleClassChart from '../components/widgets/VehicleClassChart';
import VehicleTable from '../components/widgets/VehicleTable';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import { Clock } from 'lucide-react';
import clsx from 'clsx';

const TIME_RANGES = [
  { value: 5, label: 'Last 5 minutes' },
  { value: 15, label: 'Last 15 minutes' },
  { value: 60, label: 'Last 60 minutes' },
] as const;

export default function AnalyticsPage() {
  const { isLoading, isBackendOffline, kpis, retryConnection } = useTraffic();
  const [timeRangeMinutes, setTimeRangeMinutes] = useState<number>(5);

  useEffect(() => {
    document.title = 'Analytics · IntelliRoads';
  }, []);

  if (isBackendOffline && !kpis) {
    return (
      <div className="py-12">
        <ErrorState
          title="Traffic analytics unavailable"
          message="We can't reach the traffic system right now to collect speed and volume statistics."
          onRetry={retryConnection}
        />
      </div>
    );
  }

  if (isLoading && !kpis) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <LoadingSpinner size="lg" label="Loading traffic data…" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between shadow-2xs">
        <div>
          <h2 className="text-sm font-semibold text-ink tracking-tight sm:text-[15px]">Traffic analytics & trends</h2>
          <p className="text-xs text-muted">Review speed trends across time windows; road crowdedness, fullness, and vehicle mix show live conditions</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted flex items-center gap-1 font-medium">
            <Clock size={13} className="text-faint" />
            Time range:
          </span>
          <div role="radiogroup" aria-label="Time range selector" className="flex items-center rounded-lg border border-line bg-subtle p-0.5">
            {TIME_RANGES.map((range) => {
              const active = timeRangeMinutes === range.value;
              return (
                <button
                  key={range.value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setTimeRangeMinutes(range.value)}
                  className={clsx(
                    'min-h-[36px] rounded-md px-3 text-xs font-medium transition-all',
                    active ? 'bg-surface text-brand shadow-xs' : 'text-muted hover:text-ink',
                  )}
                >
                  {range.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <SpeedDistribution timeRangeMinutes={timeRangeMinutes} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DensityChart />
        <OccupancyChart />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <VehicleClassChart />
        <div className="lg:col-span-2">
          <VehicleTable />
        </div>
      </div>
    </div>
  );
}
