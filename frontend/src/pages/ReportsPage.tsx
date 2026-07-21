import React, { useEffect, useState } from 'react';
import { fetchPerformance } from '../services/api';
import type { PerformanceResponse } from '../types/traffic';
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
  CheckCircle2 
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

  useEffect(() => {
    loadData();
    // Poll performance data every 5 seconds to keep metrics updated
    const id = setInterval(loadData, 5000);
    return () => clearInterval(id);
  }, [timeWindow]);

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
    </div>
  );
}
