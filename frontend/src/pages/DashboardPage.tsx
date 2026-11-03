import KPICards from '../components/widgets/KPICards';
import SignalStatusGrid from '../components/widgets/SignalStatusGrid';
import CongestionAlerts from '../components/widgets/CongestionAlerts';
import DensityChart from '../components/widgets/DensityChart';
import OccupancyChart from '../components/widgets/OccupancyChart';
import VehicleClassChart from '../components/widgets/VehicleClassChart';
import VehicleTable from '../components/widgets/VehicleTable';
import EmergencyPriorityBanner from '../components/widgets/EmergencyPriorityBanner';
import ControlModePanel from '../components/widgets/ControlModePanel';
import VehicleInjectionPanel from '../components/widgets/VehicleInjectionPanel';

export default function DashboardPage() {
  return (
    <div>
      <EmergencyPriorityBanner />

      <div className="space-y-5">
        <KPICards />

        {/* the two things you can change: how signals are controlled, and how much traffic there is */}
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
          <div className="xl:col-span-2">
            <ControlModePanel />
          </div>
          <div className="xl:col-span-3">
            <VehicleInjectionPanel />
          </div>
        </div>

        {/* what is happening as a result */}
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <div className="space-y-5 xl:col-span-2">
            <SignalStatusGrid />
            <CongestionAlerts />
          </div>
          <VehicleClassChart />
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <DensityChart />
          <OccupancyChart />
        </div>

        <VehicleTable />
      </div>
    </div>
  );
}
