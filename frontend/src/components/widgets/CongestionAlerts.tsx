import React from 'react';
import { useTraffic } from '../../context/TrafficContext';
import Card from '../ui/Card';
import Badge from '../ui/Badge';
import { AlertTriangle, CheckCircle, Clock } from 'lucide-react';

export default function CongestionAlerts() {
  const { congestion } = useTraffic();

  const events = congestion?.events ?? [];
  const activeEvents = events.filter((e) => e.status === 'CONGESTED' && !e.resolved_at);

  const getJunctionName = (id: string) => {
    if (id.includes('A') || id.includes('junctionA')) return 'Intersection A';
    if (id.includes('B') || id.includes('junctionB')) return 'Intersection B';
    if (id.includes('C') || id.includes('junctionC')) return 'Intersection C';
    if (id.includes('D') || id.includes('junctionD')) return 'Intersection D';
    return id;
  };

  const formatTime = (ts: any) => {
    if (!ts) return '';
    // If it's a number (unix timestamp)
    if (typeof ts === 'number') {
      return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
    // If it is already a string
    try {
      const date = new Date(ts);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return String(ts);
    }
  };

  return (
    <Card
      title="Congestion Alerts"
      subtitle="Real-time traffic bottleneck warnings"
      icon={<AlertTriangle className="h-5 w-5 text-red-500" />}
    >
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-slate-400">Status</span>
        <Badge
          label={`${activeEvents.length} Active`}
          variant={activeEvents.length > 0 ? 'danger' : 'success'}
        />
      </div>

      <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-slate-500">
            <CheckCircle className="h-8 w-8 text-green-500 mb-2" />
            <p className="text-sm font-medium">All lanes clear</p>
          </div>
        ) : (
          events.map((event, index) => {
            const isActive = event.status === 'CONGESTED' && !event.resolved_at;
            return (
              <div
                key={`${event.intersection_id}-${index}`}
                className={`p-3 rounded-lg border bg-slate-900/40 transition-all ${
                  isActive
                    ? 'border-red-500/40 border-l-4 border-l-red-500 animate-pulse-slow'
                    : 'border-slate-800 opacity-60'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="font-semibold text-sm text-slate-200">
                      {getJunctionName(event.intersection_id)}
                      {event.direction && (
                        <span className="ml-2 text-[10px] font-semibold text-amber-400 align-middle">
                          {event.direction} approach
                        </span>
                      )}
                    </h4>
                    <p className="text-xs text-slate-400 mt-1">
                      Density: <span className="font-semibold text-slate-300">{event.density_value} veh/km</span> (Threshold: {event.threshold})
                    </p>
                  </div>
                  <Badge
                    label={isActive ? 'CONGESTED' : 'RESOLVED'}
                    variant={isActive ? 'danger' : 'success'}
                    size="sm"
                  />
                </div>
                <div className="flex items-center gap-1 mt-2 text-[10px] text-slate-500">
                  <Clock className="h-3 w-3" />
                  <span>Detected: {formatTime(event.timestamp)}</span>
                  {event.resolved_at && (
                    <>
                      <span className="mx-1">•</span>
                      <span>Cleared: {formatTime(event.resolved_at)}</span>
                    </>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}
