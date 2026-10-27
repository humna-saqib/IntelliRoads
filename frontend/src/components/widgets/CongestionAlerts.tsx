import { useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import { resolveCongestionAlert } from '../../services/api';
import Card from '../ui/Card';
import Badge from '../ui/Badge';
import clsx from 'clsx';

const formatTime = (ts: unknown) => {
  if (!ts) return '';
  const date = typeof ts === 'number' ? new Date(ts * 1000) : new Date(String(ts));
  if (isNaN(date.getTime())) return String(ts);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const junctionName = (id: string) => {
  if (id.includes('A')) return 'Junction A';
  if (id.includes('B')) return 'Junction B';
  if (id.includes('C')) return 'Junction C';
  if (id.includes('D')) return 'Junction D';
  return id;
};

export default function CongestionAlerts() {
  const { congestion } = useTraffic();
  const [resolvingIds, setResolvingIds] = useState<Record<string, boolean>>({});
  const [manuallyResolved, setManuallyResolved] = useState<Record<string, boolean>>({});

  const events = congestion?.events ?? [];
  const isOpen = (e: (typeof events)[number]) =>
    e.status === 'CONGESTED' && !e.resolved_at && !manuallyResolved[e.id || e.intersection_id];
  const activeCount = events.filter(isOpen).length;

  const handleResolve = async (key: string) => {
    setResolvingIds((prev) => ({ ...prev, [key]: true }));
    try {
      await resolveCongestionAlert(key);
      setManuallyResolved((prev) => ({ ...prev, [key]: true }));
    } catch (err) {
      console.error('Failed to resolve alert:', err);
    } finally {
      setResolvingIds((prev) => ({ ...prev, [key]: false }));
    }
  };

  return (
    <Card
      title="Congestion alerts"
      subtitle="Lane density above the junction threshold"
      action={<Badge label={`${activeCount} active`} variant={activeCount > 0 ? 'danger' : 'success'} size="sm" />}
      padded={false}
    >
      {events.length === 0 ? (
        <p className="px-4 py-8 text-center text-[13px] text-faint">All lanes clear</p>
      ) : (
        <ul className="max-h-[300px] divide-y divide-line overflow-y-auto">
          {events.map((event, index) => {
            const key = event.id || event.intersection_id;
            const active = isOpen(event);
            const cleared = event.resolved_at || manuallyResolved[key];
            return (
              <li
                key={`${key || 'evt'}-${index}`}
                className={clsx('border-l-2 px-4 py-2.5', active ? 'border-l-bad' : 'border-l-transparent opacity-60')}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium">
                      {junctionName(event.intersection_id)}
                      {event.direction && <span className="ml-2 text-xs font-normal text-muted">{event.direction} approach</span>}
                    </p>
                    <p className="mt-0.5 text-xs text-muted">
                      <span className="font-mono tabular-nums">{event.density_value}</span> veh/km
                      <span className="text-faint"> (threshold {event.threshold})</span>
                    </p>
                  </div>
                  <div className="flex flex-shrink-0 flex-col items-end gap-1">
                    <Badge label={active ? 'Congested' : 'Resolved'} variant={active ? 'danger' : 'success'} size="sm" />
                    {active && (
                      <button
                        onClick={() => handleResolve(key)}
                        disabled={resolvingIds[key]}
                        className="text-xs text-muted underline decoration-strong underline-offset-2 hover:text-ink disabled:opacity-50"
                      >
                        {resolvingIds[key] ? 'Resolving…' : 'Mark resolved'}
                      </button>
                    )}
                  </div>
                </div>
                <p className="mt-1 text-2xs text-faint">
                  Detected {formatTime(event.timestamp)}
                  {cleared && ` · cleared ${formatTime(event.resolved_at || Date.now() / 1000)}`}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
