import { useLocation } from 'react-router-dom';
import { Clock, Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { useTraffic } from '../../context/TrafficContext';
import clsx from 'clsx';

const PAGE_TITLES: Record<string, string> = {
  '/':          'Dashboard Overview',
  '/map':       'Traffic Map',
  '/analytics': 'Analytics',
};

function formatSimTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return h > 0
    ? `${h}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`
    : `${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`;
}

function formatLastUpdated(ts: number | null): string {
  if (!ts) return 'Never';
  const delta = Math.floor((Date.now() - ts) / 1000);
  if (delta < 5)  return 'Just now';
  if (delta < 60) return `${delta}s ago`;
  return `${Math.floor(delta / 60)}m ago`;
}

export default function Header() {
  const location   = useLocation();
  const { kpis, isConnected, lastUpdate, connectionStatus, isLoading } = useTraffic();
  const title = PAGE_TITLES[location.pathname] ?? 'IntelliRoads';

  return (
    <header className="flex items-center justify-between px-6 py-3.5 bg-slate-950/80 backdrop-blur-md border-b border-white/5 z-10">
      {/* Left: page title */}
      <div>
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <p className="text-xs text-slate-500">IntelliRoads AI Traffic Control System</p>
      </div>

      {/* Right: status bar */}
      <div className="flex items-center gap-4">
        {/* Loading indicator */}
        {isLoading && (
          <RefreshCw size={14} className="text-accent-400 animate-spin" />
        )}

        {/* Simulation time */}
        {kpis && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/8">
            <Clock size={13} className="text-accent-400" />
            <span className="text-xs font-mono text-slate-300">
              {formatSimTime(kpis.simulation_time)}
            </span>
          </div>
        )}

        {/* Last updated */}
        <div className="text-xs text-slate-500 hidden sm:block">
          Updated {formatLastUpdated(lastUpdate)}
        </div>

        {/* WS status badge */}
        <div
          className={clsx(
            'flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium',
            connectionStatus === 'connected'
              ? 'bg-success-500/10 border-success-500/30 text-success-400'
              : connectionStatus === 'connecting'
              ? 'bg-accent-500/10 border-accent-500/30 text-accent-400'
              : 'bg-danger-500/10  border-danger-500/30  text-danger-400',
          )}
        >
          {isConnected
            ? <Wifi size={13} />
            : <WifiOff size={13} />
          }
          {connectionStatus === 'connected'
            ? 'Live'
            : connectionStatus === 'connecting'
            ? 'Connecting'
            : 'Offline'}
        </div>
      </div>
    </header>
  );
}
