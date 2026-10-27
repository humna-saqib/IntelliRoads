import React, { useState, useRef } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import { useChartTheme } from '../../theme/chartTheme';
import Card from '../ui/Card';
import type { IntersectionData, VehicleData } from '../../types/traffic';

const JUNCTION_SHORT_NAMES: Record<string, string> = {
  junctionA: 'Northwest Square',
  junctionB: 'Northeast Plaza',
  junctionC: 'Southeast Gateway',
  junctionD: 'Southwest Crossing',
};

// 2x2 grid in SVG space (400 x 400)
const JUNCTION_COORDS: Record<string, { x: number; y: number }> = {
  junctionA: { x: 120, y: 120 },
  junctionB: { x: 280, y: 120 },
  junctionC: { x: 280, y: 280 },
  junctionD: { x: 120, y: 280 },
};

const SIGNAL_FILL: Record<string, string> = {
  GREEN: 'fill-sig-green',
  YELLOW: 'fill-sig-yellow',
  RED: 'fill-sig-red',
};

/** Density thresholds (veh/km): under 20 free flow, 20 to 40 congested, over 40 severe. */
const densityState = (density: number) =>
  density < 20 ? { stroke: 'stroke-ok', label: 'Free flow', tone: 'text-ok' } :
  density < 40 ? { stroke: 'stroke-warn', label: 'Congested', tone: 'text-warn' } :
  { stroke: 'stroke-bad', label: 'Severe', tone: 'text-bad' };

const VEHICLE_TYPES = ['car', 'motorcycle', 'bus', 'emergency'] as const;

export default function IntersectionMap() {
  const { intersections, vehicles } = useTraffic();
  const c = useChartTheme();
  const [hovered, setHovered] = useState<IntersectionData | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  const vehicleColor = (type: string) => {
    const i = VEHICLE_TYPES.indexOf(type?.toLowerCase() as (typeof VEHICLE_TYPES)[number]);
    return i >= 0 ? c.series[i] : c.axis;
  };

  const handleHover = (e: React.MouseEvent, junction: IntersectionData) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setHovered(junction);
    setTooltipPos({
      x: Math.min(Math.max(e.clientX - rect.left + 15, 10), rect.width - 170),
      y: Math.min(Math.max(e.clientY - rect.top + 15, 10), rect.height - 130),
    });
  };

  // SUMO coordinates to SVG space, with a small per-vehicle offset so the two directions stay apart
  const vehicleCoords = (v: VehicleData) => {
    const posX = typeof v.position_x === 'number' ? v.position_x : 0;
    const posY = typeof v.position_y === 'number' ? v.position_y : 0;

    let x = Math.min(Math.max((posX + 500) * 0.4, 5), 395);
    let y = Math.min(Math.max((500 - posY) * 0.4, 5), 395);

    const lane = (v.lane_id || '').toLowerCase();
    const offset = v.vehicle_id.charCodeAt(v.vehicle_id.length - 1) % 2 === 0 ? 3 : -3;
    if (lane.includes('a') || lane.includes('d')) y += offset;
    else if (lane.includes('b') || lane.includes('c')) x += offset;
    return { x, y };
  };

  return (
    <Card title="Network map" subtitle="Live view of the four junctions and the vehicles between them">
      <div ref={containerRef} className="relative mx-auto aspect-square max-w-[440px] overflow-hidden rounded-md border border-line bg-page">
        <svg viewBox="0 0 400 400" className="h-full w-full" role="img" aria-label="Road network with four signalised junctions">
          {/* roads */}
          {[120, 280].map((p) => (
            <g key={p}>
              <line x1="0" y1={p} x2="400" y2={p} className="stroke-line" strokeWidth="22" />
              <line x1="0" y1={p} x2="400" y2={p} className="stroke-surface" strokeWidth="1" strokeDasharray="6 6" />
              <line x1={p} y1="0" x2={p} y2="400" className="stroke-line" strokeWidth="22" />
              <line x1={p} y1="0" x2={p} y2="400" className="stroke-surface" strokeWidth="1" strokeDasharray="6 6" />
            </g>
          ))}

          {/* junctions */}
          {intersections.map((junction) => {
            const coords = JUNCTION_COORDS[junction.id];
            if (!coords) return null;
            const state = densityState(junction.density);
            return (
              <g
                key={junction.id}
                className="cursor-pointer"
                onMouseEnter={(e) => handleHover(e, junction)}
                onMouseMove={(e) => handleHover(e, junction)}
                onMouseLeave={() => setHovered(null)}
                onClick={(e) => handleHover(e, junction)}
              >
                <circle cx={coords.x} cy={coords.y} r="30" fill="transparent" />
                <circle cx={coords.x} cy={coords.y} r="15" className={`fill-surface ${state.stroke}`} strokeWidth={junction.density >= 40 ? 3 : 2} />
                <circle cx={coords.x} cy={coords.y} r="5.5" className={SIGNAL_FILL[junction.signal?.toUpperCase()] ?? 'fill-faint'} />
                <text x={coords.x} y={coords.y - 22} textAnchor="middle" fontSize="10" fontWeight="500" className="pointer-events-none select-none fill-muted">
                  {JUNCTION_SHORT_NAMES[junction.id] || junction.id}
                </text>
              </g>
            );
          })}

          {/* vehicles */}
          {vehicles.map((v) => {
            const p = vehicleCoords(v);
            return (
              <circle key={v.vehicle_id} cx={p.x} cy={p.y} r="3" fill={vehicleColor(v.vehicle_type)} className="pointer-events-none" style={{ transition: 'cx 0.9s linear, cy 0.9s linear' }}>
                <title>{`${v.vehicle_id} (${v.vehicle_type}): ${v.speed} m/s`}</title>
              </circle>
            );
          })}
        </svg>

        {hovered && (
          <div
            className="pointer-events-none absolute z-10 min-w-[160px] rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-sm"
            style={{ left: tooltipPos.x, top: tooltipPos.y }}
          >
            <p className="mb-1.5 font-medium text-ink">{hovered.name || JUNCTION_SHORT_NAMES[hovered.id] || hovered.id}</p>
            <dl className="space-y-1">
              <div className="flex justify-between gap-4"><dt className="text-muted">Signal</dt><dd className="text-ink">{hovered.signal.charAt(0) + hovered.signal.slice(1).toLowerCase()}</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-muted">Density</dt><dd className="font-mono tabular-nums text-ink">{Number(hovered.density || 0).toFixed(1)} veh/km</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-muted">State</dt><dd className={densityState(hovered.density).tone}>{densityState(hovered.density).label}</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-muted">Vehicles</dt><dd className="font-mono tabular-nums text-ink">{hovered.vehicle_count}</dd></div>
            </dl>
          </div>
        )}
      </div>

      <div className="mt-4 space-y-2 border-t border-line pt-3 text-xs text-faint">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          {VEHICLE_TYPES.map((t, i) => (
            <span key={t} className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ background: c.series[i] }} />
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border-2 border-ok" />Free flow, under 20 veh/km</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border-2 border-warn" />Congested, 20 to 40</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border-2 border-bad" />Severe, over 40</span>
        </div>
      </div>
    </Card>
  );
}
