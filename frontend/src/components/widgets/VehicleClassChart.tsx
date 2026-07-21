import {
  PieChart, Pie, Cell, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';
import { useTraffic } from '../../context/TrafficContext';
import Card from '../ui/Card';
import { PieChart as PieIcon } from 'lucide-react';

const VEHICLE_COLORS = {
  car:        '#06b6d4',
  motorcycle: '#8b5cf6',
  bus:        '#f59e0b',
  emergency:  '#ef4444',
};

const VEHICLE_LABELS: Record<string, string> = {
  car:        '🚗 Car',
  motorcycle: '🏍️ Moto',
  bus:        '🚌 Bus',
  emergency:  '🚨 Emergency',
};

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number; payload: { pct: number } }> }) {
  if (!active || !payload?.length) return null;
  const { name, value, payload: inner } = payload[0];
  return (
    <div className="glass-card rounded-xl p-2.5 border border-white/10 shadow-xl text-xs">
      <p className="font-semibold text-white">{VEHICLE_LABELS[name] ?? name}</p>
      <p className="text-slate-300">{value} vehicles</p>
      <p className="text-slate-400">{inner.pct?.toFixed(1)}%</p>
    </div>
  );
}

function CenterLabel({ total }: { total: number }) {
  return (
    <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle">
      <tspan x="50%" dy="-8" fontSize="24" fontWeight="bold" fill="white">{total}</tspan>
      <tspan x="50%" dy="18" fontSize="11" fill="#64748b">vehicles</tspan>
    </text>
  );
}

export default function VehicleClassChart() {
  const { classification } = useTraffic();

  const entries = ['car', 'motorcycle', 'bus', 'emergency'] as const;
  const total   = entries.reduce((s, k) => s + (classification?.[k] ?? 0), 0);

  const data = entries.map((k) => ({
    name: k,
    value: classification?.[k] ?? 0,
    pct:  total > 0 ? ((classification?.[k] ?? 0) / total) * 100 : 0,
  })).filter((d) => d.value > 0);

  return (
    <Card
      title="Vehicle Classification"
      subtitle="Real-time type distribution"
      icon={<PieIcon size={16} />}
      gradient
    >
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <defs>
              {entries.map((k) => (
                <radialGradient key={k} id={`grad-${k}`} cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor={VEHICLE_COLORS[k]} stopOpacity={1} />
                  <stop offset="100%" stopColor={VEHICLE_COLORS[k]} stopOpacity={0.6} />
                </radialGradient>
              ))}
            </defs>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={90}
              paddingAngle={3}
              dataKey="value"
              nameKey="name"
              isAnimationActive
              animationDuration={900}
            >
              {data.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={`url(#grad-${entry.name})`}
                  stroke={VEHICLE_COLORS[entry.name as keyof typeof VEHICLE_COLORS]}
                  strokeWidth={1}
                />
              ))}
            </Pie>
            <text>
              <CenterLabel total={total} />
            </text>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Custom legend */}
      <div className="grid grid-cols-2 gap-2 mt-1">
        {entries.map((k) => {
          const count = classification?.[k] ?? 0;
          const pct   = total > 0 ? (count / total * 100).toFixed(1) : '0.0';
          return (
            <div key={k} className="flex items-center gap-2 text-xs">
              <div
                className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                style={{ background: VEHICLE_COLORS[k] }}
              />
              <span className="text-slate-400 capitalize">{k}</span>
              <span className="ml-auto text-white font-medium">{count}</span>
              <span className="text-slate-600">({pct}%)</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
