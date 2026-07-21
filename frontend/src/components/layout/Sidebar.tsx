import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Map, BarChart3, FileText, Zap, X } from 'lucide-react';
import { useTraffic } from '../../context/TrafficContext';
import StatusIndicator from '../ui/StatusIndicator';
import clsx from 'clsx';

const navItems = [
  { to: '/',          label: 'Dashboard',    icon: LayoutDashboard },
  { to: '/map',       label: 'Traffic Map',  icon: Map             },
  { to: '/analytics', label: 'Analytics',    icon: BarChart3       },
  { to: '/reports',   label: 'Reports',      icon: FileText        },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { connectionStatus, kpis } = useTraffic();

  const statusLabel =
    connectionStatus === 'connected'    ? 'Live Feed'    :
    connectionStatus === 'connecting'   ? 'Connecting…'  :
    connectionStatus === 'disconnected' ? 'Offline'      :
    'Error';

  const indicatorStatus =
    connectionStatus === 'connected'    ? 'online'     :
    connectionStatus === 'connecting'   ? 'connecting' :
    connectionStatus === 'error'        ? 'warning'    :
    'offline';

  return (
    <>
      {/* Mobile backdrop overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={clsx(
          'fixed top-0 left-0 h-full z-40 flex flex-col w-64 flex-shrink-0',
          'bg-slate-950/95 backdrop-blur-md border-r border-white/5',
          'transition-transform duration-300 ease-in-out',
          // Mobile: slide in/out; Desktop: always visible
          'lg:relative lg:translate-x-0 lg:z-auto',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {/* Logo */}
        <div className="flex items-center justify-between px-6 py-6 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-slate-800 to-zinc-900 border border-zinc-700/50 shadow-card">
              <Zap size={20} className="text-accent-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">IntelliRoads</h1>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest font-medium">AI Traffic Control</p>
            </div>
          </div>
          {/* Close button — mobile only */}
          <button
            onClick={onClose}
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200',
                  isActive
                    ? 'bg-white/5 text-white border border-white/10 shadow-[0_0_12px_rgba(255,255,255,0.03)]'
                    : 'text-slate-400 hover:text-white hover:bg-white/5',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    size={18}
                    className={clsx(isActive ? 'text-accent-400' : 'text-slate-500')}
                  />
                  {label}
                  {isActive && (
                    <div className="ml-auto w-1.5 h-1.5 rounded-full bg-accent-500 shadow-[0_0_6px_rgba(245,158,11,0.6)]" />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Stats summary */}
        {kpis && (
          <div className="mx-3 mb-3 rounded-xl bg-white/3 border border-white/5 p-3">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2 font-medium">Live Stats</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="text-center">
                <p className="text-xl font-bold text-white">{kpis.total_vehicles}</p>
                <p className="text-[10px] text-slate-500">Vehicles</p>
              </div>
              <div className="text-center">
                <p className="text-xl font-bold text-warning-400">{kpis.active_alerts}</p>
                <p className="text-[10px] text-slate-500">Alerts</p>
              </div>
            </div>
          </div>
        )}

        {/* Connection status */}
        <div className="border-t border-white/5 px-4 py-4">
          <StatusIndicator status={indicatorStatus} label={statusLabel} size="sm" />
          <p className="text-[10px] text-slate-600 mt-1.5 pl-5">
            {connectionStatus === 'connected' ? 'WebSocket active' : 'Polling REST API'}
          </p>
          {kpis && (
            <p
              className={clsx(
                'text-[10px] mt-2 pl-5 font-semibold uppercase tracking-widest',
                kpis.data_source === 'LIVE' ? 'text-success-400' : 'text-amber-400',
              )}
              title={
                kpis.data_source === 'LIVE'
                  ? 'Data is coming from a connected SUMO/TraCI simulation.'
                  : 'SUMO is not connected — showing synthetic mock data.'
              }
            >
              {kpis.data_source === 'LIVE' ? '● Live SUMO Data' : '● Mock Data'}
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
