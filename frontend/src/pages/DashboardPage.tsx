import React from 'react';
import KPICards from '../components/widgets/KPICards';
import SignalStatusGrid from '../components/widgets/SignalStatusGrid';
import CongestionAlerts from '../components/widgets/CongestionAlerts';
import DensityChart from '../components/widgets/DensityChart';
import OccupancyChart from '../components/widgets/OccupancyChart';
import VehicleClassChart from '../components/widgets/VehicleClassChart';
import VehicleTable from '../components/widgets/VehicleTable';

export default function DashboardPage() {
  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Top row: KPI cards */}
      <KPICards />

      {/* Grid row 2: Signals and Alerts */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 sm:gap-6">
        <div className="xl:col-span-2">
          <SignalStatusGrid />
        </div>
        <div>
          <CongestionAlerts />
        </div>
      </div>

      {/* Grid row 3: Density and Occupancy Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <DensityChart />
        <OccupancyChart />
      </div>

      {/* Grid row 4: Class Distribution and Vehicle Table */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 sm:gap-6">
        <div className="xl:col-span-1">
          <VehicleClassChart />
        </div>
        <div className="xl:col-span-2">
          <VehicleTable />
        </div>
      </div>
    </div>
  );
}
