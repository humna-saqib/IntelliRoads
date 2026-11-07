import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTraffic } from '../context/TrafficContext';
import { getJunctionName, formatMinutesOnly } from '../constants/plainWords';
import { fetchControllerMode, fetchPerformance } from '../services/api';
import type { PerformanceSummary } from '../types/traffic';
import ErrorState from '../components/ui/ErrorState';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Badge from '../components/ui/Badge';
import EmergencyPriorityBanner from '../components/widgets/EmergencyPriorityBanner';
import JunctionCard from '../components/widgets/JunctionCard';
import TimingModeSwitch from '../components/widgets/TimingModeSwitch';
import {
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  TrendingUp,
  TrendingDown,
  Minus,
  Clock,
  ShieldAlert,
  ArrowRight,
} from 'lucide-react';
import clsx from 'clsx';

export default function HomePage() {
  const {
    isBackendOffline,
    isLoading,
    kpis,
    kpiHistory,
    intersections,
    signals,
    congestion,
    retryConnection,
  } = useTraffic();
  const [controllerMode, setControllerMode] = useState<string | null>(null);
  const [perfSummaries, setPerfSummaries] = useState<PerformanceSummary[]>([]);

  useEffect(() => {
    fetchControllerMode()
      .then((res) => setControllerMode(res.mode))
      .catch(() => {});

    // Fetch minute-by-minute performance summary for trend fallback
    fetchPerformance(10)
      .then((res) => {
        if (res?.per_minute) setPerfSummaries(res.per_minute);
      })
      .catch(() => {});
  }, []);

  // Item 3: Calculate 5-minute trend note from real rolling buffer or per_minute API data
  const trend = useMemo(() => {
    const now = Date.now();
    const fiveMinutesAgo = now - 5 * 60 * 1000;

    // Check rolling buffer first
    if (kpiHistory.length > 0 && kpis) {
      // Find oldest point or point closest to 5 minutes ago
      let closestPoint = kpiHistory[0];
      let minDiff = Math.abs(closestPoint.timestamp - fiveMinutesAgo);

      for (const p of kpiHistory) {
        const diff = Math.abs(p.timestamp - fiveMinutesAgo);
        if (diff < minDiff) {
          minDiff = diff;
          closestPoint = p;
        }
      }

      const elapsedSec = (now - closestPoint.timestamp) / 1000;
      if (elapsedSec >= 45) {
        const speedDiffKmh = (kpis.average_speed - closestPoint.averageSpeed) * 3.6;
        const waitDiffSec = kpis.average_wait_time - closestPoint.averageWaitTime;

        if (speedDiffKmh >= 1.5 || waitDiffSec <= -8) {
          return {
            title: 'Better than 5 minutes ago',
            description: `Traffic is clearing up — average speeds improved by ${Math.abs(Math.round(speedDiffKmh))} km/h.`,
            tone: 'better' as const,
          };
        }
        if (speedDiffKmh <= -1.5 || waitDiffSec >= 8) {
          return {
            title: 'Worse than 5 minutes ago',
            description: `Delays increased slightly — wait times are up by ${formatMinutesOnly(Math.abs(waitDiffSec))}.`,
            tone: 'worse' as const,
          };
        }
        return {
          title: 'Stable compared to 5 minutes ago',
          description: 'Flow rates and vehicle speeds have remained steady.',
          tone: 'stable' as const,
        };
      }
    }

    // Fallback to /api/performance per_minute data
    if (perfSummaries.length >= 2) {
      const latest = perfSummaries[perfSummaries.length - 1];
      const pastIndex = Math.max(0, perfSummaries.length - 5);
      const past = perfSummaries[pastIndex];

      const waitDiff = latest.avg_waiting_time - past.avg_waiting_time;
      if (waitDiff <= -5) {
        return {
          title: 'Better than 5 minutes ago',
          description: `Average queue delays decreased by ${formatMinutesOnly(Math.abs(waitDiff))}.`,
          tone: 'better' as const,
        };
      }
      if (waitDiff >= 5) {
        return {
          title: 'Worse than 5 minutes ago',
          description: `Corridor queue delays increased by ${formatMinutesOnly(waitDiff)}.`,
          tone: 'worse' as const,
        };
      }
      return {
        title: 'Stable compared to 5 minutes ago',
        description: 'Waiting times have held steady across intersections.',
        tone: 'stable' as const,
      };
    }

    return {
      title: 'Tracking 5-minute trend',
      description: 'Accumulating initial traffic history from active simulation feed.',
      tone: 'collecting' as const,
    };
  }, [kpiHistory, kpis, perfSummaries]);

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

  // Item 4: Active warning count from real KPI / congestion data
  const activeWarningCount = kpis?.active_alerts ?? (congestion?.total_congested ?? 0);

  return (
    <div className="space-y-6">
      <EmergencyPriorityBanner />

      {/* Item 1 & Item 3: Status sentence at the top with colored edge, what-to-do, and 5-min trend note */}
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
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
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

          {/* Item 3: Trend note */}
          <div className="flex-shrink-0 rounded-lg border border-line bg-subtle/80 px-3.5 py-2.5 md:max-w-[280px]">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-ink">
              {trend.tone === 'better' && <TrendingUp size={14} className="text-ok" />}
              {trend.tone === 'worse' && <TrendingDown size={14} className="text-bad" />}
              {trend.tone === 'stable' && <Minus size={14} className="text-muted" />}
              {trend.tone === 'collecting' && <Clock size={14} className="text-faint" />}
              <span>{trend.title}</span>
            </div>
            <p className="mt-0.5 text-2xs leading-relaxed text-muted">
              {trend.description}
            </p>
          </div>
        </div>
      </div>

      {/* Item 4 & Item 5: Timing Mode Switch and Open Warnings shortcut */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <TimingModeSwitch onModeChange={(newMode) => setControllerMode(newMode)} />

        <Link
          to="/alerts"
          aria-label={`Open warnings: ${activeWarningCount} active alerts`}
          className={clsx(
            'group flex min-h-[44px] items-center justify-between gap-4 rounded-xl border px-4 py-3 shadow-xs transition-all',
            activeWarningCount > 0
              ? 'border-bad/30 bg-bad/5 text-ink hover:border-bad/50 hover:bg-bad/10'
              : 'border-line bg-surface text-ink hover:bg-subtle',
          )}
        >
          <div className="flex items-center gap-3">
            <div
              className={clsx(
                'flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border',
                activeWarningCount > 0
                  ? 'border-bad/20 bg-bad/10 text-bad'
                  : 'border-line bg-subtle text-faint',
              )}
            >
              <ShieldAlert size={18} />
            </div>
            <div className="text-left">
              <span className="text-sm font-semibold tracking-tight text-ink">Open warnings</span>
              <p className="text-xs text-muted">
                {activeWarningCount === 0
                  ? 'No active traffic bottlenecks'
                  : `${activeWarningCount} active traffic warning${activeWarningCount === 1 ? '' : 's'} recorded`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge
              label={activeWarningCount > 0 ? `${activeWarningCount} active` : '0 active'}
              variant={activeWarningCount > 0 ? 'danger' : 'neutral'}
              size="sm"
            />
            <ArrowRight size={15} className="text-faint transition-transform group-hover:translate-x-0.5" />
          </div>
        </Link>
      </div>

      {/* Item 2: One card per junction */}
      <section aria-labelledby="junctions-heading" className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 id="junctions-heading" className="text-sm font-semibold tracking-tight text-ink sm:text-base">
            Monitored Junctions
          </h2>
          <span className="text-xs text-muted">Real-time light status & queue levels</span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {intersections.map((intersection) => {
            const sig = signals?.signals.find((s) => s.junction_id === intersection.id);
            return (
              <JunctionCard
                key={intersection.id}
                intersection={intersection}
                signal={sig}
                controllerMode={controllerMode}
              />
            );
          })}
        </div>
      </section>
    </div>
  );
}
