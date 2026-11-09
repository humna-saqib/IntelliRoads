import { useEffect, useState, useMemo } from 'react';
import { fetchCongestionHistory } from '../services/api';
import { useTraffic } from '../context/TrafficContext';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import PageIntro from '../components/ui/PageIntro';
import { RotateCcw, Download } from 'lucide-react';
import type { CongestionEvent } from '../types/traffic';
import { getJunctionName } from '../constants/plainWords';

export default function AlertHistoryPage() {
  const { isBackendOffline } = useTraffic();
  const [loading, setLoading] = useState<boolean>(true);
  const [history, setHistory] = useState<CongestionEvent[]>([]);

  const [selectedIntersection, setSelectedIntersection] = useState<string>('ALL');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [timeRange, setTimeRange] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const loadHistory = async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { limit: 500 };
      if (selectedStatus !== 'ALL') params.status = selectedStatus;
      if (selectedIntersection !== 'ALL') params.intersection_id = selectedIntersection;
      setHistory(await fetchCongestionHistory(params));
    } catch (err) {
      console.error('Failed to fetch congestion history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = 'Past Warnings · IntelliRoads';
  }, []);

  useEffect(() => {
    loadHistory();
  }, [selectedIntersection, selectedStatus]);

  const formatDateTime = (ts: unknown) => {
    if (!ts) return 'N/A';
    const date = typeof ts === 'number' ? new Date(ts * 1000) : new Date(String(ts));
    if (isNaN(date.getTime())) return String(ts);
    return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const getCause = (event: CongestionEvent): string => {
    if (event.density_value > event.threshold) {
      return 'Too many cars — road density exceeded the warning limit';
    }
    return 'Road became congested';
  };

  const toSec = (v: unknown) => {
    if (!v) return null;
    const n = typeof v === 'number' ? v : new Date(String(v)).getTime() / 1000;
    return isNaN(n) ? null : n;
  };

  const formatDuration = (start: unknown, end?: unknown): string => {
    const s = toSec(start);
    const e = toSec(end);
    if (!s) return '';
    const dur = (e ?? Date.now() / 1000) - s;
    if (dur < 60) return `${Math.round(dur)}s`;
    const mins = Math.round(dur / 60);
    return mins === 1 ? 'lasted 1 minute' : `lasted ${mins} minutes`;
  };

  const isActiveEvent = (event: CongestionEvent) =>
    (event.status === 'CONGESTED' || (event.status as string) === 'ACTIVE') && !event.resolved_at;

  const filteredHistory = useMemo(() => {
    const nowSec = Date.now() / 1000;
    return history
      .filter((event) => {
        if (!searchQuery.trim()) return true;
        const q = searchQuery.toLowerCase();
        const name = getJunctionName(event.intersection_id).toLowerCase();
        const cause = getCause(event).toLowerCase();
        return name.includes(q) || cause.includes(q);
      })
      .filter((event) => {
        if (selectedIntersection !== 'ALL' && !event.intersection_id.toLowerCase().includes(selectedIntersection.toLowerCase())) return false;

        if (selectedStatus !== 'ALL') {
          const active = isActiveEvent(event);
          if (selectedStatus === 'ACTIVE' && !active) return false;
          if (selectedStatus === 'RESOLVED' && active) return false;
        }

        if (timeRange !== 'ALL') {
          const eventTs = typeof event.timestamp === 'number' ? event.timestamp : new Date(event.timestamp).getTime() / 1000;
          const limit = timeRange === '15M' ? 15 * 60 : timeRange === '1H' ? 60 * 60 : 24 * 60 * 60;
          if (nowSec - eventTs > limit) return false;
        }

        return true;
      });
  }, [history, selectedIntersection, selectedStatus, timeRange, searchQuery]);

  const handleResetFilters = () => {
    setSelectedIntersection('ALL');
    setSelectedStatus('ALL');
    setTimeRange('ALL');
    setSearchQuery('');
  };

  const exportCsv = () => {
    const header = ['Junction', 'Cause', 'Density (cars/km)', 'Warning limit', 'Status', 'Detected', 'Resolved'];
    const rows = filteredHistory.map((e) => [
      getJunctionName(e.intersection_id),
      getCause(e),
      e.density_value.toFixed(1),
      String(e.threshold),
      isActiveEvent(e) ? 'Ongoing' : 'Resolved',
      formatDateTime(e.timestamp),
      e.resolved_at ? formatDateTime(e.resolved_at) : 'Still active',
    ]);
    const csv = [header, ...rows].map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const dateStr = new Date().toISOString().slice(0, 10);
    a.download = `intelliroads-warnings-${dateStr}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <PageIntro
        description="A record of congestion events — when a junction approach became overcrowded and when it cleared."
        actions={
          <div className="flex gap-2">
            <button onClick={exportCsv} className="btn btn-ghost" disabled={filteredHistory.length === 0}>
              <Download size={14} strokeWidth={1.75} />
              Export CSV
            </button>
            <button onClick={loadHistory} className="btn">
              <RotateCcw size={14} strokeWidth={1.75} />
              Refresh
            </button>
          </div>
        }
      />

      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 rounded-lg border border-line bg-surface p-4 sm:grid-cols-4">
          <div className="sm:col-span-4">
            <label htmlFor="f-search" className="field-label">Search</label>
            <input
              id="f-search"
              type="search"
              placeholder="Junction name or cause…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="input"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4 sm:col-span-4">
            <div>
              <label htmlFor="f-junction" className="field-label">Junction</label>
              <select id="f-junction" value={selectedIntersection} onChange={(e) => setSelectedIntersection(e.target.value)} className="input">
                <option value="ALL">All junctions</option>
                <option value="junctionA">Junction A (Northwest)</option>
                <option value="junctionB">Junction B (Northeast)</option>
                <option value="junctionC">Junction C (Southeast)</option>
                <option value="junctionD">Junction D (Southwest)</option>
              </select>
            </div>
            <div>
              <label htmlFor="f-status" className="field-label">Status</label>
              <select id="f-status" value={selectedStatus} onChange={(e) => setSelectedStatus(e.target.value)} className="input">
                <option value="ALL">Active and resolved</option>
                <option value="ACTIVE">Active only</option>
                <option value="RESOLVED">Resolved only</option>
              </select>
            </div>
            <div>
              <label htmlFor="f-time" className="field-label">Time range</label>
              <select id="f-time" value={timeRange} onChange={(e) => setTimeRange(e.target.value)} className="input">
                <option value="ALL">All time</option>
                <option value="15M">Last 15 minutes</option>
                <option value="1H">Last hour</option>
                <option value="24H">Last 24 hours</option>
              </select>
            </div>
            <div className="flex items-end">
              <button onClick={handleResetFilters} className="btn btn-ghost">Reset filters</button>
            </div>
          </div>
        </div>

        <Card title={`Past warnings (${filteredHistory.length})`} subtitle="Newest first" padded={false}>
          {loading ? (
            <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
          ) : isBackendOffline && history.length === 0 ? (
            <div className="p-6">
              <ErrorState
                title="Past warnings unavailable"
                message="We can't connect to the server right now to fetch past warnings."
                onRetry={loadHistory}
              />
            </div>
          ) : filteredHistory.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-[13px] font-medium">No past warnings match these filters</p>
              <p className="mt-1 text-xs text-faint">Try resetting the filters or widening the time range.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Warning</th>
                    <th>Junction</th>
                    <th>Approach</th>
                    <th>Density</th>
                    <th>Status</th>
                    <th>Detected</th>
                    <th>Resolved</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredHistory.map((event, idx) => {
                    const active = isActiveEvent(event);
                    return (
                      <tr key={event.id || `${event.intersection_id}-${idx}`}>
                        <td>
                          <p className="text-[13px] font-medium">{getCause(event)}</p>
                          <p className="text-xs text-muted">
                            {formatDuration(event.timestamp, event.resolved_at || undefined)}
                            {!event.resolved_at && <span className="ml-1 text-bad">· still ongoing</span>}
                          </p>
                        </td>
                        <td>
                          <span className="text-[13px]">{getJunctionName(event.intersection_id)}</span>
                        </td>
                        <td className="text-muted">{event.direction ? `${event.direction}bound` : '–'}</td>
                        <td className="whitespace-nowrap text-xs">
                          <span className={active ? 'font-mono tabular-nums text-bad' : 'font-mono tabular-nums'}>
                            {event.density_value.toFixed(1)} cars/km
                          </span>
                          <br />
                          <span className="text-faint">limit: {event.threshold} cars/km</span>
                        </td>
                        <td><Badge label={active ? 'Congested' : 'Resolved'} variant={active ? 'danger' : 'success'} size="sm" /></td>
                        <td className="whitespace-nowrap font-mono text-xs text-muted">{formatDateTime(event.timestamp)}</td>
                        <td className="whitespace-nowrap font-mono text-xs text-muted">
                          {event.resolved_at ? formatDateTime(event.resolved_at) : <span className="font-sans text-bad">Still active</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
