import { useTraffic } from '../context/TrafficContext';
import SpeedDistribution from '../components/widgets/SpeedDistribution';
import DensityChart from '../components/widgets/DensityChart';
import OccupancyChart from '../components/widgets/OccupancyChart';
import VehicleClassChart from '../components/widgets/VehicleClassChart';
import VehicleTable from '../components/widgets/VehicleTable';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';

export default function AnalyticsPage() {
  const { isLoading, isBackendOffline, kpis, retryConnection } = useTraffic();

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
      <SpeedDistribution />

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
