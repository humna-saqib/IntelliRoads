import KPICards from '../components/widgets/KPICards';
import SignalStatusGrid from '../components/widgets/SignalStatusGrid';
import CongestionAlerts from '../components/widgets/CongestionAlerts';
import DensityChart from '../components/widgets/DensityChart';
import OccupancyChart from '../components/widgets/OccupancyChart';
import VehicleClassChart from '../components/widgets/VehicleClassChart';
import VehicleTable from '../components/widgets/VehicleTable';
import EmergencyPriorityBanner from '../components/widgets/EmergencyPriorityBanner';
import ControlModePanel from '../components/widgets/ControlModePanel';

export default function DashboardPage() {
  return (
    <div>
      <EmergencyPriorityBanner />

      <div className="space-y-4">
        <KPICards />

        {/* left column: what the signals are doing; right column: how they are controlled */}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="space-y-4 xl:col-span-2">
            <SignalStatusGrid />
            <CongestionAlerts />
          </div>
          <div className="space-y-4">
            <ControlModePanel />
            <VehicleClassChart />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <DensityChart />
          <OccupancyChart />
        </div>

        <VehicleTable />
      </div>
    </div>
  );
}
