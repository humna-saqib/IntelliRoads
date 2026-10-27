import { useTraffic } from '../../context/TrafficContext';
import { useChartTheme } from '../../theme/chartTheme';
import Card from '../ui/Card';

const CLASSES = [
  { key: 'car', label: 'Car' },
  { key: 'motorcycle', label: 'Motorcycle' },
  { key: 'bus', label: 'Bus' },
  { key: 'emergency', label: 'Emergency' },
] as const;

/** Vehicle mix as one proportional bar plus a plain list, instead of a donut. */
export default function VehicleClassChart() {
  const { classification } = useTraffic();
  const c = useChartTheme();

  const counts = CLASSES.map((cls, i) => ({ ...cls, count: classification?.[cls.key] ?? 0, color: c.series[i] }));
  const total = counts.reduce((sum, row) => sum + row.count, 0);

  return (
    <Card title="Vehicle mix" subtitle="Share of vehicles by type">
      <p className="text-3xl font-medium tabular-nums tracking-tight">
        {total.toLocaleString()}
        <span className="ml-2 text-xs font-normal text-faint">vehicles</span>
      </p>

      <div className="mt-4 flex h-2 w-full overflow-hidden rounded-full bg-subtle" role="img" aria-label="Vehicle type proportions">
        {total > 0 &&
          counts
            .filter((row) => row.count > 0)
            .map((row) => <span key={row.key} style={{ width: `${(row.count / total) * 100}%`, background: row.color }} />)}
      </div>

      <ul className="mt-4 space-y-2.5">
        {counts.map((row) => (
          <li key={row.key} className="flex items-center gap-2.5 text-[13px]">
            <span className="h-2 w-2 flex-shrink-0 rounded-sm" style={{ background: row.color }} />
            <span className="text-ink">{row.label}</span>
            <span className="ml-auto font-mono tabular-nums text-ink">{row.count}</span>
            <span className="w-12 text-right font-mono text-xs tabular-nums text-faint">{total > 0 ? ((row.count / total) * 100).toFixed(1) : '0.0'}%</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
