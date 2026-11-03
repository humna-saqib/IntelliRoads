import { useEffect, useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import { useChartTheme } from '../../theme/chartTheme';
import Card from '../ui/Card';
import ChartTooltip from '../ui/ChartTooltip';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';

interface SpeedHistoryPoint {
  simTime: number;
  timeLabel: string;
  speed: number;
}

export default function SpeedDistribution() {
  const { kpis } = useTraffic();
  const c = useChartTheme();
  const [history, setHistory] = useState<SpeedHistoryPoint[]>([]);

  useEffect(() => {
    if (!kpis) return;
    setHistory((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].simTime === kpis.simulation_time) return prev;
      const point: SpeedHistoryPoint = {
        simTime: kpis.simulation_time,
        timeLabel: `${Math.floor(kpis.simulation_time)} s`,
        speed: kpis.average_speed,
      };
      const updated = [...prev, point];
      return updated.length > 30 ? updated.slice(updated.length - 30) : updated; // last 30 readings
    });
  }, [kpis]);

  return (
    <Card title="Average speed" subtitle="Rolling mean speed of vehicles in the network">
      <div className="h-[240px] w-full">
        {history.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[13px] text-faint">Waiting for simulation data…</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 10, right: 12, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={c.grid} vertical={false} />
              <XAxis dataKey="timeLabel" tick={{ fill: c.axis, fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis tick={{ fill: c.axis, fontSize: 11 }} tickLine={false} axisLine={false} domain={[0, 'auto']} />
              <Tooltip content={<ChartTooltip unit="m/s" />} cursor={{ stroke: c.grid }} />
              <ReferenceLine
                y={2}
                stroke={c.bad}
                strokeDasharray="3 4"
                strokeOpacity={0.7}
                label={{ value: 'Congestion threshold 2 m/s', fill: c.axis, fontSize: 11, position: 'insideTopRight' }}
              />
              <Line type="monotone" dataKey="speed" name="Average speed" stroke={c.series[0]} strokeWidth={1.75} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
