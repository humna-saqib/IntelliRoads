import { useEffect, useState, useMemo } from 'react';
import { fetchCongestionHistory } from '../services/api';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import PageIntro from '../components/ui/PageIntro';
import { RotateCcw } from 'lucide-react';
import type { CongestionEvent } from '../types/traffic';

export default function AlertHistoryPage() {
  const [loading, setLoading] = useState<boolean>(true);
  const [history, setHistory] = useState<CongestionEvent[]>([]);

  const [selectedIntersection, setSelectedIntersection] = useState<string>('ALL');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [timeRange, setTimeRange] = useState<string>('ALL');

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
    loadHistory();
  }, [selectedIntersection, selectedStatus]);

  const formatDateTime = (ts: unknown) => {
    if (!ts) return 'N/A';
    const date = typeof ts === 'number' ? new Date(ts * 1000) : new Date(String(ts));
    if (isNaN(date.getTime())) return String(ts);
    return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const getJunctionName = (id: string) => {
    if (!id) return 'Unknown junction';
    if (id.includes('A')) return 'Junction A · Northwest Square';
    if (id.includes('B')) return 'Junction B · Northeast Plaza';
    if (id.includes('C')) return 'Junction C · Southeast Gateway';
    if (id.includes('D')) return 'Junction D · Southwest Crossing';
    return id;
  };

  const isActiveEvent = (event: CongestionEvent) =>
    (event.status === 'CONGESTED' || (event.status as string) === 'ACTIVE') && !event.resolved_at;

  const filteredHistory = useMemo(() => {
    const nowSec = Date.now() / 1000;
    return history.filter((event) => {
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
  }, [history, selectedIntersection, selectedStatus, timeRange]);

  const handleResetFilters = () => {
    setSelectedIntersection('ALL');
    setSelectedStatus('ALL');
    setTimeRange('ALL');
  };

  return (
    <div>
      <PageIntro
        description="Record of congestion events: when a junction approach went over its density threshold and when it cleared."
        actions={
          <button onClick={loadHistory} className="btn">
            <RotateCcw size={14} strokeWidth={1.75} />
            Refresh
          </button>
        }
      />

      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 rounded-lg border border-line bg-surface p-4 sm:grid-cols-4">
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

        <Card title={`Alert records (${filteredHistory.length})`} subtitle="Newest first" padded={false}>
          {loading ? (
            <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
          ) : filteredHistory.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-[13px] font-medium">No alert records match these filters</p>
              <p className="mt-1 text-xs text-faint">Try resetting the filters or widening the time range.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Event</th>
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
                        <td className="font-mono text-xs text-muted" title={event.id}>{event.id ? event.id.substring(0, 14) : `evt-${idx}`}</td>
                        <td>
                          <span className="text-[13px]">{getJunctionName(event.intersection_id)}</span>
                        </td>
                        <td className="text-muted">{event.direction ? `${event.direction}bound` : '–'}</td>
                        <td className="whitespace-nowrap">
                          <span className={active ? 'font-mono tabular-nums text-bad' : 'font-mono tabular-nums'}>{event.density_value.toFixed(1)}</span>
                          <span className="ml-1 text-xs text-faint">veh/km · limit {event.threshold}</span>
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
