import { useTraffic } from '../context/TrafficContext';
import { getJunctionName } from '../constants/plainWords';
import ErrorState from '../components/ui/ErrorState';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import EmergencyPriorityBanner from '../components/widgets/EmergencyPriorityBanner';
import { CheckCircle2, AlertTriangle, AlertOctagon } from 'lucide-react';
import clsx from 'clsx';

export default function HomePage() {
  const { isBackendOffline, isLoading, kpis, intersections, retryConnection } = useTraffic();

  if (isBackendOffline && !kpis) {
    return (
      <div className="py-12">
        <ErrorState
          title="Traffic system offline"
          message="We can't reach the traffic system right now. Retrying connection..."
          onRetry={retryConnection}
        />
      </div>
    );
  }

  if (isLoading && !kpis) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <LoadingSpinner size="lg" label="Connecting to traffic system…" />
      </div>
    );
  }

  // 1. Status sentence & what-to-do determination
  const congestedJunctions = intersections.filter((j) => j.congestion_status === 'CONGESTED');
  const hasSevereCongestion = congestedJunctions.length > 0;
  const hasModerateCongestion = !hasSevereCongestion && ((kpis?.congestion_percentage ?? 0) > 20 || (kpis?.active_alerts ?? 0) > 0);

  let statusTitle = 'Traffic is flowing smoothly across all intersections';
  let whatToDo = 'All monitored corridors are clear. No special action is required.';
  let tone: 'good' | 'warn' | 'bad' = 'good';

  if (hasSevereCongestion) {
    tone = 'bad';
    const names = congestedJunctions.map((j) => getJunctionName(j.id));
    if (names.length === 1) {
      statusTitle = `Heavy congestion at ${names[0]}`;
    } else {
      statusTitle = `Heavy congestion at ${names.slice(0, 2).join(' and ')}${names.length > 2 ? ` and ${names.length - 2} other junction` : ''}`;
    }
    whatToDo = 'Signal control is prioritizing these approaches to clear queues. Keep monitoring the active corridors.';
  } else if (hasModerateCongestion) {
    tone = 'warn';
    statusTitle = 'Moderate traffic buildup across monitored intersections';
    whatToDo = 'Traffic is moving steadily. System timing is adjusting phase lengths to maintain flow.';
  }

  return (
    <div className="space-y-6">
      <EmergencyPriorityBanner />

      {/* Item 1: Status sentence at the top with colored edge + what to do */}
      <div
        role="status"
        aria-live="polite"
        className={clsx(
          'relative rounded-xl border border-line bg-surface p-5 shadow-xs transition-all',
          'border-l-4',
          tone === 'bad' && 'border-l-bad bg-bad/[0.03]',
          tone === 'warn' && 'border-l-warn bg-warn/[0.03]',
          tone === 'good' && 'border-l-ok bg-ok/[0.03]',
        )}
      >
        <div className="flex items-start gap-3.5">
          <div className="mt-0.5 flex-shrink-0">
            {tone === 'bad' && <AlertOctagon size={20} className="text-bad" />}
            {tone === 'warn' && <AlertTriangle size={20} className="text-warn" />}
            {tone === 'good' && <CheckCircle2 size={20} className="text-ok" />}
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-semibold tracking-tight text-ink sm:text-lg">
              {statusTitle}
            </h1>
            <p className="mt-1 text-sm text-muted">
              <span className="font-medium text-ink">What to do: </span>
              {whatToDo}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
