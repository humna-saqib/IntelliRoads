import { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts';
import { useTraffic } from '../../context/TrafficContext';
import { useChartTheme } from '../../theme/chartTheme';
import type { LaneDensity } from '../../types/traffic';
import { fetchAllThresholds, type JunctionThresholds } from '../../services/api';
import Card from '../ui/Card';
import Badge from '../ui/Badge';
import { Info } from 'lucide-react';

function DensityTooltip({ active, payload }: { active?: boolean; payload?: { payload?: LaneDensity }[] }) {
  const d = payload?.[0]?.payload;
  if (!active || !d) return null;
  const tone = d.level === 'HIGH' ? 'text-bad' : d.level === 'MEDIUM' ? 'text-warn' : 'text-ok';
  return (
    <div className="min-w-[150px] rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <p className="mb-1.5 font-medium text-ink">{d.lane_id}</p>
      <dl className="space-y-1">
        <div className="flex justify-between gap-4">
          <dt className="text-muted">Density</dt>
          <dd className="font-mono tabular-nums text-ink">{d.density?.toFixed(1)} cars/km</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-muted">Vehicles</dt>
          <dd className="font-mono tabular-nums text-ink">{d.vehicle_count}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-muted">Level</dt>
          <dd className={tone}>{d.level.charAt(0) + d.level.slice(1).toLowerCase()}</dd>
        </div>
      </dl>
    </div>
  );
}

export default function DensityChart() {
  const { density } = useTraffic();
  const c = useChartTheme();
  const [thresholds, setThresholds] = useState<Record<string, JunctionThresholds> | null>(null);
  const [thresholdFetchFailed, setThresholdFetchFailed] = useState<boolean>(false);

  useEffect(() => {
    fetchAllThresholds()
      .then((res) => {
        setThresholds(res);
        setThresholdFetchFailed(false);
      })
      .catch((err) => {
        console.warn('Failed to fetch thresholds from /api/settings/thresholds, using safe fallbacks:', err);
        setThresholdFetchFailed(true);
      });
  }, []);

  const fallbackLow = 20;
  const fallbackHigh = 40;
  const thresholdList = thresholds ? Object.values(thresholds) : [];
  const lowThreshold =
    thresholdList.length > 0
      ? Math.round(thresholdList.reduce((acc, t) => acc + (t.low_threshold ?? 20), 0) / thresholdList.length)
      : fallbackLow;
  const highThreshold =
    thresholdList.length > 0
      ? Math.round(thresholdList.reduce((acc, t) => acc + (t.congestion_threshold ?? 40), 0) / thresholdList.length)
      : fallbackHigh;

  const data = density?.lanes ?? [];
  const barColor = (value: number) => (value >= highThreshold ? c.bad : value >= lowThreshold ? c.warn : c.ok);

  let densityTakeaway = 'All monitored roads are flowing smoothly with light traffic.';
  if (data.length > 0) {
    const maxLane = data.reduce((max, l) => (l.density > max.density ? l : max), data[0]);
    const levelText = maxLane.density >= highThreshold ? 'heavy traffic' : maxLane.density >= lowThreshold ? 'moderate traffic' : 'light traffic';
    const laneName = maxLane.lane_id.replace(/^lane_/, '').replace(/_/g, ' ');
    densityTakeaway = `The most crowded road is ${laneName} with ${maxLane.density.toFixed(1)} cars per km (${levelText}).`;
  }

  return (
    <Card
      title="Which roads are most crowded?"
      subtitle="Cars per kilometre on each monitored approach"
      action={
        <div className="flex items-center gap-2">
          {thresholdFetchFailed && (
            <span className="inline-flex items-center rounded border border-warn/30 bg-warn/10 px-2 py-0.5 text-2xs font-medium text-warn">
              Using default limits
            </span>
          )}
          <Badge label="Live right now" variant="success" size="sm" />
        </div>
      }
    >
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid stroke={c.grid} vertical={false} />
            <XAxis dataKey="lane_id" tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip content={<DensityTooltip />} cursor={{ fill: c.cursor }} />
            <ReferenceLine
              y={lowThreshold}
              stroke={c.warn}
              strokeDasharray="3 4"
              strokeOpacity={0.7}
              label={{ value: `Moderate (${lowThreshold})`, fill: c.axis, fontSize: 10, position: 'insideTopLeft' }}
            />
            <ReferenceLine
              y={highThreshold}
              stroke={c.bad}
              strokeDasharray="3 4"
              strokeOpacity={0.7}
              label={{ value: `Congestion (${highThreshold})`, fill: c.axis, fontSize: 10, position: 'insideTopLeft' }}
            />
            <Bar dataKey="density" radius={[2, 2, 0, 0]} maxBarSize={36} isAnimationActive={false}>
              {data.map((entry, idx) => (
                <Cell key={`cell-${idx}`} fill={barColor(entry.density)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-faint">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-ok" />Light traffic, under {lowThreshold} cars/km</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-warn" />Moderate traffic, {lowThreshold} to {highThreshold} cars/km</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-bad" />Heavy traffic, over {highThreshold} cars/km</span>
        {thresholdFetchFailed && (
          <span className="text-2xs text-warn ml-auto font-medium">Using default limits</span>
        )}
      </div>

      <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-line bg-subtle/50 px-3 py-2 text-xs text-muted">
        <Info size={13} className="text-brand shrink-0" />
        <span>{densityTakeaway}</span>
      </div>
    </Card>
  );
}
