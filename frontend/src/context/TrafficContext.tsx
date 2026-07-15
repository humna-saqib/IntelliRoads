import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import type {
  ClassificationData,
  CongestionResponse,
  DensityResponse,
  IntersectionData,
  KPIData,
  SignalResponse,
  TrafficSnapshot,
  VehicleData,
} from '../types/traffic';
import { fetchAllData } from '../services/api';
import { TrafficWebSocket } from '../services/websocket';

function getWebSocketUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${path}`;
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface TrafficContextType {
  vehicles:         VehicleData[];
  classification:   ClassificationData | null;
  density:          DensityResponse | null;
  congestion:       CongestionResponse | null;
  signals:          SignalResponse | null;
  kpis:             KPIData | null;
  intersections:    IntersectionData[];
  isConnected:      boolean;
  isLoading:        boolean;
  lastUpdate:       number | null;
  connectionStatus: ConnectionStatus;
}

const defaultClassification: ClassificationData = {
  car: 0, motorcycle: 0, bus: 0, truck: 0,
  percentages: {}, most_common_type: 'unknown',
};

const TrafficContext = createContext<TrafficContextType>({
  vehicles:         [],
  classification:   null,
  density:          null,
  congestion:       null,
  signals:          null,
  kpis:             null,
  intersections:    [],
  isConnected:      false,
  isLoading:        true,
  lastUpdate:       null,
  connectionStatus: 'connecting',
});

export function TrafficProvider({ children }: { children: React.ReactNode }) {
  const [vehicles,         setVehicles]         = useState<VehicleData[]>([]);
  const [classification,   setClassification]   = useState<ClassificationData | null>(null);
  const [density,          setDensity]          = useState<DensityResponse | null>(null);
  const [congestion,       setCongestion]       = useState<CongestionResponse | null>(null);
  const [signals,          setSignals]          = useState<SignalResponse | null>(null);
  const [kpis,             setKPIs]             = useState<KPIData | null>(null);
  const [intersections,    setIntersections]    = useState<IntersectionData[]>([]);
  const [isConnected,      setIsConnected]      = useState(false);
  const [isLoading,        setIsLoading]        = useState(true);
  const [lastUpdate,       setLastUpdate]       = useState<number | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');

  const wsRef     = useRef<TrafficWebSocket | null>(null);
  const pollRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  const wsConnRef = useRef(false);

  const applySnapshot = useCallback((snap: TrafficSnapshot) => {
    if (snap.vehicles)      setVehicles(snap.vehicles as unknown as VehicleData[]);
    if (snap.classification) setClassification(snap.classification ?? defaultClassification);
    if (snap.density)        setDensity(snap.density);
    if (snap.congestion)     setCongestion(snap.congestion);
    if (snap.signals)        setSignals(snap.signals);
    if (snap.kpis)           setKPIs(snap.kpis);
    if (snap.intersections)  setIntersections(snap.intersections);
    setLastUpdate(Date.now());
    setIsLoading(false);
  }, []);

  const loadRest = useCallback(async () => {
    try {
      const data = await fetchAllData();
      setVehicles(data.vehicles.vehicles ?? []);
      setClassification(data.classification ?? defaultClassification);
      setDensity(data.density);
      setCongestion(data.congestion);
      setSignals(data.signals);
      setKPIs(data.kpis);
      setIntersections(data.intersections ?? []);
      setLastUpdate(Date.now());
      setIsLoading(false);
    } catch (err) {
      console.error('[TrafficContext] REST fetch error:', err);
      setConnectionStatus('error');
      setIsLoading(false);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(() => {
      if (!wsConnRef.current) {
        loadRest();
      }
    }, 3000);
  }, [loadRest, stopPolling]);

  useEffect(() => {
    // Initial REST load
    loadRest();

    // Connect WebSocket
    setConnectionStatus('connecting');
    const ws = new TrafficWebSocket(
      getWebSocketUrl('/ws/live'),
      (snap) => { applySnapshot(snap); },
      () => {
        wsConnRef.current = true;
        setIsConnected(true);
        setConnectionStatus('connected');
        stopPolling();
      },
      () => {
        wsConnRef.current = false;
        setIsConnected(false);
        setConnectionStatus('disconnected');
        startPolling();
      },
    );
    wsRef.current = ws;
    ws.connect();

    // Fallback polling if WS never connects
    const fallbackTimer = setTimeout(() => {
      if (!wsConnRef.current) startPolling();
    }, 3000);

    return () => {
      clearTimeout(fallbackTimer);
      ws.disconnect();
      stopPolling();
    };
  }, [applySnapshot, loadRest, startPolling, stopPolling]);

  return (
    <TrafficContext.Provider
      value={{
        vehicles,
        classification,
        density,
        congestion,
        signals,
        kpis,
        intersections,
        isConnected,
        isLoading,
        lastUpdate,
        connectionStatus,
      }}
    >
      {children}
    </TrafficContext.Provider>
  );
}

export function useTraffic(): TrafficContextType {
  const ctx = useContext(TrafficContext);
  if (!ctx) throw new Error('useTraffic must be used within a TrafficProvider');
  return ctx;
}
