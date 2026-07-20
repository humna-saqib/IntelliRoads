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

  // Map density to color-coded status
  // Based on thresholds: Low (<20), Medium (20-40), High (>40) v/km
  const getDensityColor = (density: number) => {
    if (density < 20) {
      return {
        ring: '#22c55e',      // Green - Free flow
        glow: 'rgba(34, 197, 94, 0.3)',
        label: 'Free Flow'
      };
    } else if (density < 40) {
      return {
        ring: '#f59e0b',      // Orange - Congested
        glow: 'rgba(245, 158, 11, 0.3)',
        label: 'Congested'
      };
    } else {
      return {
        ring: '#ef4444',      // Red - Severely congested
        glow: 'rgba(239, 68, 68, 0.3)',
        label: 'Severe'
      };
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
          {/* Define gradients for all density levels */}
          <defs>
            <style>{`
              @keyframes density-pulse {
                0%, 100% { opacity: 0.5; }
                50% { opacity: 1; }
              }
              .pulse-animation { animation: density-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
            `}</style>
            <radialGradient id="glow-green" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#22c55e" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="glow-orange" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="glow-red" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#ef4444" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
            </radialGradient>
          </defs>
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
            const densityInfo = getDensityColor(junction.density);
            const isHighDensity = junction.density >= 40;

            // Select the appropriate gradient ID based on density
            let gradientId = 'glow-green';
            if (junction.density < 20) {
              gradientId = 'glow-green';
            } else if (junction.density < 40) {
              gradientId = 'glow-orange';
            } else {
              gradientId = 'glow-red';
            }

            return (
              <g key={junction.id}>
                {/* Background Glow Circle */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r="26"
                  fill={`url(#${gradientId})`}
                  className="pointer-events-none"
                />

                {/* Animated Pulse Ring (High density only) */}
                {isHighDensity && (
                  <circle
                    cx={coords.x}
                    cy={coords.y}
                    r="22"
                    fill="none"
                    stroke={densityInfo.ring}
                    strokeWidth="2"
                    className="pulse-animation"
                    opacity="0.5"
                    style={{ transformOrigin: `${coords.x}px ${coords.y}px` }}
                  />
                )}

                {/* Base Intersection Circle - Color coded by density */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r="16"
                  fill="#1e293b"
                  stroke={densityInfo.ring}
                  strokeWidth="2.5"
                  className="cursor-pointer hover:fill-slate-800 transition-all duration-300"
                  onMouseMove={(e) => handleJunctionHover(e, junction)}
                  onMouseLeave={() => setHoveredJunction(null)}
                  style={{
                    boxShadow: `0 0 8px ${densityInfo.ring}40`
                  }}
                />

                {/* Signal Light Center */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r="6"
                  fill={signalColor}
                  className="pointer-events-none transition-colors duration-300"
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
              Density: <span className="font-semibold text-slate-100">{hoveredJunction.density.toFixed(1)} veh/km</span>
            </div>
            <div>
              Status: <span className={`font-semibold px-2 py-0.5 rounded text-xs ${
                hoveredJunction.density < 20 
                  ? 'bg-green-500/20 text-green-300' 
                  : hoveredJunction.density < 40 
                    ? 'bg-orange-500/20 text-orange-300'
                    : 'bg-red-500/20 text-red-300'
              }`}>
                {hoveredJunction.density < 20 ? '✓ Free Flow' : hoveredJunction.density < 40 ? '⚠ Congested' : '✕ Severe'}
              </span>
            </div>
            <div>
              Vehicles: <span className="font-semibold text-slate-100">{hoveredJunction.vehicle_count}</span>
            </div>
          </div>
        )}
      </div>

      {/* Map Legend */}
      <div className="flex flex-wrap items-center justify-center gap-3 mt-4 text-[10px] text-slate-400 border-t border-slate-850 pt-3">
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

        <div className="w-full h-px bg-slate-700/50 my-1" />

        <div className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-[#22c55e] bg-slate-900" />
          <span>Green - Free Flow (&lt;20 v/km)</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-[#f59e0b] bg-slate-900" />
          <span>Orange - Congested (20-40 v/km)</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-[#ef4444] bg-slate-900" />
          <span>Red - Severe (&gt;40 v/km)</span>
        </div>
      </div>
    </Card>
  );
}
