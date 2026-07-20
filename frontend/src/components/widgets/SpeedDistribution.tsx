import React, { useEffect, useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import Card from '../ui/Card';
import { Activity } from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';

interface SpeedHistoryPoint {
  simTime: number;
  timeLabel: string;
  speed: number;
}

export default function SpeedDistribution() {
  const { kpis } = useTraffic();
  const [history, setHistory] = useState<SpeedHistoryPoint[]>([]);

  useEffect(() => {
    if (!kpis) return;

    setHistory((prev) => {
      // Avoid duplicate points for the same simulation second
      if (prev.length > 0 && prev[prev.length - 1].simTime === kpis.simulation_time) {
        return prev;
      }

      const label = `${Math.floor(kpis.simulation_time)}s`;
      const newPoint: SpeedHistoryPoint = {
        simTime: kpis.simulation_time,
        timeLabel: label,
        speed: kpis.average_speed,
      };

      const updated = [...prev, newPoint];
      // Keep only last 30 readings
      if (updated.length > 30) {
        return updated.slice(updated.length - 30);
      }
      return updated;
    });
  }, [kpis]);

  return (
    <Card
      title="Vehicle Speed Timeline"
      subtitle="Rolling average speed of active vehicles"
      icon={<Activity className="h-5 w-5 text-emerald-500" />}
    >
      <div className="h-[250px] w-full mt-4">
        {history.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            Waiting for simulation data...
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="speedGlow" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.15} />
              <XAxis
                dataKey="timeLabel"
                stroke="#64748b"
                fontSize={10}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#64748b"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                domain={[0, 'auto']}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  color: '#f8fafc',
                  fontSize: '11px',
                }}
                labelClassName="font-bold"
              />
              {/* Reference line at 2 m/s for congestion indicator */}
              <ReferenceLine
                y={2}
                stroke="#ef4444"
                strokeDasharray="3 3"
                label={{
                  value: 'Congestion Threshold (2 m/s)',
                  fill: '#ef4444',
                  fontSize: 8,
                  position: 'top',
                }}
              />
              <Area
                type="monotone"
                dataKey="speed"
                name="Avg Speed (m/s)"
                stroke="#10b981"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#speedGlow)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
