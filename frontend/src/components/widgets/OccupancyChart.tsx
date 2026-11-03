import { useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import Card from '../ui/Card';
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
  lane_A_west_in: 'West approach (Grand Ave)',
  lane_A_north_in: 'North approach (5th St)',
  lane_AB_west: 'East approach (5th St corridor)',
  lane_AD_north: 'South approach (Grand Ave corridor)',

  lane_AB_east: 'West approach (5th St corridor)',
  lane_B_north_in: 'North approach (5th St)',
  lane_B_east_in: 'East approach (Broadway)',
  lane_BC_north: 'South approach (Broadway corridor)',

  lane_CD_east: 'West approach (1st St corridor)',
  lane_BC_south: 'North approach (Broadway corridor)',
  lane_C_east_in: 'East approach (Broadway)',
  lane_C_south_in: 'South approach (1st St)',

  lane_D_west_in: 'West approach (Grand Ave)',
  lane_AD_south: 'North approach (Grand Ave corridor)',
  lane_CD_west: 'East approach (1st St corridor)',
  lane_D_south_in: 'South approach (1st St)',
};

/** Share of lane length occupied by vehicles: clear below 30 %, moderate to 50 %, severe above. */
const tone = (percent: number) =>
  percent >= 50 ? { bar: 'bg-bad', text: 'text-bad', label: 'Severe' } :
  percent >= 30 ? { bar: 'bg-warn', text: 'text-warn', label: 'Moderate' } :
  { bar: 'bg-ok', text: 'text-ok', label: 'Clear' };

export default function OccupancyChart() {
  const { occupancy } = useTraffic();
  const [selectedJunction, setSelectedJunction] = useState<string>('all');

  const rawLanes = occupancy?.lanes ?? [];

  const averageFor = (laneIds: string[]) => {
    const matched = rawLanes.filter((l) => laneIds.includes(l.lane_id));
    return matched.length === 0 ? 0 : matched.reduce((s, l) => s + l.occupancy_percent, 0) / matched.length;
  };

  let rows: { id: string; name: string; percent: number }[];
  let average: number;

  if (selectedJunction === 'all') {
    rows = Object.entries(JUNCTION_NAMES).map(([id, name]) => ({ id, name, percent: averageFor(JUNCTION_LANE_MAP[id]) }));
    average = rows.reduce((sum, r) => sum + r.percent, 0) / rows.length;
  } else {
    const targetLanes = JUNCTION_LANE_MAP[selectedJunction] ?? [];
    rows = rawLanes
      .filter((l) => targetLanes.includes(l.lane_id))
      .map((l) => ({ id: l.lane_id, name: APPROACH_LABELS[l.lane_id] ?? l.lane_id, percent: l.occupancy_percent }));
    average = averageFor(targetLanes);
  }

  const avgTone = tone(average);

  return (
    <Card
      title="Lane occupancy"
      subtitle={selectedJunction === 'all' ? 'Share of road space in use, by junction' : `Approaches at ${JUNCTION_NAMES[selectedJunction]}`}
      action={
        <select
          value={selectedJunction}
          onChange={(e) => setSelectedJunction(e.target.value)}
          className="input h-7 w-auto pr-6 text-xs"
          aria-label="Junction"
        >
          <option value="all">All junctions</option>
          {Object.entries(JUNCTION_NAMES).map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>
      }
    >
      <div className="mb-4 flex items-baseline gap-2">
        <span className={clsx('text-3xl font-medium tabular-nums tracking-tight', avgTone.text)}>{average.toFixed(1)}%</span>
        <span className="text-xs text-faint">{selectedJunction === 'all' ? 'network average' : 'junction average'} · {avgTone.label.toLowerCase()}</span>
      </div>

      {rows.length === 0 ? (
        <p className="py-6 text-center text-[13px] text-faint">No occupancy data available</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => {
            const t = tone(row.percent);
            return (
              <li key={row.id}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3 text-xs">
                  <span className="truncate text-ink">{row.name}</span>
                  <span className="font-mono tabular-nums text-muted">{row.percent.toFixed(1)}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-subtle">
                  <div className={clsx('h-full rounded-full transition-[width] duration-500', t.bar)} style={{ width: `${Math.min(100, Math.max(1.5, row.percent))}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line pt-3 text-xs text-faint">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-ok" />Clear, under 30%</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-warn" />Moderate, 30 to 50%</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-bad" />Severe, 50% and over</span>
      </div>
    </Card>
  );
}
