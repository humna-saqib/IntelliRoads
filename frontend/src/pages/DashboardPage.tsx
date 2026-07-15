import React from 'react';
import KPICards from '../components/widgets/KPICards';
import SignalStatusGrid from '../components/widgets/SignalStatusGrid';
import CongestionAlerts from '../components/widgets/CongestionAlerts';
import DensityChart from '../components/widgets/DensityChart';
import VehicleClassChart from '../components/widgets/VehicleClassChart';
import VehicleTable from '../components/widgets/VehicleTable';

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Top row: KPI cards */}
      <KPICards />

      {/* Grid row 2: Signals and Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <SignalStatusGrid />
        </div>
        <div>
          <CongestionAlerts />
        </div>
      </div>

      {/* Grid row 3: Density and Vehicle Class Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DensityChart />
        <VehicleClassChart />
      </div>

      {/* Grid row 4: Live vehicle list */}
      <VehicleTable />
    </div>
  );
}
