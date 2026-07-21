import React, { useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import Card from '../ui/Card';
import Badge from '../ui/Badge';
import { Percent, HelpCircle } from 'lucide-react';
import clsx from 'clsx';

const JUNCTION_LANE_MAP: Record<string, string[]> = {
  junctionA: ['lane_A_west_in', 'lane_A_north_in', 'lane_AB_west', 'lane_AD_north'],
  junctionB: ['lane_AB_east', 'lane_B_north_in', 'lane_B_east_in', 'lane_BC_north'],
  junctionC: ['lane_CD_east', 'lane_BC_south', 'lane_C_east_in', 'lane_C_south_in'],
  junctionD: ['lane_D_west_in', 'lane_AD_south', 'lane_CD_west', 'lane_D_south_in'],
};

const JUNCTION_NAMES: Record<string, string> = {
  junctionA: 'Northwest Square',
  junctionB: 'Northeast Plaza',
  junctionC: 'Southeast Gateway',
  junctionD: 'Southwest Crossing',
};

const APPROACH_LABELS: Record<string, string> = {
  // Junction A approaches
  lane_A_west_in: 'West Approach (Grand Ave)',
  lane_A_north_in: 'North Approach (5th St)',
  lane_AB_west: 'East Approach (5th St Corridor)',
  lane_AD_north: 'South Approach (Grand Ave Corridor)',
  
  // Junction B approaches
  lane_AB_east: 'West Approach (5th St Corridor)',
  lane_B_north_in: 'North Approach (5th St)',
  lane_B_east_in: 'East Approach (Broadway)',
  lane_BC_north: 'South Approach (Broadway Corridor)',
  
  // Junction C approaches
  lane_CD_east: 'West Approach (1st St Corridor)',
  lane_BC_south: 'North Approach (Broadway Corridor)',
  lane_C_east_in: 'East Approach (Broadway)',
  lane_C_south_in: 'South Approach (1st St)',
  
  // Junction D approaches
  lane_D_west_in: 'West Approach (Grand Ave)',
  lane_AD_south: 'North Approach (Grand Ave Corridor)',
  lane_CD_west: 'East Approach (1st St Corridor)',
  lane_D_south_in: 'South Approach (1st St)',
};

export default function OccupancyChart() {
  const { occupancy } = useTraffic();
  const [selectedJunction, setSelectedJunction] = useState<string>('all');

  const rawLanes = occupancy?.lanes ?? [];

  // Helper to calculate average occupancy for a list of lane IDs
  const getAverageForLanes = (laneIds: string[]) => {
    const matched = rawLanes.filter((l) => laneIds.includes(l.lane_id));
    if (matched.length === 0) return 0;
    return matched.reduce((s, l) => s + l.occupancy_percent, 0) / matched.length;
  };

  // Compile data based on selection
  let displayData: { id: string; name: string; occupancy_percent: number; occupancy_level: string }[] = [];
  let average = 0;

  if (selectedJunction === 'all') {
    // Show the 4 junctions and calculate their average of averages
    displayData = Object.entries(JUNCTION_NAMES).map(([jId, name]) => {
      const avgOcc = getAverageForLanes(JUNCTION_LANE_MAP[jId]);
      return {
        id: jId,
        name: name,
        occupancy_percent: avgOcc,
        occupancy_level: avgOcc < 30 ? 'LOW' : avgOcc < 50 ? 'MEDIUM' : 'HIGH',
      };
    });
    average = displayData.reduce((sum, item) => sum + item.occupancy_percent, 0) / 4;
  } else {
    // Show the 4 approach lanes of the selected junction
    const targetLanes = JUNCTION_LANE_MAP[selectedJunction] ?? [];
    displayData = rawLanes
      .filter((l) => targetLanes.includes(l.lane_id))
      .map((l) => ({
        id: l.lane_id,
        name: APPROACH_LABELS[l.lane_id] ?? l.lane_id,
        occupancy_percent: l.occupancy_percent,
        occupancy_level: l.occupancy_level,
      }));
    average = getAverageForLanes(targetLanes);
  }

  const getOccupancyColor = (percent: number) => {
    if (percent >= 50) return {
      bar: 'bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.4)]',
      text: 'text-red-400',
      badge: 'danger' as const,
      label: 'Severe'
    };
    if (percent >= 30) return {
      bar: 'bg-yellow-500 shadow-[0_0_12px_rgba(234,179,8,0.4)]',
      text: 'text-yellow-400',
      badge: 'warning' as const,
      label: 'Moderate'
    };
    return {
      bar: 'bg-green-500 shadow-[0_0_12px_rgba(34,197,94,0.4)]',
      text: 'text-green-400',
      badge: 'success' as const,
      label: 'Clear'
    };
  };

  const avgStatus = getOccupancyColor(average);

  const selector = (
    <select
      value={selectedJunction}
      onChange={(e) => setSelectedJunction(e.target.value)}
      className="bg-slate-950/80 border border-white/10 text-slate-300 text-[11px] rounded-lg px-2.5 py-1 focus:outline-none focus:border-purple-500 transition-colors cursor-pointer"
    >
      <option value="all">All Intersections</option>
      {Object.entries(JUNCTION_NAMES).map(([id, name]) => (
        <option key={id} value={id}>{name}</option>
      ))}
    </select>
  );

  return (
    <Card
      title="Lane Occupancy"
      subtitle={selectedJunction === 'all' ? "Space utilization across junctions" : `Approaches at ${JUNCTION_NAMES[selectedJunction]}`}
      icon={<Percent size={16} />}
      gradient
      action={selector}
    >
      <div className="space-y-4">
        {/* Intersection definition explanation */}
        <div className="flex items-start gap-2.5 p-3 rounded-xl bg-purple-500/5 border border-purple-500/10 text-[11px] text-slate-400 leading-relaxed">
          <HelpCircle size={14} className="text-purple-400 shrink-0 mt-0.5" />
          <p>
            An <strong className="text-white font-semibold">Intersection (Junction)</strong> is a crossing point where multiple road legs meet. In this traffic network, we monitor four key intersections. When you select a specific intersection, you can see the vehicle occupancy rates of all four of its approach lanes (North, South, East, and West).
          </p>
        </div>

        <div className="flex flex-col md:flex-row gap-6 items-center">
          {/* Left column: Large average display */}
          <div className="flex flex-col items-center justify-center p-4 bg-white/3 border border-white/5 rounded-2xl w-full md:w-1/3 min-h-[160px] text-center">
            <span className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1">
              {selectedJunction === 'all' ? 'Network Average' : 'Junction Average'}
            </span>
            <div className="relative flex items-baseline justify-center">
              <span className={clsx("text-5xl font-mono font-bold tracking-tight", avgStatus.text)}>
                {average.toFixed(1)}
              </span>
              <span className="text-xl font-semibold text-slate-400 ml-0.5">%</span>
            </div>
            <div className="mt-3">
              <Badge label={avgStatus.label} variant={avgStatus.badge} />
            </div>
          </div>

          {/* Right column: Progress bars */}
          <div className="flex-1 w-full space-y-4">
            {displayData.length === 0 ? (
              <div className="text-center py-8 text-slate-500 text-sm">
                No occupancy data available
              </div>
            ) : (
              displayData.map((item) => {
                const status = getOccupancyColor(item.occupancy_percent);
                return (
                  <div key={item.id} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-200">{item.name}</span>
                      <div className="flex items-center gap-2">
                        <span className={clsx("font-mono font-bold", status.text)}>
                          {item.occupancy_percent.toFixed(1)}%
                        </span>
                        <span className="scale-75 origin-right">
                          <Badge label={item.occupancy_level} variant={status.badge} size="sm" />
                        </span>
                      </div>
                    </div>

                    {/* Progress track */}
                    <div className="h-3 w-full bg-slate-950/80 rounded-full border border-white/5 overflow-hidden">
                      {/* Animated glowing bar */}
                      <div
                        className={clsx("h-full rounded-full transition-all duration-700 ease-out", status.bar)}
                        style={{ width: `${Math.min(100, Math.max(2, item.occupancy_percent))}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Threshold Indicators Legend */}
      <div className="flex items-center justify-center gap-6 mt-4 pt-3 border-t border-white/5 text-[10px] text-slate-500">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-success-500" />
          CLEAR (&lt;30%)
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-warning-500" />
          MODERATE (30–50%)
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-danger-500" />
          SEVERE (&gt;=50%)
        </span>
      </div>
    </Card>
  );
}
