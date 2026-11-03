import SpeedDistribution from '../components/widgets/SpeedDistribution';
import DensityChart from '../components/widgets/DensityChart';
import OccupancyChart from '../components/widgets/OccupancyChart';
import VehicleClassChart from '../components/widgets/VehicleClassChart';
import VehicleTable from '../components/widgets/VehicleTable';

export default function AnalyticsPage() {
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
