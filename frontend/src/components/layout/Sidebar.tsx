import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Map, BarChart3, FileText, ShieldAlert, Settings2, X } from 'lucide-react';
import { useTraffic } from '../../context/TrafficContext';
import StatusIndicator from '../ui/StatusIndicator';
import Logo from '../ui/Logo';
import clsx from 'clsx';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/map', label: 'Traffic map', icon: Map },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/alerts', label: 'Alert history', icon: ShieldAlert },
  { to: '/reports', label: 'Reports', icon: FileText },
  { to: '/settings', label: 'Settings', icon: Settings2 },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { connectionStatus, kpis } = useTraffic();

  const statusLabel =
    connectionStatus === 'connected' ? 'Live feed' :
    connectionStatus === 'connecting' ? 'Connecting' :
    connectionStatus === 'disconnected' ? 'Offline' :
    'Connection error';

  const indicator =
    connectionStatus === 'connected' ? 'online' :
    connectionStatus === 'connecting' ? 'connecting' :
    connectionStatus === 'error' ? 'warning' :
    'offline';

  return (
    <>
      {isOpen && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={onClose} aria-hidden="true" />}

      <aside
        className={clsx(
          'fixed left-0 top-0 z-40 flex h-full w-56 flex-shrink-0 flex-col border-r border-line bg-surface',
          'transition-transform duration-200 ease-out',
          'lg:relative lg:z-auto lg:translate-x-0',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-line px-4">
          <div className="flex items-center gap-2.5">
            <Logo size={20} />
            <span className="text-[15px] font-medium tracking-tight">IntelliRoads</span>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon lg:hidden" aria-label="Close menu">
            <X size={16} />
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 px-2 py-3" aria-label="Main">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                clsx(
                  'flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] transition-colors',
                  isActive ? 'bg-subtle font-medium text-ink' : 'text-muted hover:bg-subtle/70 hover:text-ink',
                )
              }
            >
              <Icon size={16} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="space-y-1 border-t border-line px-4 py-3">
          <StatusIndicator status={indicator} label={statusLabel} size="sm" />
          {kpis && (
            <p
              className="pl-3.5 text-2xs text-faint"
              title={
                kpis.data_source === 'LIVE'
                  ? 'Data comes from a connected SUMO / TraCI simulation.'
                  : 'SUMO is not connected: showing synthetic mock data.'
              }
            >
              {kpis.data_source === 'LIVE' ? 'SUMO simulation' : 'Mock data'}
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
