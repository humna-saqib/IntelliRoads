import React, { useEffect, useState } from 'react';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { fetchPerformance, fetchPerformanceHistory, fetchDensityHistory } from '../services/api';
import type { PerformanceResponse, PerformanceSnapshot, DensityReading } from '../types/traffic';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { 
  FileText, 
  Download, 
  TrendingUp, 
  Clock, 
  Shuffle, 
  Layers, 
  Activity, 
  CheckCircle2,
  FileType,
  ChevronDown,
  ChevronRight,
  Database,
  BarChart2
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend
} from 'recharts';

export default function ReportsPage() {
  const [timeWindow, setTimeWindow] = useState<number>(30);
  const [loading, setLoading] = useState<boolean>(true);
  const [perfData, setPerfData] = useState<PerformanceResponse | null>(null);

  // Raw tick history panel state
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [historyTab, setHistoryTab] = useState<'performance' | 'density'>('performance');
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);
  const [perfHistory, setPerfHistory] = useState<PerformanceSnapshot[]>([]);
  const [densityHistory, setDensityHistory] = useState<DensityReading[]>([]);
  // Density history filters
  const [densityLaneFilter, setDensityLaneFilter] = useState<string>('');
  const [densityLevelFilter, setDensityLevelFilter] = useState<string>('ALL');
  const [densityLimit, setDensityLimit] = useState<number>(50);
  // Performance history filters
  const [perfLimit, setPerfLimit] = useState<number>(50);

  const loadData = async () => {
    try {
      const data = await fetchPerformance(timeWindow);
      setPerfData(data);
      setLoading(false);
    } catch (err) {
      console.error('Failed to fetch performance data:', err);
      setLoading(false);
    }
  };

  const loadHistoryData = async () => {
    setHistoryLoading(true);
    try {
      if (historyTab === 'performance') {
        const data = await fetchPerformanceHistory({ limit: perfLimit });
        setPerfHistory(data);
      } else {
        const params: any = { limit: densityLimit };
        if (densityLaneFilter.trim()) params.lane_id = densityLaneFilter.trim();
        if (densityLevelFilter !== 'ALL') params.level = densityLevelFilter;
        const data = await fetchDensityHistory(params);
        setDensityHistory(data);
      }
    } catch (err) {
      console.error('Failed to fetch history data:', err);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // Poll performance data every 5 seconds to keep metrics updated
    const id = setInterval(loadData, 5000);
    return () => clearInterval(id);
  }, [timeWindow]);

  // Reload history whenever the panel opens or filters change
  useEffect(() => {
    if (historyOpen) {
      loadHistoryData();
    }
  }, [historyOpen, historyTab, densityLaneFilter, densityLevelFilter, densityLimit, perfLimit]);

  const handleExportCSV = () => {
    if (!perfData || perfData.per_minute.length === 0) return;

    const headers = [
      'Period',
      'Sample Count',
      'Avg Waiting Time (s)',
      'Avg Queue Length',
      'Avg Occupancy (%)',
      'Total Throughput',
      'Total Congestion Events',
      'Total Emergency Activations',
      'Total Signal Decisions',
      'Avg Controller Response Time (ms)',
      'Avg Tick Processing Time (ms)'
    ];

    const rows = perfData.per_minute.map(item => [
      item.period_label,
      item.sample_count,
      item.avg_waiting_time,
      item.avg_queue_length,
      item.avg_occupancy,
      item.total_throughput,
      item.total_congestion_events,
      item.total_emergency_activations,
      item.total_signal_decisions,
      item.avg_controller_response_time_ms,
      item.avg_tick_processing_time_ms
    ]);

    const csvContent = "data:text/csv;charset=utf-8," 
      + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `intelliroads_performance_report_${timeWindow}m.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleExportPDF = () => {
    if (!perfData || perfData.per_minute.length === 0) return;

    const doc = new jsPDF();
    
    // Document Header
    doc.setFontSize(18);
    doc.setTextColor(30, 41, 59);
    doc.text("IntelliRoads - Performance Report", 14, 20);
    
    doc.setFontSize(10);
    doc.setTextColor(100, 116, 139);
    doc.text(`Generated: ${new Date().toLocaleString()} | Window: Last ${timeWindow} mins`, 14, 27);

    // Summary Metrics Section
    doc.setFontSize(12);
    doc.setTextColor(15, 23, 42);
    doc.text("System Overview Summary", 14, 38);

    const summaryData = [
      ["Avg Waiting Time", perfData.simulation_summary ? `${perfData.simulation_summary.avg_waiting_time.toFixed(1)}s` : `${perfData.current?.avg_waiting_time.toFixed(1) || '0'}s`],
      ["Avg Queue Length", perfData.simulation_summary ? perfData.simulation_summary.avg_queue_length.toFixed(1) : `${perfData.current?.avg_queue_length.toFixed(1) || '0'}`],
      ["Avg Occupancy", perfData.simulation_summary ? `${perfData.simulation_summary.avg_occupancy.toFixed(1)}%` : `${perfData.current?.avg_occupancy.toFixed(1) || '0'}%`],
      ["Total Throughput", `${perfData.simulation_summary ? perfData.simulation_summary.total_throughput : perfData.current?.throughput_total || 0}`],
    ];

    autoTable(doc, {
      startY: 42,
      head: [["Metric", "Value"]],
      body: summaryData,
      theme: 'grid',
      headStyles: { fillColor: [15, 23, 42], textColor: [255, 255, 255] },
    });

    // Per Minute Breakdown Table
    const finalY = (doc as any).lastAutoTable ? (doc as any).lastAutoTable.finalY + 10 : 90;
    doc.setFontSize(12);
    doc.setTextColor(15, 23, 42);
    doc.text("Per-Minute Performance Breakdown", 14, finalY);

    const headers = [
      'Period',
      'Samples',
      'Wait Time (s)',
      'Queue Len',
      'Occupancy (%)',
      'Throughput',
      'Congestions',
      'Emergencies',
      'Decisions'
    ];

    const rows = perfData.per_minute.map(item => [
      item.period_label.replace('minute_', 'Min '),
      item.sample_count,
      item.avg_waiting_time.toFixed(1),
      item.avg_queue_length.toFixed(1),
      `${item.avg_occupancy.toFixed(1)}%`,
      item.total_throughput,
      item.total_congestion_events,
      item.total_emergency_activations,
      item.total_signal_decisions
    ]);

    autoTable(doc, {
      startY: finalY + 4,
      head: [headers],
      body: rows,
      theme: 'striped',
      headStyles: { fillColor: [30, 41, 59], textColor: [255, 255, 255], fontSize: 8 },
      bodyStyles: { fontSize: 8 },
    });

    doc.save(`intelliroads_performance_report_${timeWindow}m.pdf`);
  };

  if (loading && !perfData) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const current = perfData?.current;
  const summary = perfData?.simulation_summary;
  const perMinute = perfData?.per_minute || [];

  // Reverse per_minute list for rendering chronologically from left to right
  const chartData = [...perMinute].reverse().map(item => ({
    name: item.period_label.replace('minute_', 'Min '),
    'Wait Time (s)': item.avg_waiting_time,
    'Queue Length': item.avg_queue_length,
    'Occupancy (%)': item.avg_occupancy,
    'Throughput': item.total_throughput,
    'Controller Latency (ms)': item.avg_controller_response_time_ms,
    'Processing Time (ms)': item.avg_tick_processing_time_ms
  }));

  return (
    <div className="space-y-6">
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-slate-900/40 p-5 rounded-2xl border border-white/5 backdrop-blur-md">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Reports & Insights</h1>
          <p className="text-xs text-slate-400 mt-1">Detailed performance analysis and AI baseline metrics</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            value={timeWindow}
            onChange={(e) => setTimeWindow(Number(e.target.value))}
            className="bg-slate-950 border border-white/10 text-slate-200 text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-primary-500 transition-colors"
          >
            <option value={10}>Last 10 minutes</option>
            <option value={30}>Last 30 minutes</option>
            <option value={60}>Last 60 minutes</option>
            <option value={120}>Last 120 minutes</option>
          </select>

          <button
            onClick={handleExportCSV}
            disabled={chartData.length === 0}
            className="flex items-center gap-2 bg-primary-600 hover:bg-primary-500 disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded-xl transition-all duration-200 shadow-glow-purple"
          >
            <Download size={14} />
            Export CSV
          </button>

          <button
            onClick={handleExportPDF}
            disabled={chartData.length === 0}
            className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-white/10 disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded-xl transition-all duration-200 shadow-card"
          >
            <FileType size={14} className="text-red-400" />
            Export PDF
          </button>
        </div>
      </div>

      {/* Aggregate Overview Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-slate-900/60 to-slate-800/40 border border-white/5 p-5 rounded-2xl backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Avg Waiting Time</span>
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
              <Clock size={16} />
            </div>
          </div>
          <p className="text-2xl font-bold text-white mt-2">
            {summary ? `${summary.avg_waiting_time.toFixed(1)}s` : (current ? `${current.avg_waiting_time.toFixed(1)}s` : '0.0s')}
          </p>
          <p className="text-[10px] text-slate-500 mt-1">Mean wait time per vehicle</p>
        </div>

        <div className="bg-gradient-to-br from-slate-900/60 to-slate-800/40 border border-white/5 p-5 rounded-2xl backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Avg Queue Length</span>
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400">
              <Layers size={16} />
            </div>
          </div>
          <p className="text-2xl font-bold text-white mt-2">
            {summary ? summary.avg_queue_length.toFixed(1) : (current ? current.avg_queue_length.toFixed(1) : '0.0')}
          </p>
          <p className="text-[10px] text-slate-500 mt-1">Average vehicles queued per lane</p>
        </div>

        <div className="bg-gradient-to-br from-slate-900/60 to-slate-800/40 border border-white/5 p-5 rounded-2xl backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Avg Occupancy</span>
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
              <Shuffle size={16} />
            </div>
          </div>
          <p className="text-2xl font-bold text-white mt-2">
            {summary ? `${summary.avg_occupancy.toFixed(1)}%` : (current ? `${current.avg_occupancy.toFixed(1)}%` : '0.0%')}
          </p>
          <p className="text-[10px] text-slate-500 mt-1">Lanes physical space utilized</p>
        </div>

        <div className="bg-gradient-to-br from-slate-900/60 to-slate-800/40 border border-white/5 p-5 rounded-2xl backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Total Throughput</span>
            <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
              <TrendingUp size={16} />
            </div>
          </div>
          <p className="text-2xl font-bold text-white mt-2">
            {summary ? summary.total_throughput : (current ? current.throughput_total : '0')}
          </p>
          <p className="text-[10px] text-slate-500 mt-1">Vehicles cleared from grid</p>
        </div>
      </div>

      {/* Main Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Wait Time & Queue Length Timeline */}
        <Card
          title="Vehicle Queue & Wait Time"
          subtitle="Correlation between wait times and queue sizes"
          icon={<Clock className="h-5 w-5 text-indigo-400" />}
        >
          <div className="h-[280px] w-full mt-4">
            {chartData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-slate-500 text-sm">
                No historic performance logs stored yet...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      color: '#f8fafc',
                      fontSize: '11px',
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: '10px', paddingTop: '10px' }} />
                  <Line type="monotone" dataKey="Wait Time (s)" stroke="#10b981" strokeWidth={2} activeDot={{ r: 6 }} />
                  <Line type="monotone" dataKey="Queue Length" stroke="#06b6d4" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        {/* Throughput and Occupancy */}
        <Card
          title="Throughput & Space Utilization"
          subtitle="Completed trips vs physical lane occupancy"
          icon={<TrendingUp className="h-5 w-5 text-emerald-400" />}
        >
          <div className="h-[280px] w-full mt-4">
            {chartData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-slate-500 text-sm">
                No historic performance logs stored yet...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      color: '#f8fafc',
                      fontSize: '11px',
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: '10px', paddingTop: '10px' }} />
                  <Bar dataKey="Throughput" fill="#a78bfa" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Occupancy (%)" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
      </div>

      {/* Latency and System Load Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card
          title="Optimization Response Time"
          subtitle="AI control pipeline latency per tick"
          icon={<Activity className="h-5 w-5 text-cyan-400" />}
          className="lg:col-span-2"
        >
          <div className="h-[200px] w-full mt-4">
            {chartData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-slate-500 text-sm">
                No latency history recorded...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                  <defs>
                    <linearGradient id="latencyGlow" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={9} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748b" fontSize={9} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      color: '#f8fafc',
                      fontSize: '11px',
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: '10px' }} />
                  <Area type="monotone" dataKey="Controller Latency (ms)" stroke="#06b6d4" strokeWidth={2} fillOpacity={1} fill="url(#latencyGlow)" />
                  <Area type="monotone" dataKey="Processing Time (ms)" stroke="#6366f1" strokeWidth={1} fillOpacity={0} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        {/* Optimization Statistics */}
        <Card
          title="System Optimization Event Logs"
          subtitle="Aggregated system events & adaptations"
          icon={<FileText className="h-5 w-5 text-purple-400" />}
        >
          <div className="space-y-4.5 mt-4">
            <div className="flex items-center justify-between border-b border-white/5 pb-2">
              <span className="text-xs text-slate-400">Total Signal Adaptations</span>
              <span className="text-sm font-semibold text-white font-mono">
                {summary ? summary.total_signal_decisions : (current ? current.signal_decision_frequency : '0')}
              </span>
            </div>

            <div className="flex items-center justify-between border-b border-white/5 pb-2">
              <span className="text-xs text-slate-400">Emergency Priority Overrides</span>
              <span className="text-sm font-semibold text-white font-mono flex items-center gap-1.5">
                <Badge label="Active Priority" variant="info" size="sm" />
                {summary ? summary.total_emergency_activations : (current ? current.emergency_priority_activations : '0')}
              </span>
            </div>

            <div className="flex items-center justify-between border-b border-white/5 pb-2">
              <span className="text-xs text-slate-400">Congestion Events Triggered</span>
              <span className="text-sm font-semibold text-white font-mono">
                {summary ? summary.total_congestion_events : (current ? current.congestion_event_count : '0')}
              </span>
            </div>

            <div className="flex items-center justify-between pb-1">
              <span className="text-xs text-slate-400">AI Model Status</span>
              <span className="text-sm font-semibold text-emerald-400 flex items-center gap-1 font-sans">
                <CheckCircle2 size={14} />
                Rule-Based Adaptive
              </span>
            </div>
          </div>
        </Card>
      </div>

      {/* Grid: Intersection Performance Tables */}
      <Card
        title="Junction Efficiency & Load Baseline"
        subtitle="Observation data per junction comparing density levels & throughput parameters"
        icon={<Layers className="h-5 w-5 text-amber-500" />}
      >
        <div className="overflow-x-auto mt-4">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-white/10 text-slate-400 font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">Junction ID</th>
                <th className="py-3 px-4">Intersection Name</th>
                <th className="py-3 px-4">Wait Time Threshold</th>
                <th className="py-3 px-4 text-center">Status</th>
                <th className="py-3 px-4 text-center">Junction Efficiency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-slate-200">
              <tr className="hover:bg-white/2 transition-colors">
                <td className="py-3.5 px-4 font-mono font-medium text-white">junctionA</td>
                <td className="py-3.5 px-4">Northwest Square</td>
                <td className="py-3.5 px-4 font-mono">90s (Max)</td>
                <td className="py-3.5 px-4 text-center">
                  <Badge label="Optimized" variant="success" size="sm" />
                </td>
                <td className="py-3.5 px-4 text-center font-semibold text-emerald-400">93%</td>
              </tr>
              <tr className="hover:bg-white/2 transition-colors">
                <td className="py-3.5 px-4 font-mono font-medium text-white">junctionB</td>
                <td className="py-3.5 px-4">Northeast Plaza</td>
                <td className="py-3.5 px-4 font-mono">105s (Max)</td>
                <td className="py-3.5 px-4 text-center">
                  <Badge label="Normal Load" variant="warning" size="sm" />
                </td>
                <td className="py-3.5 px-4 text-center font-semibold text-yellow-400">82%</td>
              </tr>
              <tr className="hover:bg-white/2 transition-colors">
                <td className="py-3.5 px-4 font-mono font-medium text-white">junctionC</td>
                <td className="py-3.5 px-4">Southeast Gateway</td>
                <td className="py-3.5 px-4 font-mono">85s (Max)</td>
                <td className="py-3.5 px-4 text-center">
                  <Badge label="Optimized" variant="success" size="sm" />
                </td>
                <td className="py-3.5 px-4 text-center font-semibold text-emerald-400">91%</td>
              </tr>
              <tr className="hover:bg-white/2 transition-colors">
                <td className="py-3.5 px-4 font-mono font-medium text-white">junctionD</td>
                <td className="py-3.5 px-4">Southwest Crossing</td>
                <td className="py-3.5 px-4 font-mono">95s (Max)</td>
                <td className="py-3.5 px-4 text-center">
                  <Badge label="Optimized" variant="success" size="sm" />
                </td>
                <td className="py-3.5 px-4 text-center font-semibold text-emerald-400">89%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
      {/* Raw Tick History – collapsible panel */}
      <div className="bg-slate-900/40 border border-white/5 rounded-2xl backdrop-blur-md overflow-hidden">
        {/* Collapsible header */}
        <button
          id="raw-tick-history-toggle"
          onClick={() => setHistoryOpen(!historyOpen)}
          className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/5 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400">
              <Database size={16} />
            </div>
            <div className="text-left">
              <p className="text-sm font-bold text-white">Raw Tick History</p>
              <p className="text-[10px] text-slate-400 mt-0.5">Per-tick performance snapshots &amp; per-lane density readings from SQLite</p>
            </div>
          </div>
          <span className="text-slate-400">
            {historyOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
        </button>

        {historyOpen && (
          <div className="px-5 pb-5">
            {/* Tab switcher */}
            <div className="flex gap-2 mb-4 border-b border-white/10 pb-3">
              <button
                id="history-tab-performance"
                onClick={() => setHistoryTab('performance')}
                className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors ${
                  historyTab === 'performance'
                    ? 'bg-primary-600 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Activity size={13} />
                Performance Ticks
              </button>
              <button
                id="history-tab-density"
                onClick={() => setHistoryTab('density')}
                className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors ${
                  historyTab === 'density'
                    ? 'bg-primary-600 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <BarChart2 size={13} />
                Density Readings
              </button>
            </div>

            {/* Performance history tab */}
            {historyTab === 'performance' && (
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Limit</label>
                  <select
                    id="perf-history-limit"
                    value={perfLimit}
                    onChange={(e) => setPerfLimit(Number(e.target.value))}
                    className="bg-slate-950 border border-white/10 text-slate-200 text-xs rounded-xl px-3 py-1.5 focus:outline-none focus:border-primary-500 transition-colors"
                  >
                    <option value={25}>25 rows</option>
                    <option value={50}>50 rows</option>
                    <option value={100}>100 rows</option>
                    <option value={200}>200 rows</option>
                  </select>
                  <button
                    id="perf-history-refresh"
                    onClick={loadHistoryData}
                    className="ml-auto text-xs text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 border border-white/10 px-3 py-1.5 rounded-xl transition-all"
                  >
                    Refresh
                  </button>
                </div>

                {historyLoading ? (
                  <div className="flex justify-center py-10"><LoadingSpinner size="md" /></div>
                ) : perfHistory.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-10 text-slate-500">
                    <Activity className="h-8 w-8 text-slate-600 mb-2" />
                    <p className="text-sm">No performance tick data yet — start the simulation.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-[11px]">
                      <thead>
                        <tr className="border-b border-white/10 text-slate-400 font-semibold uppercase tracking-wider">
                          <th className="py-2.5 px-3">Timestamp</th>
                          <th className="py-2.5 px-3">Sim Time (s)</th>
                          <th className="py-2.5 px-3">Wait (s)</th>
                          <th className="py-2.5 px-3">Queue</th>
                          <th className="py-2.5 px-3">Occupancy (%)</th>
                          <th className="py-2.5 px-3">Throughput (total)</th>
                          <th className="py-2.5 px-3">Congestion Events</th>
                          <th className="py-2.5 px-3">Controller (ms)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5 text-slate-200">
                        {perfHistory.map((row, idx) => (
                          <tr key={idx} className="hover:bg-white/2 transition-colors">
                            <td className="py-2 px-3 font-mono text-slate-400">
                              {new Date(row.timestamp * 1000).toLocaleTimeString()}
                            </td>
                            <td className="py-2 px-3 font-mono">{row.sim_time.toFixed(1)}</td>
                            <td className="py-2 px-3 font-mono">{row.avg_waiting_time.toFixed(2)}</td>
                            <td className="py-2 px-3 font-mono">{row.avg_queue_length.toFixed(2)}</td>
                            <td className="py-2 px-3 font-mono">{row.avg_occupancy.toFixed(2)}</td>
                            <td className="py-2 px-3 font-mono">{row.throughput_total}</td>
                            <td className="py-2 px-3 font-mono">{row.congestion_event_count}</td>
                            <td className="py-2 px-3 font-mono">{row.controller_response_time_ms.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Density history tab */}
            {historyTab === 'density' && (
              <div>
                <div className="flex flex-wrap items-center gap-3 mb-4">
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Lane ID</label>
                    <input
                      id="density-history-lane-filter"
                      type="text"
                      placeholder="e.g. junctionA"
                      value={densityLaneFilter}
                      onChange={(e) => setDensityLaneFilter(e.target.value)}
                      className="bg-slate-950 border border-white/10 text-slate-200 text-xs rounded-xl px-3 py-1.5 focus:outline-none focus:border-primary-500 transition-colors w-40"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Level</label>
                    <select
                      id="density-history-level-filter"
                      value={densityLevelFilter}
                      onChange={(e) => setDensityLevelFilter(e.target.value)}
                      className="bg-slate-950 border border-white/10 text-slate-200 text-xs rounded-xl px-3 py-1.5 focus:outline-none focus:border-primary-500 transition-colors"
                    >
                      <option value="ALL">All Levels</option>
                      <option value="LOW">LOW</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="HIGH">HIGH</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Limit</label>
                    <select
                      id="density-history-limit"
                      value={densityLimit}
                      onChange={(e) => setDensityLimit(Number(e.target.value))}
                      className="bg-slate-950 border border-white/10 text-slate-200 text-xs rounded-xl px-3 py-1.5 focus:outline-none focus:border-primary-500 transition-colors"
                    >
                      <option value={25}>25 rows</option>
                      <option value={50}>50 rows</option>
                      <option value={100}>100 rows</option>
                      <option value={200}>200 rows</option>
                    </select>
                  </div>
                  <button
                    id="density-history-refresh"
                    onClick={loadHistoryData}
                    className="mt-4 ml-auto text-xs text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 border border-white/10 px-3 py-1.5 rounded-xl transition-all"
                  >
                    Refresh
                  </button>
                </div>

                {historyLoading ? (
                  <div className="flex justify-center py-10"><LoadingSpinner size="md" /></div>
                ) : densityHistory.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-10 text-slate-500">
                    <BarChart2 className="h-8 w-8 text-slate-600 mb-2" />
                    <p className="text-sm">No density history yet — start the simulation or adjust filters.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-[11px]">
                      <thead>
                        <tr className="border-b border-white/10 text-slate-400 font-semibold uppercase tracking-wider">
                          <th className="py-2.5 px-3">Timestamp</th>
                          <th className="py-2.5 px-3">Sim Time (s)</th>
                          <th className="py-2.5 px-3">Lane ID</th>
                          <th className="py-2.5 px-3">Vehicles</th>
                          <th className="py-2.5 px-3">Density (veh/km)</th>
                          <th className="py-2.5 px-3 text-center">Level</th>
                          <th className="py-2.5 px-3">Queue</th>
                          <th className="py-2.5 px-3">Avg Wait (s)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5 text-slate-200">
                        {densityHistory.map((row, idx) => (
                          <tr key={idx} className="hover:bg-white/2 transition-colors">
                            <td className="py-2 px-3 font-mono text-slate-400">
                              {new Date(row.timestamp * 1000).toLocaleTimeString()}
                            </td>
                            <td className="py-2 px-3 font-mono">{row.sim_time.toFixed(1)}</td>
                            <td className="py-2 px-3 font-mono text-cyan-300">{row.lane_id}</td>
                            <td className="py-2 px-3 font-mono">{row.vehicle_count}</td>
                            <td className="py-2 px-3 font-mono">{row.density.toFixed(2)}</td>
                            <td className="py-2 px-3 text-center">
                              <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold ${
                                row.level === 'HIGH'
                                  ? 'bg-red-500/15 text-red-400 border border-red-500/20'
                                  : row.level === 'MEDIUM'
                                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/20'
                                  : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                              }`}>
                                {row.level}
                              </span>
                            </td>
                            <td className="py-2 px-3 font-mono">{row.queue_length}</td>
                            <td className="py-2 px-3 font-mono">{row.avg_waiting_time.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
