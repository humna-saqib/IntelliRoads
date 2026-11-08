import { useEffect, useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import { useChartTheme } from '../../theme/chartTheme';
import Card from '../ui/Card';
import ChartTooltip from '../ui/ChartTooltip';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';
import { Info } from 'lucide-react';

interface SpeedHistoryPoint {
  simTime: number;
  timeLabel: string;
  speed: number;
}

interface SpeedDistributionProps {
  timeRangeMinutes?: number;
}

export default function SpeedDistribution({ timeRangeMinutes = 5 }: SpeedDistributionProps = {}) {
  const { kpis, kpiHistory } = useTraffic();
  const c = useChartTheme();
  const [history, setHistory] = useState<SpeedHistoryPoint[]>([]);

  const maxPoints = timeRangeMinutes <= 5 ? 30 : timeRangeMinutes <= 15 ? 90 : 360;

  const currentSpeedKmh = Math.round(kpis?.average_speed ? kpis.average_speed * 3.6 : 0);
  let diffText = '';
  if (kpiHistory && kpiHistory.length > 1) {
    const nowTs = kpiHistory[kpiHistory.length - 1].timestamp;
    let pastPoint = kpiHistory[0];
    for (const pt of kpiHistory) {
      if (nowTs - pt.timestamp >= 300) {
        pastPoint = pt;
      }
    }
    const pastSpeedKmh = Math.round(pastPoint.averageSpeed * 3.6);
    const diff = currentSpeedKmh - pastSpeedKmh;
    if (diff > 0) {
      diffText = `, ${diff} km/h faster than 5 minutes ago`;
    } else if (diff < 0) {
      diffText = `, ${Math.abs(diff)} km/h slower than 5 minutes ago`;
    } else {
      diffText = ', steady over the last 5 minutes';
    }
  }
  const speedTakeaway = `Average speed is ${currentSpeedKmh} km/h${diffText}.`;

  useEffect(() => {
    if (!kpis) return;
    setHistory((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].simTime === kpis.simulation_time) return prev;
      const point: SpeedHistoryPoint = {
        simTime: kpis.simulation_time,
        timeLabel: `${Math.floor(kpis.simulation_time)} s`,
        speed: Math.round(kpis.average_speed * 3.6 * 10) / 10,
      };
      const updated = [...prev, point];
      return updated.length > maxPoints ? updated.slice(updated.length - maxPoints) : updated;
    });
  }, [kpis, maxPoints]);

  const maxWindowSec = timeRangeMinutes * 60;
  const displayHistory = history.filter((pt) => {
    if (history.length === 0) return true;
    const latest = history[history.length - 1].simTime;
    return latest - pt.simTime <= maxWindowSec;
  });

  return (
    <Card title="How fast are vehicles moving?" subtitle="Rolling mean speed of vehicles across the network">
      <div className="h-[240px] w-full">
        {displayHistory.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[13px] text-faint">Waiting for simulation data…</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={displayHistory} margin={{ top: 10, right: 12, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={c.grid} vertical={false} />
              <XAxis dataKey="timeLabel" tick={{ fill: c.axis, fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis tick={{ fill: c.axis, fontSize: 11 }} tickLine={false} axisLine={false} domain={[0, 'auto']} />
              <Tooltip content={<ChartTooltip unit="km/h" />} cursor={{ stroke: c.grid }} />
              <ReferenceLine
                y={7.2}
                stroke={c.bad}
                strokeDasharray="3 4"
                strokeOpacity={0.7}
                label={{ value: 'Traffic is crawling below this speed (7.2 km/h)', fill: c.axis, fontSize: 11, position: 'insideTopRight' }}
              />
              <Line type="monotone" dataKey="speed" name="Average speed" stroke={c.series[0]} strokeWidth={1.75} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-line bg-subtle/50 px-3 py-2 text-xs text-muted">
        <Info size={13} className="text-brand shrink-0" />
        <span>{speedTakeaway}</span>
      </div>
    </Card>
  );
}
