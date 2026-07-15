import React from 'react';
import SpeedDistribution from '../components/widgets/SpeedDistribution';
import DensityChart from '../components/widgets/DensityChart';
import VehicleClassChart from '../components/widgets/VehicleClassChart';
import VehicleTable from '../components/widgets/VehicleTable';

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      {/* Top: Speed timeline distribution */}
      <SpeedDistribution />

      {/* Middle: Lane density distribution */}
      <DensityChart />

      {/* Bottom: Side-by-side vehicle breakdown and active list */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div>
          <VehicleClassChart />
        </div>
        <div className="lg:col-span-2">
          <VehicleTable />
        </div>
      </div>
    </div>
  );
}
