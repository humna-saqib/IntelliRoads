import React, { useState, useRef, useEffect } from 'react';
import { useTraffic } from '../../context/TrafficContext';
import { useChartTheme } from '../../theme/chartTheme';
import Card from '../ui/Card';
import type { IntersectionData, VehicleData } from '../../types/traffic';
import { getJunctionName, formatSignalReason } from '../../constants/plainWords';
import { X, Clock, Sparkles, Car, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import clsx from 'clsx';

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

const VEHICLE_TYPES = ['car', 'bus', 'truck', 'emergency', 'motorcycle'] as const;

function VehicleIconSvg({ type, color }: { type: string; color: string }) {
  const norm = (type || 'car').toLowerCase();
  if (norm.includes('bus')) {
    return (
      <g>
        <rect x="-6" y="-3.5" width="12" height="7" rx="1.5" fill={color} />
        <rect x="-4" y="-2" width="6" height="4" rx="0.5" fill="#fff" fillOpacity="0.75" />
        <line x1="3.5" y1="-2.5" x2="3.5" y2="2.5" stroke="#fff" strokeWidth="1" />
      </g>
    );
  }
  if (norm.includes('truck')) {
    return (
      <g>
        <rect x="-7" y="-3.5" width="8" height="7" rx="1" fill={color} fillOpacity="0.9" />
        <rect x="2" y="-3" width="4.5" height="6" rx="1" fill={color} />
        <line x1="1" y1="-2" x2="1" y2="2" stroke="#fff" strokeWidth="0.8" />
      </g>
    );
  }
  if (norm.includes('emergency')) {
    return (
      <g>
        <rect x="-5.5" y="-3.5" width="11" height="7" rx="1.5" fill={color} stroke="#ef4444" strokeWidth="1" />
        <rect x="-2" y="-1.5" width="4" height="3" rx="0.5" fill="#fff" fillOpacity="0.8" />
        <circle cx="0" cy="0" r="1.5" fill="#ef4444" className="animate-pulse" />
      </g>
    );
  }
  if (norm.includes('motorcycle') || norm.includes('bike')) {
    return (
      <g>
        <circle cx="-3" cy="0" r="1.5" fill={color} />
        <circle cx="3" cy="0" r="1.5" fill={color} />
        <line x1="-3" y1="0" x2="3" y2="0" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      </g>
    );
  }
  // Default: car
  return (
    <g>
      <rect x="-4.5" y="-2.5" width="9" height="5" rx="1.5" fill={color} />
      <rect x="-2" y="-1.5" width="4" height="3" rx="1" fill="#fff" fillOpacity="0.75" />
    </g>
  );
}

interface IntersectionMapProps {
  selectedJunctionId?: string | null;
  onSelectJunction?: (id: string | null) => void;
}

export default function IntersectionMap({ selectedJunctionId, onSelectJunction }: IntersectionMapProps = {}) {
  const { intersections, vehicles, signals } = useTraffic();
  const c = useChartTheme();
  const [hovered, setHovered] = useState<IntersectionData | null>(null);
  const [selectedJunction, setSelectedJunction] = useState<IntersectionData | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [signalCountdowns, setSignalCountdowns] = useState<Record<string, number>>({});
  const [zoom, setZoom] = useState<number>(1);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleZoomIn = () => setZoom((z) => Math.min(2.5, Math.round((z + 0.25) * 100) / 100));
  const handleZoomOut = () => setZoom((z) => Math.max(1, Math.round((z - 0.25) * 100) / 100));
  const handleResetZoom = () => setZoom(1);

  const viewWidth = 400 / zoom;
  const viewHeight = 400 / zoom;
  const minX = 200 - viewWidth / 2;
  const minY = 200 - viewHeight / 2;

  useEffect(() => {
    if (selectedJunctionId !== undefined) {
      const match = intersections.find((j) => j.id === selectedJunctionId) ?? null;
      setSelectedJunction(match);
    }
  }, [selectedJunctionId, intersections]);

  // Synchronize and countdown signal duration per junction
  useEffect(() => {
    if (!signals?.signals) return;
    const initial: Record<string, number> = {};
    for (const s of signals.signals) {
      initial[s.junction_id] = s.duration_seconds ?? 0;
    }
    setSignalCountdowns(initial);

    const interval = setInterval(() => {
      setSignalCountdowns((prev) => {
        const next: Record<string, number> = {};
        for (const [k, v] of Object.entries(prev)) {
          next[k] = v > 0 ? v - 1 : 0;
        }
        return next;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [signals]);

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
        {/* Accessible Zoom and Reset Controls */}
        <div
          role="toolbar"
          aria-label="Map view zoom controls"
          className="absolute top-2 left-2 z-20 flex items-center gap-1 rounded-lg border border-line bg-surface/90 p-1 shadow-xs backdrop-blur-xs"
        >
          <button
            type="button"
            onClick={handleZoomIn}
            disabled={zoom >= 2.5}
            aria-label="Zoom in"
            title="Zoom in"
            className="btn btn-ghost btn-icon h-7 w-7 text-ink disabled:opacity-40"
          >
            <ZoomIn size={14} />
          </button>
          <button
            type="button"
            onClick={handleZoomOut}
            disabled={zoom <= 1}
            aria-label="Zoom out"
            title="Zoom out"
            className="btn btn-ghost btn-icon h-7 w-7 text-ink disabled:opacity-40"
          >
            <ZoomOut size={14} />
          </button>
          <button
            type="button"
            onClick={handleResetZoom}
            disabled={zoom === 1}
            aria-label="Reset view"
            title="Reset view to 100%"
            className="btn btn-ghost h-7 px-2 text-2xs font-medium text-ink disabled:opacity-40 flex items-center gap-1"
          >
            <RotateCcw size={12} />
            <span>Reset view</span>
          </button>
          <span className="px-1 font-mono text-2xs text-faint tabular-nums" aria-hidden="true">
            {Math.round(zoom * 100)}%
          </span>
        </div>

        <svg
          viewBox={`${minX} ${minY} ${viewWidth} ${viewHeight}`}
          className="h-full w-full transition-all duration-300 ease-out"
          role="img"
          aria-label="Road network with four signalised junctions"
        >
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
            const isHeavy = junction.density >= 40 || junction.congestion_status === 'CONGESTED';
            const isModerate = !isHeavy && junction.density >= 20;
            const isSelected = selectedJunction?.id === junction.id;
            const trafficLevelLabel = isHeavy ? 'Heavy traffic' : isModerate ? 'Moderate traffic' : 'Light traffic';

            return (
              <g
                key={junction.id}
                role="button"
                tabIndex={0}
                aria-label={`${getJunctionName(junction.id)}: ${trafficLevelLabel}, light is ${junction.signal.toLowerCase()}`}
                className="cursor-pointer focus:outline-hidden"
                onMouseEnter={(e) => handleHover(e, junction)}
                onMouseMove={(e) => handleHover(e, junction)}
                onMouseLeave={() => setHovered(null)}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedJunction(junction);
                  onSelectJunction?.(junction.id);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedJunction(junction);
                    onSelectJunction?.(junction.id);
                  }
                }}
              >
                {/* Hit target */}
                <circle cx={coords.x} cy={coords.y} r="32" fill="transparent" />

                {/* Selection ring */}
                {isSelected && (
                  <circle
                    cx={coords.x}
                    cy={coords.y}
                    r="25"
                    fill="none"
                    className="stroke-brand animate-pulse"
                    strokeWidth="2"
                    strokeDasharray="4 2"
                  />
                )}

                {/* Colour-blind-safe shapes: Square = Heavy, Triangle = Moderate, Circle = Light */}
                {isHeavy ? (
                  <rect
                    x={coords.x - 15}
                    y={coords.y - 15}
                    width="30"
                    height="30"
                    rx="4"
                    className="fill-surface stroke-bad"
                    strokeWidth="3"
                  />
                ) : isModerate ? (
                  <polygon
                    points={`${coords.x},${coords.y - 18} ${coords.x - 17},${coords.y + 13} ${coords.x + 17},${coords.y + 13}`}
                    className="fill-surface stroke-warn"
                    strokeWidth="2.5"
                    strokeLinejoin="round"
                  />
                ) : (
                  <circle
                    cx={coords.x}
                    cy={coords.y}
                    r="15"
                    className="fill-surface stroke-ok"
                    strokeWidth="2.5"
                  />
                )}

                {/* Central Traffic Signal Light indicator */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r="5.5"
                  className={SIGNAL_FILL[junction.signal?.toUpperCase()] ?? 'fill-faint'}
                  stroke="currentColor"
                  strokeWidth="1"
                />

                <text
                  x={coords.x}
                  y={coords.y - 23}
                  textAnchor="middle"
                  fontSize="10"
                  fontWeight="600"
                  className="pointer-events-none select-none fill-ink"
                >
                  {getJunctionName(junction.id)}
                </text>
              </g>
            );
          })}

          {/* vehicles */}
          {vehicles.map((v) => {
            const p = vehicleCoords(v);
            const color = vehicleColor(v.vehicle_type);
            const speedKmh = Math.round(v.speed * 3.6);
            return (
              <g
                key={v.vehicle_id}
                transform={`translate(${p.x}, ${p.y})`}
                className="pointer-events-none"
                style={{ transition: 'transform 0.9s linear' }}
              >
                <title>{`${v.vehicle_id} (${v.vehicle_type}): ${speedKmh} km/h`}</title>
                <VehicleIconSvg type={v.vehicle_type} color={color} />
              </g>
            );
          })}
        </svg>

        {hovered && (() => {
          const name = getJunctionName(hovered.id);
          const sig = signals?.signals?.find((s) => s.junction_id === hovered.id);
          const secondsLeft = signalCountdowns[hovered.id] ?? sig?.duration_seconds ?? 0;
          const lightColor = hovered.signal.toLowerCase();
          const lightText = secondsLeft > 0 ? `light is ${lightColor} for ${Math.round(secondsLeft)} more seconds` : `light is ${lightColor}`;
          const trafficLevel =
            hovered.congestion_status === 'CONGESTED' || hovered.density >= 40
              ? 'heavy traffic'
              : hovered.density >= 20
              ? 'moderate traffic'
              : 'light traffic';

          return (
            <div
              className="pointer-events-none absolute z-20 max-w-[260px] rounded-lg border border-line bg-surface/95 p-3 text-xs shadow-md backdrop-blur-xs"
              style={{ left: tooltipPos.x, top: tooltipPos.y }}
            >
              <p className="font-semibold text-ink leading-snug">
                {name}: <span className="font-normal text-muted">{trafficLevel}, {lightText}</span>
              </p>
              <dl className="mt-2 space-y-1 border-t border-line/60 pt-2 text-2xs text-muted">
                <div className="flex justify-between gap-3">
                  <dt>Vehicles</dt>
                  <dd className="font-medium text-ink">{hovered.vehicle_count} active</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Crowdedness</dt>
                  <dd className="font-medium text-ink">{Number(hovered.density || 0).toFixed(1)} cars/km</dd>
                </div>
              </dl>
            </div>
          );
        })()}

        {/* Click-to-inspect Side Panel */}
        {selectedJunction && (() => {
          const name = getJunctionName(selectedJunction.id);
          const sig = signals?.signals?.find((s) => s.junction_id === selectedJunction.id);
          const secondsLeft = signalCountdowns[selectedJunction.id] ?? sig?.duration_seconds ?? 0;
          const lightColorLabel =
            selectedJunction.signal === 'GREEN'
              ? 'Green light (traffic is moving)'
              : selectedJunction.signal === 'YELLOW'
              ? 'Yellow light (prepare to stop)'
              : 'Red light (stopped at intersection)';
          const trafficLevel =
            selectedJunction.congestion_status === 'CONGESTED' || selectedJunction.density >= 40
              ? { text: 'Heavy traffic', tone: 'text-bad bg-bad/10 border-bad/20' }
              : selectedJunction.density >= 20
              ? { text: 'Moderate traffic', tone: 'text-warn bg-warn/10 border-warn/20' }
              : { text: 'Light traffic', tone: 'text-ok bg-ok/10 border-ok/20' };

          const actionReason = formatSignalReason(sig?.reason);

          return (
            <div
              className="absolute inset-y-0 right-0 z-30 w-full sm:w-72 border-l border-line bg-surface/98 p-4 shadow-xl backdrop-blur-md flex flex-col justify-between overflow-y-auto animate-in slide-in-from-right duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div>
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <div>
                    <span className="text-2xs font-semibold uppercase tracking-wider text-faint">Junction details</span>
                    <h4 className="text-sm font-semibold text-ink">{name}</h4>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedJunction(null);
                      onSelectJunction?.(null);
                    }}
                    className="btn btn-ghost btn-icon h-7 w-7 text-muted hover:text-ink"
                    aria-label="Close side panel"
                  >
                    <X size={15} />
                  </button>
                </div>

                <div className="mt-3 space-y-3">
                  {/* Traffic level in words */}
                  <div>
                    <span className="text-2xs text-faint uppercase font-medium">Traffic level</span>
                    <div className="mt-1">
                      <span className={clsx('inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-semibold', trafficLevel.tone)}>
                        {trafficLevel.text}
                      </span>
                    </div>
                  </div>

                  {/* Light colour in words & countdown */}
                  <div className="rounded-lg border border-line bg-subtle/50 p-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-2xs text-faint uppercase font-medium">Signal status</span>
                      <span className="flex items-center gap-1 text-xs font-semibold tabular-nums text-ink">
                        <Clock size={12} className="text-brand" />
                        {Math.round(secondsLeft)}s remaining
                      </span>
                    </div>
                    <p className="mt-1 text-xs font-medium text-ink flex items-center gap-2">
                      <span className={clsx('h-2.5 w-2.5 rounded-full', SIGNAL_FILL[selectedJunction.signal?.toUpperCase()] ?? 'fill-faint')} />
                      {lightColorLabel}
                    </p>
                    <p className="mt-0.5 text-2xs text-muted">
                      Countdown: {Math.round(secondsLeft)} more seconds
                    </p>
                  </div>

                  {/* Number of vehicles */}
                  <div className="flex items-center justify-between rounded-lg border border-line bg-subtle/30 px-3 py-2 text-xs">
                    <span className="text-muted flex items-center gap-1.5">
                      <Car size={13} className="text-faint" />
                      Number of vehicles
                    </span>
                    <span className="font-semibold text-ink">{selectedJunction.vehicle_count} active</span>
                  </div>

                  {/* What the system just did */}
                  <div className="rounded-lg border border-line bg-subtle/40 p-3">
                    <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-brand">
                      <Sparkles size={12} />
                      <span>What the system just did</span>
                    </div>
                    <p className="mt-1.5 text-xs leading-relaxed text-ink font-medium">
                      {actionReason}
                    </p>
                  </div>
                </div>
              </div>

              <div className="border-t border-line pt-2.5 mt-3 text-2xs text-faint flex justify-between">
                <span>Density: {selectedJunction.density.toFixed(1)} cars/km</span>
                <span className="capitalize">{selectedJunction.congestion_status.toLowerCase()}</span>
              </div>
            </div>
          );
        })()}
      </div>

      <div className="mt-4 space-y-3 border-t border-line pt-3 text-xs">
        <div>
          <span className="font-semibold text-ink text-2xs uppercase tracking-wider">Traffic Flow & Junction Markers</span>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-muted">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-full border-2 border-ok bg-ok/20" />
              <span>Circle: Light traffic (flowing freely, under 20 cars/km)</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-0 w-0 border-x-[6px] border-b-[10px] border-x-transparent border-b-warn" />
              <span>Triangle: Moderate traffic (slowing down, 20 to 40 cars/km)</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-xs border-2 border-bad bg-bad/20" />
              <span>Square: Heavy traffic (crowded, over 40 cars/km)</span>
            </span>
          </div>
        </div>

        <div>
          <span className="font-semibold text-ink text-2xs uppercase tracking-wider">Traffic Light Colours</span>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-muted">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-sig-green shadow-[0_0_6px_rgba(34,197,94,0.6)]" />
              <span>Green: Go (traffic is moving)</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-sig-yellow shadow-[0_0_6px_rgba(234,179,8,0.6)]" />
              <span>Yellow: Prepare to stop</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-sig-red shadow-[0_0_6px_rgba(239,68,68,0.6)]" />
              <span>Red: Stop (waiting for light)</span>
            </span>
          </div>
        </div>

        <div>
          <span className="font-semibold text-ink text-2xs uppercase tracking-wider">Vehicle Types</span>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-muted">
            {VEHICLE_TYPES.map((t, i) => (
              <span key={t} className="flex items-center gap-1.5">
                <svg width="15" height="11" viewBox="-7 -4 14 8" className="inline-block flex-shrink-0">
                  <VehicleIconSvg type={t} color={c.series[i % c.series.length]} />
                </svg>
                <span>{t === 'emergency' ? 'Emergency vehicle' : t.charAt(0).toUpperCase() + t.slice(1)}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
