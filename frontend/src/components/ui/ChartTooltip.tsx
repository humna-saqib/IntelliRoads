interface Entry {
  name?: string | number;
  value?: string | number;
  color?: string;
  dataKey?: string | number;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: Entry[];
  label?: string | number;
  /** text appended to each value, e.g. "s" or "veh/km" */
  unit?: string;
}

/** Recharts tooltip that follows the theme through Tailwind tokens. */
export default function ChartTooltip({ active, payload, label, unit = '' }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-[140px] rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      {label !== undefined && <p className="mb-1.5 font-medium text-ink">{label}</p>}
      <ul className="space-y-1">
        {payload.map((p, i) => (
          <li key={`${p.dataKey ?? p.name}-${i}`} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-muted">
              {p.color && <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />}
              {p.name}
            </span>
            <span className="font-mono tabular-nums text-ink">
              {typeof p.value === 'number' ? Number(p.value.toFixed(2)) : p.value}
              {unit && <span className="ml-0.5 text-faint">{unit}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
