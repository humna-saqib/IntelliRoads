import React, { useState } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import Card from '../ui/Card';
import Badge from '../ui/Badge';
import { Map, Info } from 'lucide-react';
import type { IntersectionData, VehicleData } from '../../types/traffic';

export default function IntersectionMap() {
  const { intersections, vehicles } = useTraffic();
  const [hoveredJunction, setHoveredJunction] = useState<IntersectionData | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // 2x2 Grid Junction Coordinates in SVG space (400x400)
  // Junction A (Top-Left): (120, 120)
  // Junction B (Top-Right): (280, 120)
  // Junction C (Bottom-Left): (120, 280)
  // Junction D (Bottom-Right): (280, 280)
  const junctionCoords: Record<string, { x: number; y: number }> = {
    junctionA: { x: 120, y: 120 },
    junctionB: { x: 280, y: 120 },
    junctionC: { x: 120, y: 280 },
    junctionD: { x: 280, y: 280 },
  };

  const getSignalColor = (signal: string) => {
    switch (signal?.toUpperCase()) {
      case 'GREEN': return '#22c55e';
      case 'YELLOW': return '#eab308';
      case 'RED': return '#ef4444';
      default: return '#64748b';
    }
  };

  const handleJunctionHover = (e: React.MouseEvent, junction: IntersectionData) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setHoveredJunction(junction);
    setTooltipPos({
      x: e.clientX - rect.left + 15,
      y: e.clientY - rect.top + 15,
    });
  };

  // Helper to map vehicle SUMO positions to SVG space
  const getVehicleCoords = (v: VehicleData) => {
    // Determine the road/lane the vehicle is on
    const lane = v.lane_id || '';
    
    // We place the vehicles along the paths between the boundaries and the junctions
    if (lane.includes('A')) {
      // Lane A leads to Junction A from the West (0, 120) -> (120, 120)
      const pct = Math.min(Math.max((v.position_x + 500) / 490, 0), 1);
      return { x: 10 + pct * 100, y: 120 + (v.vehicle_id.charCodeAt(0) % 2 === 0 ? 4 : -4) };
    }
    if (lane.includes('B')) {
      // Lane B leads to Junction B from the South (280, 400) -> (280, 120)
      const pct = Math.min(Math.max((v.position_y + 500) / 490, 0), 1);
      return { x: 280 + (v.vehicle_id.charCodeAt(0) % 2 === 0 ? 4 : -4), y: 390 - pct * 260 };
    }
    if (lane.includes('C')) {
      // Lane C leads to Junction C from the East (400, 280) -> (120, 280)
      const pct = Math.min(Math.max((500 - v.position_x) / 490, 0), 1);
      return { x: 390 - pct * 260, y: 280 + (v.vehicle_id.charCodeAt(0) % 2 === 0 ? 4 : -4) };
    }
    if (lane.includes('D')) {
      // Lane D leads to Junction D from the North (120, 0) -> (120, 280)
      const pct = Math.min(Math.max((500 - v.position_y) / 490, 0), 1);
      return { x: 120 + (v.vehicle_id.charCodeAt(0) % 2 === 0 ? 4 : -4), y: 10 + pct * 260 };
    }

    // Default random placement near center if unmapped
    return { x: 200, y: 200 };
  };

  const getVehicleColor = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'car': return '#3b82f6'; // Blue
      case 'motorcycle': return '#a855f7'; // Purple
      case 'bus': return '#f59e0b'; // Amber
      case 'truck': return '#ef4444'; // Red
      default: return '#94a3b8'; // Slate
    }
  };

  return (
    <Card
      title="Interactive Intersection Map"
      subtitle="Live traffic network simulation view"
      icon={<Map className="h-5 w-5 text-purple-500" />}
      className="relative"
    >
      <div className="relative border border-slate-800/80 rounded-lg overflow-hidden bg-slate-950/80 aspect-square max-w-[400px] mx-auto">
        {/* Dark Grid Background */}
        <div 
          className="absolute inset-0 opacity-[0.03]" 
          style={{
            backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />

        <svg viewBox="0 0 400 400" className="w-full h-full">
          {/* Roads (Thick Gray Paths) */}
          {/* Horizontal Road 1 (A-B) */}
          <line x1="0" y1="120" x2="400" y2="120" stroke="#334155" strokeWidth="24" strokeLinecap="round" />
          <line x1="0" y1="120" x2="400" y2="120" stroke="#0f172a" strokeWidth="1" strokeDasharray="6,6" />

          {/* Horizontal Road 2 (C-D) */}
          <line x1="0" y1="280" x2="400" y2="280" stroke="#334155" strokeWidth="24" strokeLinecap="round" />
          <line x1="0" y1="280" x2="400" y2="280" stroke="#0f172a" strokeWidth="1" strokeDasharray="6,6" />

          {/* Vertical Road 1 (A-C) */}
          <line x1="120" y1="0" x2="120" y2="400" stroke="#334155" strokeWidth="24" strokeLinecap="round" />
          <line x1="120" y1="0" x2="120" y2="400" stroke="#0f172a" strokeWidth="1" strokeDasharray="6,6" />

          {/* Vertical Road 2 (B-D) */}
          <line x1="280" y1="0" x2="280" y2="400" stroke="#334155" strokeWidth="24" strokeLinecap="round" />
          <line x1="280" y1="0" x2="280" y2="400" stroke="#0f172a" strokeWidth="1" strokeDasharray="6,6" />

          {/* Intersections (Junctions) */}
          {intersections.map((junction) => {
            const coords = junctionCoords[junction.id];
            if (!coords) return null;
            const signalColor = getSignalColor(junction.signal);
            const isCongested = junction.congestion_status === 'CONGESTED';

            return (
              <g key={junction.id}>
                {/* Congestion Pulse Ring */}
                {isCongested && (
                  <circle
                    cx={coords.x}
                    cy={coords.y}
                    r="22"
                    fill="none"
                    stroke="#ef4444"
                    strokeWidth="2"
                    className="animate-ping"
                    style={{ transformOrigin: `${coords.x}px ${coords.y}px` }}
                  />
                )}

                {/* Base Intersection Ring */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r="16"
                  fill="#1e293b"
                  stroke={isCongested ? '#ef4444' : '#475569'}
                  strokeWidth="2"
                  className="cursor-pointer hover:fill-slate-800 transition-colors"
                  onMouseMove={(e) => handleJunctionHover(e, junction)}
                  onMouseLeave={() => setHoveredJunction(null)}
                />

                {/* Signal Light Center */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r="6"
                  fill={signalColor}
                  className="pointer-events-none"
                  style={{
                    filter: `drop-shadow(0 0 6px ${signalColor})`
                  }}
                />

                {/* Text Label */}
                <text
                  x={coords.x}
                  y={coords.y - 20}
                  fill="#94a3b8"
                  fontSize="10"
                  fontWeight="bold"
                  textAnchor="middle"
                  className="pointer-events-none select-none"
                >
                  {junction.id.replace('junction', 'Junction ')}
                </text>
              </g>
            );
          })}

          {/* Live Vehicle Dots */}
          {vehicles.map((v) => {
            const coords = getVehicleCoords(v);
            const color = getVehicleColor(v.vehicle_type);
            return (
              <circle
                key={v.vehicle_id}
                cx={coords.x}
                cy={coords.y}
                r="4"
                fill={color}
                style={{
                  filter: `drop-shadow(0 0 2px ${color})`,
                  transition: 'cx 0.9s linear, cy 0.9s linear'
                }}
              >
                <title>{`${v.vehicle_id} (${v.vehicle_type}): ${v.speed} m/s`}</title>
              </circle>
            );
          })}
        </svg>

        {/* Hover Tooltip Overlay */}
        {hoveredJunction && (
          <div
            className="absolute z-10 p-3 rounded-lg border border-slate-700 bg-slate-900/95 backdrop-blur-sm text-xs space-y-1 text-slate-200 pointer-events-none"
            style={{ left: tooltipPos.x, top: tooltipPos.y }}
          >
            <div className="flex items-center gap-1.5 font-bold text-slate-100">
              <Info className="h-3.5 w-3.5 text-purple-400" />
              <span>{hoveredJunction.name}</span>
            </div>
            <div className="border-t border-slate-800 my-1" />
            <div>
              Signal: <span className="font-semibold" style={{ color: getSignalColor(hoveredJunction.signal) }}>{hoveredJunction.signal}</span>
            </div>
            <div>
              Status: <span className={`font-semibold ${hoveredJunction.congestion_status === 'CONGESTED' ? 'text-red-400' : 'text-green-400'}`}>{hoveredJunction.congestion_status}</span>
            </div>
            <div>
              Vehicles: <span className="font-semibold text-slate-100">{hoveredJunction.vehicle_count}</span>
            </div>
            <div>
              Density: <span className="font-semibold text-slate-100">{hoveredJunction.density} veh/km</span>
            </div>
          </div>
        )}
      </div>

      {/* Map Legend */}
      <div className="flex flex-wrap items-center justify-center gap-4 mt-4 text-[10px] text-slate-400 border-t border-slate-850 pt-3">
        <div className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#3b82f6]" />
          <span>Car</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#a855f7]" />
          <span>Motorcycle</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#f59e0b]" />
          <span>Bus</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#ef4444]" />
          <span>Truck</span>
        </div>
        <div className="w-full md:w-auto h-0.5 md:h-3 border-l border-slate-800 hidden md:block" />
        <div className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full border border-slate-700 bg-[#22c55e]" />
          <span>Green Phase</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full border border-slate-700 bg-[#ef4444]" />
          <span>Red Phase</span>
        </div>
      </div>
    </Card>
  );
}
