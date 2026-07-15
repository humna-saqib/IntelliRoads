import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts';
import { useTraffic } from '../../context/TrafficContext';
import type { LaneDensity } from '../../types/traffic';
import Card from '../ui/Card';
import { Activity } from 'lucide-react';

interface TooltipPayload {
  payload?: LaneDensity & { fill: string };
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length || !payload[0].payload) return null;
  const d = payload[0].payload as unknown as LaneDensity & { fill: string };

  const levelColor =
    d.level === 'HIGH'   ? 'text-danger-400'  :
    d.level === 'MEDIUM' ? 'text-warning-400' :
    'text-success-400';

  return (
    <div className="glass-card rounded-xl p-3 border border-white/10 shadow-xl text-xs min-w-[140px]">
      <p className="font-semibold text-white mb-1.5">{d.lane_id}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-slate-400">Density</span>
          <span className="text-white font-mono">{d.density?.toFixed(2)} veh/km</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-slate-400">Vehicles</span>
          <span className="text-white font-mono">{d.vehicle_count}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-slate-400">Level</span>
          <span className={`font-semibold ${levelColor}`}>{d.level}</span>
        </div>
      </div>
    </div>
  );
}

function getBarColor(density: number): string {
  if (density > 40) return '#ef4444'; // danger
  if (density > 20) return '#f59e0b'; // warning
  return '#22c55e';                   // success
}

export default function DensityChart() {
  const { density } = useTraffic();
  const data = density?.lanes ?? [];

  return (
    <Card
      title="Lane Traffic Density"
      subtitle="Vehicles per kilometre by lane"
      icon={<Activity size={16} />}
      gradient
    >
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="barGreenGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22c55e" stopOpacity={0.9} />
                <stop offset="100%" stopColor="#15803d" stopOpacity={0.7} />
              </linearGradient>
              <linearGradient id="barAmberGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.9} />
                <stop offset="100%" stopColor="#b45309" stopOpacity={0.7} />
              </linearGradient>
              <linearGradient id="barRedGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ef4444" stopOpacity={0.9} />
                <stop offset="100%" stopColor="#991b1b" stopOpacity={0.7} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="lane_id"
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              label={{ value: 'veh/km', angle: -90, position: 'insideLeft', fill: '#475569', fontSize: 10 }}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
            <ReferenceLine y={20} stroke="#f59e0b" strokeDasharray="4 4" strokeOpacity={0.6}
              label={{ value: 'MED', position: 'right', fill: '#f59e0b', fontSize: 9 }} />
            <ReferenceLine y={40} stroke="#ef4444" strokeDasharray="4 4" strokeOpacity={0.6}
              label={{ value: 'HIGH', position: 'right', fill: '#ef4444', fontSize: 9 }} />
            <Bar dataKey="density" radius={[4, 4, 0, 0]} isAnimationActive animationDuration={800}>
              {data.map((entry, idx) => (
                <Cell
                  key={`cell-${idx}`}
                  fill={
                    entry.density > 40
                      ? 'url(#barRedGrad)'
                      : entry.density > 20
                      ? 'url(#barAmberGrad)'
                      : 'url(#barGreenGrad)'
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 mt-2 text-[10px] text-slate-500">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-success-500" />LOW (&lt;20)</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-warning-500" />MEDIUM (20–40)</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-danger-500" />HIGH (&gt;40)</span>
      </div>
    </Card>
  );
}
