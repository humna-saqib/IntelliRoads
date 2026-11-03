import { useState } from 'react';
import { Bike, Bus, Car, Loader2, Minus, Plus, Send, CheckCircle2, type LucideIcon } from 'lucide-react';
import clsx from 'clsx';
import Card from '../ui/Card';
import { injectVehicles, type InjectVehicleType } from '../../services/api';

const MIN = 1;
const MAX = 300;

const PRESETS: { label: string; count: number }[] = [
  { label: 'Light', count: 10 },
  { label: 'Moderate', count: 40 },
  { label: 'Heavy', count: 100 },
  { label: 'Rush hour', count: 200 },
];

const TYPES: { value: InjectVehicleType; label: string; icon: LucideIcon }[] = [
  { value: 'passenger', label: 'Cars', icon: Car },
  { value: 'motorcycle', label: 'Bikes', icon: Bike },
  { value: 'bus', label: 'Buses', icon: Bus },
];

const ROUTES: { value: string; label: string }[] = [
  { value: 'all', label: 'All roads, spread evenly' },
  { value: 'route_top_east', label: 'Top street, heading east' },
  { value: 'route_top_west', label: 'Top street, heading west' },
  { value: 'route_bottom_east', label: 'Bottom street, heading east' },
  { value: 'route_bottom_west', label: 'Bottom street, heading west' },
  { value: 'route_left_south', label: 'Left street, heading south' },
  { value: 'route_left_north', label: 'Left street, heading north' },
  { value: 'route_right_south', label: 'Right street, heading south' },
  { value: 'route_right_north', label: 'Right street, heading north' },
];

const clamp = (n: number) => Math.min(MAX, Math.max(MIN, Math.round(n)));

export default function VehicleInjectionPanel() {
  const [count, setCount] = useState(40);
  const [type, setType] = useState<InjectVehicleType>('passenger');
  const [route, setRoute] = useState('all');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const valid = Number.isInteger(count) && count >= MIN && count <= MAX;
  const typeLabel = TYPES.find((t) => t.value === type)?.label.toLowerCase() ?? 'vehicles';

  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await injectVehicles(count, type, route);
      setMessage(`${res.added} ${typeLabel} are entering the simulation now. Watch the signals respond.`);
    } catch {
      setError('Could not add vehicles. Check that the simulation is connected.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Add traffic" subtitle="Choose how many vehicles to send in, then watch how the controller reacts">
      <div className="grid gap-6 lg:grid-cols-2">
        {/* left: how many */}
        <div>
          <p className="field-label">How many vehicles?</p>
          <div className="flex items-center gap-2">
            <button type="button" className="btn btn-icon h-10 w-10 rounded-lg" onClick={() => setCount(clamp((count || 0) - 10))} aria-label="Remove 10">
              <Minus size={16} />
            </button>
            <input
              type="number"
              min={MIN}
              max={MAX}
              inputMode="numeric"
              value={Number.isNaN(count) ? '' : count}
              onChange={(e) => setCount(e.target.valueAsNumber)}
              aria-label="Number of vehicles"
              className="input h-10 text-center font-mono text-lg font-semibold tabular-nums"
            />
            <button type="button" className="btn btn-icon h-10 w-10 rounded-lg" onClick={() => setCount(clamp((count || 0) + 10))} aria-label="Add 10">
              <Plus size={16} />
            </button>
          </div>
          <p className={clsx('mt-1.5 text-xs', valid ? 'text-faint' : 'text-bad')}>
            {valid ? `Any number from ${MIN} to ${MAX}` : `Enter a whole number from ${MIN} to ${MAX}`}
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => setCount(p.count)}
                className={clsx(
                  'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                  count === p.count ? 'border-brand bg-brand/10 text-brand' : 'border-line text-muted hover:bg-subtle hover:text-ink',
                )}
              >
                {p.label} <span className="font-mono text-faint">{p.count}</span>
              </button>
            ))}
          </div>
        </div>

        {/* right: what and where */}
        <div className="space-y-4">
          <div>
            <p className="field-label">Vehicle type</p>
            <div role="radiogroup" aria-label="Vehicle type" className="grid grid-cols-3 gap-1 rounded-lg bg-subtle p-1">
              {TYPES.map(({ value, label, icon: Icon }) => {
                const selected = type === value;
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setType(value)}
                    className={clsx(
                      'flex h-8 items-center justify-center gap-1.5 rounded-md text-[13px] font-medium transition-all',
                      selected ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink',
                    )}
                  >
                    <Icon size={14} strokeWidth={1.9} />
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <label className="field-label" htmlFor="inject-route">Where do they enter?</label>
            <select id="inject-route" value={route} onChange={(e) => setRoute(e.target.value)} className="input">
              {ROUTES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-h-[1.25rem] text-[13px]">
          {message && (
            <p className="flex items-center gap-1.5 text-ok">
              <CheckCircle2 size={15} /> {message}
            </p>
          )}
          {error && <p className="text-bad">{error}</p>}
          {!message && !error && <p className="text-muted">Vehicles join the normal traffic within a few seconds.</p>}
        </div>
        <button type="button" onClick={submit} disabled={!valid || busy} className="btn btn-brand">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={15} />}
          Send {valid ? count : ''} {typeLabel}
        </button>
      </div>
    </Card>
  );
}
