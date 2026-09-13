import React, { useEffect, useState, useMemo } from 'react';
import { fetchCongestionHistory } from '../services/api';
import type { CongestionEvent } from '../types/traffic';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { AlertTriangle, Filter, RotateCcw, Clock, MapPin, CheckCircle, ShieldAlert } from 'lucide-react';

export default function AlertHistoryPage() {
  const [loading, setLoading] = useState<boolean>(true);
  const [history, setHistory] = useState<CongestionEvent[]>([]);

  // Filter states
  const [selectedIntersection, setSelectedIntersection] = useState<string>('ALL');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [timeRange, setTimeRange] = useState<string>('ALL');

  const loadHistory = async () => {
    setLoading(true);
    try {
      const params: any = { limit: 500 };
      if (selectedStatus !== 'ALL') params.status = selectedStatus;
      if (selectedIntersection !== 'ALL') params.intersection_id = selectedIntersection;

      const data = await fetchCongestionHistory(params);
      setHistory(data);
    } catch (err) {
      console.error('Failed to fetch congestion history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, [selectedIntersection, selectedStatus]);

  const formatDateTime = (ts: any) => {
    if (!ts) return 'N/A';
    const date = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
    if (isNaN(date.getTime())) return String(ts);
    return date.toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const getJunctionName = (id: string) => {
    if (!id) return 'Unknown Junction';
    if (id.includes('A') || id.includes('junctionA')) return 'Intersection A (NW Square)';
    if (id.includes('B') || id.includes('junctionB')) return 'Intersection B (NE Plaza)';
    if (id.includes('C') || id.includes('junctionC')) return 'Intersection C (SE Gateway)';
    if (id.includes('D') || id.includes('junctionD')) return 'Intersection D (SW Crossing)';
    return id;
  };

  const filteredHistory = useMemo(() => {
    const nowSec = Date.now() / 1000;

    return history.filter((event) => {
      // Intersection filter
      if (selectedIntersection !== 'ALL') {
        const matchesInter =
          event.intersection_id.toLowerCase().includes(selectedIntersection.toLowerCase());
        if (!matchesInter) return false;
      }

      // Status filter
      if (selectedStatus !== 'ALL') {
        const isCongested = (event.status === 'CONGESTED' || (event.status as string) === 'ACTIVE') && !event.resolved_at;
        if (selectedStatus === 'ACTIVE' && !isCongested) return false;
        if (selectedStatus === 'RESOLVED' && isCongested) return false;
      }

      // Time range filter
      if (timeRange !== 'ALL') {
        const eventTs = typeof event.timestamp === 'number' ? event.timestamp : new Date(event.timestamp).getTime() / 1000;
        if (timeRange === '15M' && nowSec - eventTs > 15 * 60) return false;
        if (timeRange === '1H' && nowSec - eventTs > 60 * 60) return false;
        if (timeRange === '24H' && nowSec - eventTs > 24 * 60 * 60) return false;
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
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-slate-900/40 p-5 rounded-2xl border border-white/5 backdrop-blur-md">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <ShieldAlert className="h-6 w-6 text-amber-400" />
            Congestion Alerts History
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Historical record of bottleneck events, threshold breaches, and manual resolutions
          </p>
        </div>

        <button
          onClick={loadHistory}
          className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-4 py-2 rounded-xl border border-white/10 transition-all"
        >
          <RotateCcw size={14} />
          Refresh History
        </button>
      </div>

      {/* Filter Toolbar */}
      <Card
        title="Filter Alerts"
        subtitle="Search and refine alert records by location, resolution state, and timeframe"
        icon={<Filter className="h-5 w-5 text-cyan-400" />}
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
          {/* Intersection / Location filter */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              Location / Junction
            </label>
            <select
              value={selectedIntersection}
              onChange={(e) => setSelectedIntersection(e.target.value)}
              className="w-full bg-slate-950 border border-white/10 text-slate-200 text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-cyan-500 transition-colors"
            >
              <option value="ALL">All Intersections & Lanes</option>
              <option value="junctionA">Intersection A (Northwest)</option>
              <option value="junctionB">Intersection B (Northeast)</option>
              <option value="junctionC">Intersection C (Southeast)</option>
              <option value="junctionD">Intersection D (Southwest)</option>
            </select>
          </div>

          {/* Alert Status filter */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              Alert Status
            </label>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="w-full bg-slate-950 border border-white/10 text-slate-200 text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-cyan-500 transition-colors"
            >
              <option value="ALL">All States (Active & Resolved)</option>
              <option value="ACTIVE">Active Congestion Only</option>
              <option value="RESOLVED">Resolved Events Only</option>
            </select>
          </div>

          {/* Time Window filter */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              Timeframe
            </label>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="w-full bg-slate-950 border border-white/10 text-slate-200 text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-cyan-500 transition-colors"
            >
              <option value="ALL">All Time</option>
              <option value="15M">Last 15 minutes</option>
              <option value="1H">Last 1 hour</option>
              <option value="24H">Last 24 hours</option>
            </select>
          </div>
        </div>

        <div className="flex justify-end mt-4 pt-3 border-t border-white/5">
          <button
            onClick={handleResetFilters}
            className="text-xs text-slate-400 hover:text-white flex items-center gap-1 transition-colors"
          >
            <RotateCcw size={12} />
            Reset Filters
          </button>
        </div>
      </Card>

      {/* History Table Card */}
      <Card
        title={`Alert Records (${filteredHistory.length})`}
        subtitle="Chronological log of detected bottlenecks"
        icon={<AlertTriangle className="h-5 w-5 text-red-400" />}
      >
        {loading ? (
          <div className="flex py-16 justify-center">
            <LoadingSpinner size="lg" />
          </div>
        ) : filteredHistory.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-500">
            <CheckCircle className="h-10 w-10 text-emerald-500/50 mb-3" />
            <p className="text-sm font-medium text-slate-300">No alert records match filters</p>
            <p className="text-xs text-slate-500 mt-1">Try resetting your filters or adjusting the timeframe.</p>
          </div>
        ) : (
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-white/10 text-slate-400 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Event ID</th>
                  <th className="py-3 px-4">Location / Lane</th>
                  <th className="py-3 px-4">Approach</th>
                  <th className="py-3 px-4">Density Reading</th>
                  <th className="py-3 px-4 text-center">Status</th>
                  <th className="py-3 px-4">Detected At</th>
                  <th className="py-3 px-4">Resolved At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-200">
                {filteredHistory.map((event, idx) => {
                  const isActive = (event.status === 'CONGESTED' || (event.status as string) === 'ACTIVE') && !event.resolved_at;
                  const displayId = event.id ? event.id.substring(0, 18) : `evt-${idx}`;

                  return (
                    <tr key={event.id || `${event.intersection_id}-${idx}`} className="hover:bg-white/2 transition-colors">
                      <td className="py-3.5 px-4 font-mono font-medium text-slate-300" title={event.id}>
                        {displayId}
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-white flex items-center gap-1.5">
                          <MapPin size={12} className="text-slate-400" />
                          {getJunctionName(event.intersection_id)}
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono mt-0.5">{event.intersection_id}</div>
                      </td>
                      <td className="py-3.5 px-4">
                        {event.direction ? (
                          <span className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            {event.direction} Bound
                          </span>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 font-mono">
                        <span className={isActive ? 'text-red-400 font-bold' : 'text-slate-300'}>
                          {event.density_value.toFixed(1)} veh/km
                        </span>
                        <span className="text-slate-500 text-[10px] block">Thresh: {event.threshold}</span>
                      </td>
                      <td className="py-3.5 px-4 text-center">
                        <Badge
                          label={isActive ? 'CONGESTED' : 'RESOLVED'}
                          variant={isActive ? 'danger' : 'success'}
                          size="sm"
                        />
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-400">
                        <div className="flex items-center gap-1">
                          <Clock size={12} />
                          {formatDateTime(event.timestamp)}
                        </div>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-400">
                        {event.resolved_at ? (
                          formatDateTime(event.resolved_at)
                        ) : (
                          <span className="text-red-400 font-sans text-[11px]">Still Active</span>
                        )}
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
  );
}
