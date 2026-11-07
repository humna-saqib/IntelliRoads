import { useTraffic } from '../../context/TrafficContext';
import clsx from 'clsx';

interface LiveStatusBadgeProps {
  className?: string;
  showTimestamp?: boolean;
}

export default function LiveStatusBadge({
  className,
  showTimestamp = true,
}: LiveStatusBadgeProps) {
  const { connectionStatus, lastUpdate } = useTraffic();

  const isLive = connectionStatus === 'connected';
  const isConnecting = connectionStatus === 'connecting';
  const isOffline = !isLive && !isConnecting;

  const statusLabel = isLive ? 'Live' : isConnecting ? 'Connecting…' : 'Offline';

  const formatTime = (ts: number | null): string => {
    if (!ts) return '';
    const d = new Date(ts);
    const hh = d.getHours().toString().padStart(2, '0');
    const mm = d.getMinutes().toString().padStart(2, '0');
    const ss = d.getSeconds().toString().padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
  };

  const timeString = formatTime(lastUpdate);

  return (
    <div
      role="status"
      aria-live="polite"
      className={clsx(
        'inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
        isLive && 'border-ok/30 bg-ok/10 text-ok',
        isConnecting && 'border-warn/30 bg-warn/10 text-warn',
        isOffline && 'border-bad/30 bg-bad/10 text-bad',
        className,
      )}
    >
      <span
        className={clsx(
          'h-2 w-2 rounded-full transition-transform',
          isLive && 'bg-ok shadow-[0_0_6px_rgba(34,197,94,0.6)]',
          isConnecting && 'animate-pulse bg-warn',
          isOffline && 'bg-bad',
        )}
      />
      <span className="font-semibold">{statusLabel}</span>

      {showTimestamp && timeString && (
        <>
          <span className="opacity-40" aria-hidden="true">·</span>
          <span className="font-mono text-2xs font-normal tabular-nums opacity-90">
            last updated {timeString}
          </span>
        </>
      )}
    </div>
  );
}
