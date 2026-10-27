import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts';
import { useTraffic } from '../../context/TrafficContext';
import { useChartTheme } from '../../theme/chartTheme';
import type { LaneDensity } from '../../types/traffic';
import Card from '../ui/Card';

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
          <dd className="font-mono tabular-nums text-ink">{d.density?.toFixed(2)} veh/km</dd>
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
  const data = density?.lanes ?? [];
  const barColor = (value: number) => (value > 40 ? c.bad : value > 20 ? c.warn : c.ok);

  return (
    <Card title="Lane density" subtitle="Vehicles per kilometre, by lane">
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid stroke={c.grid} vertical={false} />
            <XAxis dataKey="lane_id" tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip content={<DensityTooltip />} cursor={{ fill: c.cursor }} />
            <ReferenceLine y={20} stroke={c.warn} strokeDasharray="3 4" strokeOpacity={0.7} />
            <ReferenceLine y={40} stroke={c.bad} strokeDasharray="3 4" strokeOpacity={0.7} />
            <Bar dataKey="density" radius={[2, 2, 0, 0]} maxBarSize={36} isAnimationActive={false}>
              {data.map((entry, idx) => (
                <Cell key={`cell-${idx}`} fill={barColor(entry.density)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-faint">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-ok" />Low, under 20</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-warn" />Medium, 20 to 40</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-bad" />High, over 40</span>
      </div>
    </Card>
  );
}
