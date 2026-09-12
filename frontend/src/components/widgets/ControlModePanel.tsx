import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Cpu, SlidersHorizontal, Loader2, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';
import Card from '../ui/Card';
import { fetchControllerMode, setControllerMode, type ControllerMode } from '../../services/api';

const POLL_INTERVAL_MS = 5000;

const MODES: { value: ControllerMode; label: string; description: string; icon: React.ReactNode }[] = [
  {
    value: 'RULE_BASED',
    label: 'Rule-Based',
    description: 'Fixed-threshold signal logic',
    icon: <SlidersHorizontal size={15} />,
  },
  {
    value: 'DQN',
    label: 'DQN (AI)',
    description: 'Trained reinforcement-learning agent',
    icon: <Cpu size={15} />,
  },
];

export default function ControlModePanel() {
  const [mode, setMode] = useState<ControllerMode | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetchControllerMode();
      setMode(res.mode);
      setError(null);
    } catch {
      setError('Unable to reach controller mode service.');
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
      setError(`Failed to switch to ${target === 'DQN' ? 'DQN' : 'Rule-Based'} mode. Still running previous mode.`);
      setMode(previousMode);
    } finally {
      setSwitching(false);
    }
  };

  return (
    <Card
      title="Signal Control Mode"
      subtitle="Active traffic signal controller"
      icon={<Cpu size={16} />}
    >
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-2">
          {MODES.map((m) => {
            const active = mode === m.value;
            return (
              <button
                key={m.value}
                type="button"
                disabled={switching || mode === null}
                onClick={() => handleSwitch(m.value)}
                className={clsx(
                  'relative flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition-all duration-200',
                  'disabled:cursor-not-allowed disabled:opacity-60',
                  active
                    ? 'border-primary-500/50 bg-primary-600/15 shadow-[0_0_16px_rgba(59,130,246,0.15)]'
                    : 'border-white/8 bg-white/[0.02] hover:bg-white/[0.05]',
                )}
              >
                <div className="flex items-center gap-1.5">
                  <span className={clsx(active ? 'text-primary-400' : 'text-slate-400')}>
                    {m.icon}
                  </span>
                  <span className={clsx('text-xs font-semibold', active ? 'text-white' : 'text-slate-300')}>
                    {m.label}
                  </span>
                  {active && (
                    <span className="ml-auto flex items-center gap-1 text-[9px] font-bold uppercase tracking-wide text-primary-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-primary-400 animate-pulse" />
                      Active
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-slate-500">{m.description}</p>
              </button>
            );
          })}
        </div>

        {switching && (
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <Loader2 size={12} className="animate-spin" />
            Switching controller mode…
          </div>
        )}

        {error && (
          <div className="flex items-center gap-1.5 text-[11px] text-danger-400">
            <AlertTriangle size={12} />
            {error}
          </div>
        )}

        {mode === null && !error && (
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <Loader2 size={12} className="animate-spin" />
            Loading current mode…
          </div>
        )}
      </div>
    </Card>
  );
}
