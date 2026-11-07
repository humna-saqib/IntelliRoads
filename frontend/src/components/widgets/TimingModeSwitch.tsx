import { useEffect, useState } from 'react';
import { fetchControllerMode, setControllerMode, type ControllerMode } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { Loader2, Sliders, Sparkles } from 'lucide-react';
import clsx from 'clsx';

interface TimingModeSwitchProps {
  onModeChange?: (newMode: ControllerMode) => void;
}

export default function TimingModeSwitch({ onModeChange }: TimingModeSwitchProps) {
  const [mode, setMode] = useState<ControllerMode | null>(null);
  const [switching, setSwitching] = useState(false);
  const toast = useToast();

  useEffect(() => {
    fetchControllerMode()
      .then((res) => setMode(res.mode))
      .catch(() => {});
  }, []);

  const handleSwitch = async (target: ControllerMode) => {
    if (target === mode || switching) return;
    setSwitching(true);
    const previous = mode;
    try {
      const res = await setControllerMode(target);
      setMode(res.mode);
      onModeChange?.(res.mode);
      if (res.mode === 'DQN') {
        toast.success('Switched to Smart AI. Lights are now adapting dynamically to live queue lengths.');
      } else {
        toast.info('Switched to Standard timing. Lights are running scheduled threshold cycles.');
      }
    } catch {
      setMode(previous);
      toast.error('Unable to switch controller mode. Traffic system may be busy.');
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-line bg-subtle text-brand">
          <Sparkles size={18} />
        </div>
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-faint">Signal control</span>
          <p className="text-xs text-muted">
            {mode === 'DQN'
              ? 'Smart AI is adapting green lights to live queues'
              : 'Standard timing is cycling through fixed schedules'}
          </p>
        </div>
      </div>

      <div
        role="radiogroup"
        aria-label="Signal control mode"
        className="flex min-h-[44px] items-center rounded-lg border border-line bg-subtle p-1"
      >
        <button
          type="button"
          role="radio"
          aria-checked={mode === 'RULE_BASED'}
          disabled={switching || mode === null}
          onClick={() => handleSwitch('RULE_BASED')}
          className={clsx(
            'flex min-h-[36px] items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-all',
            mode === 'RULE_BASED'
              ? 'bg-surface text-ink shadow-xs'
              : 'text-muted hover:text-ink',
            (switching || mode === null) && 'cursor-not-allowed opacity-60',
          )}
        >
          <Sliders size={13} />
          <span>Standard timing</span>
        </button>

        <button
          type="button"
          role="radio"
          aria-checked={mode === 'DQN'}
          disabled={switching || mode === null}
          onClick={() => handleSwitch('DQN')}
          className={clsx(
            'flex min-h-[36px] items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-all',
            mode === 'DQN'
              ? 'bg-surface text-brand shadow-xs'
              : 'text-muted hover:text-ink',
            (switching || mode === null) && 'cursor-not-allowed opacity-60',
          )}
        >
          {switching ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
          <span>Smart AI</span>
        </button>
      </div>
    </div>
  );
}
