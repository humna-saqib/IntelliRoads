import { useLocation } from 'react-router-dom';
import { Menu, LogOut } from 'lucide-react';
import { useTraffic } from '../../context/TrafficContext';
import ThemeToggle from '../ui/ThemeToggle';
import StatusIndicator from '../ui/StatusIndicator';

const PAGE_TITLES: Record<string, string> = {
  '/': 'Overview',
  '/map': 'Traffic map',
  '/analytics': 'Analytics',
  '/alerts': 'Alert history',
  '/reports': 'Reports',
  '/settings': 'Settings',
};

function formatSimTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = m.toString().padStart(2, '0');
  const ss = s.toString().padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

interface HeaderProps {
  onMenuClick: () => void;
  onLogout?: () => void;
}

export default function Header({ onMenuClick, onLogout }: HeaderProps) {
  const location = useLocation();
  const { kpis, connectionStatus } = useTraffic();
  const title = PAGE_TITLES[location.pathname] ?? 'IntelliRoads';

  const indicator =
    connectionStatus === 'connected' ? 'online' :
    connectionStatus === 'connecting' ? 'connecting' :
    'offline';
  const statusLabel =
    connectionStatus === 'connected' ? 'Live' :
    connectionStatus === 'connecting' ? 'Connecting' :
    'Offline';

  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between gap-3 border-b border-line bg-page px-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <button onClick={onMenuClick} className="btn btn-ghost btn-icon -ml-2 lg:hidden" aria-label="Open menu">
          <Menu size={18} />
        </button>
        <h1 className="truncate text-[15px] font-medium">{title}</h1>
      </div>

      <div className="flex flex-shrink-0 items-center gap-1 sm:gap-2">
        {kpis && (
          <span className="mr-1 hidden items-baseline gap-1.5 sm:flex" title="Simulation clock">
            <span className="text-xs text-faint">Sim time</span>
            <span className="font-mono text-[13px] tabular-nums text-ink">{formatSimTime(kpis.simulation_time)}</span>
          </span>
        )}
        <span className="mr-1 hidden sm:inline-flex">
          <StatusIndicator status={indicator} label={statusLabel} />
        </span>
        <ThemeToggle />
        {onLogout && (
          <button onClick={onLogout} className="btn btn-ghost" title="Log out">
            <LogOut size={15} strokeWidth={1.75} />
            <span className="hidden sm:inline">Log out</span>
          </button>
        )}
      </div>
    </header>
  );
}
