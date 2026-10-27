import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import clsx from 'clsx';
import Card from '../ui/Card';
import { fetchActiveModel, fetchControllerMode, setControllerMode, type ActiveModelInfo, type ControllerMode } from '../../services/api';

const POLL_INTERVAL_MS = 5000;

const MODES: { value: ControllerMode; label: string; description: string }[] = [
  { value: 'RULE_BASED', label: 'Rule-based', description: 'Green time follows fixed density thresholds.' },
  { value: 'DQN', label: 'DQN', description: 'A trained Double DQN agent chooses the signal action every 5 seconds.' },
];

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <dt className="text-faint">{label}</dt>
      <dd className="text-right font-mono tabular-nums text-muted">{children}</dd>
    </div>
  );
}

export default function ControlModePanel() {
  const [mode, setMode] = useState<ControllerMode | null>(null);
  const [model, setModel] = useState<ActiveModelInfo | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetchControllerMode();
      setMode(res.mode);
      setError(null);
    } catch {
      setError('Unable to reach the controller service.');
      return;
    }
    try {
      setModel(await fetchActiveModel());
    } catch {
      setModel(null); // older backends do not have /rl/model
    }
  }, []);

  useEffect(() => {
    refresh();
    pollRef.current = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [refresh]);

  const handleSwitch = async (target: ControllerMode) => {
    if (target === mode || switching) return;
    setSwitching(true);
    setError(null);
    const previousMode = mode;
    try {
      const res = await setControllerMode(target);
      setMode(res.mode);
    } catch {
      setError(`Could not switch to ${target === 'DQN' ? 'DQN' : 'rule-based'} mode. Still running the previous mode.`);
      setMode(previousMode);
    } finally {
      setSwitching(false);
    }
  };

  const active = MODES.find((m) => m.value === mode);

  return (
    <Card title="Signal controller" subtitle="Which logic sets the signals">
      <div role="radiogroup" aria-label="Signal controller" className="grid grid-cols-2 gap-0.5 rounded-md bg-subtle p-0.5">
        {MODES.map((m) => {
          const selected = mode === m.value;
          return (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={switching || mode === null}
              onClick={() => handleSwitch(m.value)}
              className={clsx(
                'h-7 rounded text-[13px] font-medium transition-colors disabled:cursor-not-allowed',
                selected ? 'border border-line bg-surface text-ink shadow-sm' : 'border border-transparent text-muted hover:text-ink',
              )}
            >
              {m.label}
            </button>
          );
        })}
      </div>

      <p className="mt-3 min-h-[2.5rem] text-xs leading-relaxed text-muted">{active?.description ?? ' '}</p>

      {mode === 'DQN' && model && (
        <dl className="mt-3 space-y-1.5 border-t border-line pt-3">
          {model.file ? (
            <>
              <Row label="Model">{model.obs_version}</Row>
              <Row label="Checkpoint">episode {model.selected_episode}</Row>
              <Row label="Inputs">{model.state_size} features</Row>
              {model.stats && <Row label="Decisions made">{model.stats.decisions.toLocaleString()}</Row>}
            </>
          ) : (
            <Row label="Model">legacy 5-feature demo</Row>
          )}
        </dl>
      )}

      {switching && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-faint">
          <Loader2 size={12} className="animate-spin" />
          Switching…
        </p>
      )}
      {error && <p className="mt-3 text-xs text-bad">{error}</p>}
    </Card>
  );
}
