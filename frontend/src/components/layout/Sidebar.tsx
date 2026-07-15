import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Map, BarChart3, Zap } from 'lucide-react';
import { useTraffic } from '../../context/TrafficContext';
import StatusIndicator from '../ui/StatusIndicator';
import clsx from 'clsx';

const navItems = [
  { to: '/',          label: 'Dashboard',    icon: LayoutDashboard },
  { to: '/map',       label: 'Traffic Map',  icon: Map             },
  { to: '/analytics', label: 'Analytics',    icon: BarChart3       },
];

export default function Sidebar() {
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
    <aside className="flex h-full w-64 flex-shrink-0 flex-col bg-slate-950/90 backdrop-blur-md border-r border-white/5">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-6 border-b border-white/5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary-600 to-accent-500 shadow-glow-purple">
          <Zap size={20} className="text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-white tracking-tight">IntelliRoads</h1>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-medium">AI Traffic Control</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-gradient-to-r from-primary-600/30 to-accent-500/10 text-white border border-primary-500/30 shadow-[0_0_12px_rgba(124,58,237,0.2)]'
                  : 'text-slate-400 hover:text-white hover:bg-white/5',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={18}
                  className={clsx(isActive ? 'text-primary-400' : 'text-slate-500')}
                />
                {label}
                {isActive && (
                  <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary-400 shadow-[0_0_6px_rgba(167,139,250,0.8)]" />
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
      </div>
    </aside>
  );
}
