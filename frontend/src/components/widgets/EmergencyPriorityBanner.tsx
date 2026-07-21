import React from 'react';
import { useTraffic } from '../../context/TrafficContext';
import { Siren, ShieldAlert } from 'lucide-react';
import clsx from 'clsx';

export default function EmergencyPriorityBanner() {
  const { emergency } = useTraffic();

  if (!emergency || !emergency.active_vehicles || emergency.active_vehicles.length === 0) {
    return null;
  }

  // Get first active vehicle (usually there is one at a time)
  const activeVehicle = emergency.active_vehicles[0];

  const junctionNames: Record<string, string> = {
    junctionA: 'Northwest Square',
    junctionB: 'Northeast Plaza',
    junctionC: 'Southeast Gateway',
    junctionD: 'Southwest Crossing'
  };

  const location = activeVehicle.junction_id 
    ? (junctionNames[activeVehicle.junction_id] || activeVehicle.junction_id)
    : 'Monitored Intersection';

  return (
    <div className={clsx(
      'relative overflow-hidden w-full p-4.5 rounded-2xl border border-blue-500/30 backdrop-blur-md',
      'bg-gradient-to-r from-blue-950/80 via-blue-900/40 to-indigo-950/80',
      'shadow-[0_0_24px_rgba(37,99,235,0.25)] animate-pulse-slow'
    )}>
      {/* Dynamic left ambient glow */}
      <div className="absolute top-[-50%] left-[-10%] w-[30%] aspect-square rounded-full bg-blue-500/20 blur-[50px] pointer-events-none" />
      
      <div className="relative z-10 flex items-center justify-between flex-wrap sm:flex-nowrap gap-4">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/20 text-blue-400 border border-blue-500/30 shadow-[0_0_12px_rgba(59,130,246,0.3)]">
            <Siren size={20} className="animate-bounce" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-widest text-blue-400">
                Priority Override Active
              </span>
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />
            </div>
            <h2 className="text-sm font-bold text-white mt-0.5">
              Emergency {activeVehicle.vehicle_type} (ID: {activeVehicle.vehicle_id}) approaching {location}
            </h2>
            <p className="text-[10px] text-slate-300/80 mt-0.5">
              Signal Priority control is routing a cleared green corridor along {activeVehicle.lane_id.replace('lane_', '').replace('_in', '')}.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-center sm:self-auto ml-auto sm:ml-0 bg-blue-500/10 border border-blue-500/20 px-3 py-1.5 rounded-lg text-[10px] font-semibold text-blue-300 font-mono">
          <ShieldAlert size={12} />
          SPEED: {(activeVehicle.speed * 3.6).toFixed(0)} km/h
        </div>
      </div>
    </div>
  );
}
