import { useEffect, useState, type ReactNode } from 'react';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { fetchPerformance, fetchPerformanceHistory, fetchDensityHistory, fetchActiveModel, type ActiveModelInfo } from '../services/api';
import type { PerformanceResponse, PerformanceSnapshot, DensityReading } from '../types/traffic';
import { useChartTheme } from '../theme/chartTheme';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ChartTooltip from '../components/ui/ChartTooltip';
import PageIntro from '../components/ui/PageIntro';
import { Download, ChevronDown, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';

const EMPTY_MESSAGE = 'No performance history has been recorded yet.';

export default function ReportsPage() {
  const c = useChartTheme();
  const [timeWindow, setTimeWindow] = useState<number>(30);
  const [loading, setLoading] = useState<boolean>(true);
  const [perfData, setPerfData] = useState<PerformanceResponse | null>(null);
  const [model, setModel] = useState<ActiveModelInfo | null>(null);

  // raw tick history panel
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [historyTab, setHistoryTab] = useState<'performance' | 'density'>('performance');
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);
  const [perfHistory, setPerfHistory] = useState<PerformanceSnapshot[]>([]);
  const [densityHistory, setDensityHistory] = useState<DensityReading[]>([]);
  const [densityLaneFilter, setDensityLaneFilter] = useState<string>('');
  const [densityLevelFilter, setDensityLevelFilter] = useState<string>('ALL');
  const [densityLimit, setDensityLimit] = useState<number>(50);
  const [perfLimit, setPerfLimit] = useState<number>(50);

  const loadData = async () => {
    try {
      setPerfData(await fetchPerformance(timeWindow));
    } catch (err) {
      console.error('Failed to fetch performance data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadHistoryData = async () => {
    setHistoryLoading(true);
    try {
      if (historyTab === 'performance') {
        setPerfHistory(await fetchPerformanceHistory({ limit: perfLimit }));
      } else {
        const params: Record<string, string | number> = { limit: densityLimit };
        if (densityLaneFilter.trim()) params.lane_id = densityLaneFilter.trim();
        if (densityLevelFilter !== 'ALL') params.level = densityLevelFilter;
        setDensityHistory(await fetchDensityHistory(params));
      }
    } catch (err) {
      console.error('Failed to fetch history data:', err);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const id = setInterval(loadData, 5000); // keep the metrics fresh
    return () => clearInterval(id);
  }, [timeWindow]);

  useEffect(() => {
    let cancelled = false;
    const loadModel = () => fetchActiveModel().then((m) => !cancelled && setModel(m)).catch(() => !cancelled && setModel(null));
    loadModel();
    const id = setInterval(loadModel, 10000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (historyOpen) loadHistoryData();
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
      'Avg Tick Processing Time (ms)',
    ];

    const rows = perfData.per_minute.map((item) => [
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
      item.avg_tick_processing_time_ms,
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');

    const link = document.createElement('a');
    link.setAttribute('href', encodeURI(csvContent));
    link.setAttribute('download', `intelliroads_performance_report_${timeWindow}m.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleExportPDF = () => {
    if (!perfData || perfData.per_minute.length === 0) return;

    const doc = new jsPDF();

    doc.setFontSize(18);
    doc.setTextColor(24, 24, 27);
    doc.text('IntelliRoads - Performance Report', 14, 20);

    doc.setFontSize(10);
    doc.setTextColor(113, 113, 122);
    doc.text(`Generated: ${new Date().toLocaleString()} | Window: Last ${timeWindow} mins`, 14, 27);

    doc.setFontSize(12);
    doc.setTextColor(24, 24, 27);
    doc.text('System Overview Summary', 14, 38);

    const summaryData = [
      ['Avg Waiting Time', perfData.simulation_summary ? `${perfData.simulation_summary.avg_waiting_time.toFixed(1)}s` : `${perfData.current?.avg_waiting_time.toFixed(1) || '0'}s`],
      ['Avg Queue Length', perfData.simulation_summary ? perfData.simulation_summary.avg_queue_length.toFixed(1) : `${perfData.current?.avg_queue_length.toFixed(1) || '0'}`],
      ['Avg Occupancy', perfData.simulation_summary ? `${perfData.simulation_summary.avg_occupancy.toFixed(1)}%` : `${perfData.current?.avg_occupancy.toFixed(1) || '0'}%`],
      ['Total Throughput', `${perfData.simulation_summary ? perfData.simulation_summary.total_throughput : perfData.current?.throughput_total || 0}`],
    ];

    autoTable(doc, {
      startY: 42,
      head: [['Metric', 'Value']],
      body: summaryData,
      theme: 'grid',
      headStyles: { fillColor: [24, 24, 27], textColor: [255, 255, 255] },
    });

    const finalY = (doc as unknown as { lastAutoTable?: { finalY: number } }).lastAutoTable
      ? (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 10
      : 90;
    doc.setFontSize(12);
    doc.setTextColor(24, 24, 27);
    doc.text('Per-Minute Performance Breakdown', 14, finalY);

    const headers = ['Period', 'Samples', 'Wait Time (s)', 'Queue Len', 'Occupancy (%)', 'Throughput', 'Congestions', 'Emergencies', 'Decisions'];

    const rows = perfData.per_minute.map((item) => [
      item.period_label.replace('minute_', 'Min '),
      item.sample_count,
      item.avg_waiting_time.toFixed(1),
      item.avg_queue_length.toFixed(1),
      `${item.avg_occupancy.toFixed(1)}%`,
      item.total_throughput,
      item.total_congestion_events,
      item.total_emergency_activations,
      item.total_signal_decisions,
    ]);

    autoTable(doc, {
      startY: finalY + 4,
      head: [headers],
      body: rows,
      theme: 'striped',
      headStyles: { fillColor: [39, 39, 42], textColor: [255, 255, 255], fontSize: 8 },
      bodyStyles: { fontSize: 8 },
    });

    doc.save(`intelliroads_performance_report_${timeWindow}m.pdf`);
  };

  if (loading && !perfData) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const current = perfData?.current;
  const summary = perfData?.simulation_summary;
  const perMinute = perfData?.per_minute || [];

  // oldest first, so charts read left to right
  const chartData = [...perMinute].reverse().map((item) => ({
    name: item.period_label.replace('minute_', 'Min '),
    'Wait time (s)': item.avg_waiting_time,
    'Queue length': item.avg_queue_length,
    'Occupancy (%)': item.avg_occupancy,
    Throughput: item.total_throughput,
    'Controller latency (ms)': item.avg_controller_response_time_ms,
    'Processing time (ms)': item.avg_tick_processing_time_ms,
  }));

  const axisProps = { tick: { fill: c.axis, fontSize: 11 }, tickLine: false, axisLine: false } as const;
  const legendProps = { wrapperStyle: { fontSize: 12, paddingTop: 8 }, iconType: 'plainline' as const };

  const stats = [
    {
      label: 'Average wait',
      value: summary ? `${summary.avg_waiting_time.toFixed(1)} s` : current ? `${current.avg_waiting_time.toFixed(1)} s` : '0.0 s',
      note: 'mean wait per vehicle',
    },
    {
      label: 'Average queue',
      value: summary ? summary.avg_queue_length.toFixed(1) : current ? current.avg_queue_length.toFixed(1) : '0.0',
      note: 'vehicles queued per lane',
    },
    {
      label: 'Average occupancy',
      value: summary ? `${summary.avg_occupancy.toFixed(1)}%` : current ? `${current.avg_occupancy.toFixed(1)}%` : '0.0%',
      note: 'road space in use',
    },
    {
      label: 'Throughput',
      value: String(summary ? summary.total_throughput : current ? current.throughput_total : '0'),
      note: 'vehicles cleared from the grid',
    },
  ];

  const controllerText =
    model?.mode === 'DQN'
      ? model.file
        ? `DQN, ${model.obs_version} (episode ${model.selected_episode})`
        : 'DQN, legacy demo model'
      : model?.mode === 'RULE_BASED'
      ? 'Rule-based'
      : 'Unavailable';

  const eventRows: { label: string; value: ReactNode }[] = [
    { label: 'Signal decisions', value: summary ? summary.total_signal_decisions : current ? current.signal_decision_frequency : '0' },
    { label: 'Emergency priority overrides', value: summary ? summary.total_emergency_activations : current ? current.emergency_priority_activations : '0' },
    { label: 'Congestion events', value: summary ? summary.total_congestion_events : current ? current.congestion_event_count : '0' },
    { label: 'Active controller', value: controllerText },
  ];

  const chartEmpty = <div className="flex h-full items-center justify-center text-[13px] text-faint">{EMPTY_MESSAGE}</div>;

  return (
    <div>
      <PageIntro
        description="Performance of the traffic network over time, with exports for the selected window."
        actions={
          <>
            <select value={timeWindow} onChange={(e) => setTimeWindow(Number(e.target.value))} className="input w-auto" aria-label="Time window">
              <option value={10}>Last 10 minutes</option>
              <option value={30}>Last 30 minutes</option>
              <option value={60}>Last 60 minutes</option>
              <option value={120}>Last 120 minutes</option>
            </select>
            <button onClick={handleExportCSV} disabled={chartData.length === 0} className="btn">
              <Download size={14} strokeWidth={1.75} />
              CSV
            </button>
            <button onClick={handleExportPDF} disabled={chartData.length === 0} className="btn btn-primary">
              <Download size={14} strokeWidth={1.75} />
              PDF
            </button>
          </>
        }
      />

      <div className="space-y-4">
        <section className="grid grid-cols-2 overflow-hidden rounded-lg border border-line bg-surface lg:grid-cols-4" aria-label="Summary">
          {stats.map((s, i) => (
            <div key={s.label} className={clsx('px-4 py-3.5', i % 2 === 1 && 'border-l border-line', i >= 2 && 'border-t border-line lg:border-t-0', i === 2 && 'lg:border-l')}>
              <p className="text-xs text-faint">{s.label}</p>
              <p className="mt-1 text-2xl font-medium tabular-nums tracking-tight">{s.value}</p>
              <p className="mt-0.5 text-xs text-faint">{s.note}</p>
            </div>
          ))}
        </section>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card title="Wait time and queue length" subtitle="How waiting relates to queue size, per minute">
            <div className="h-[260px] w-full">
              {chartData.length === 0 ? chartEmpty : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke={c.grid} vertical={false} />
                    <XAxis dataKey="name" {...axisProps} />
                    <YAxis {...axisProps} />
                    <Tooltip content={<ChartTooltip />} cursor={{ stroke: c.grid }} />
                    <Legend {...legendProps} />
                    <Line type="monotone" dataKey="Wait time (s)" stroke={c.series[0]} strokeWidth={1.75} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
                    <Line type="monotone" dataKey="Queue length" stroke={c.series[1]} strokeWidth={1.75} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>

          <Card title="Throughput and occupancy" subtitle="Completed trips against road space in use, per minute">
            <div className="h-[260px] w-full">
              {chartData.length === 0 ? chartEmpty : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke={c.grid} vertical={false} />
                    <XAxis dataKey="name" {...axisProps} />
                    <YAxis {...axisProps} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: c.cursor }} />
                    <Legend {...legendProps} iconType="square" />
                    <Bar dataKey="Throughput" fill={c.series[0]} radius={[2, 2, 0, 0]} maxBarSize={22} isAnimationActive={false} />
                    <Bar dataKey="Occupancy (%)" fill={c.series[2]} radius={[2, 2, 0, 0]} maxBarSize={22} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card title="Controller response time" subtitle="Time the control pipeline takes per simulation step" className="lg:col-span-2">
            <div className="h-[200px] w-full">
              {chartData.length === 0 ? chartEmpty : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke={c.grid} vertical={false} />
                    <XAxis dataKey="name" {...axisProps} />
                    <YAxis {...axisProps} />
                    <Tooltip content={<ChartTooltip unit="ms" />} cursor={{ stroke: c.grid }} />
                    <Legend {...legendProps} />
                    <Line type="monotone" dataKey="Controller latency (ms)" stroke={c.series[0]} strokeWidth={1.75} dot={false} isAnimationActive={false} />
                    <Line type="monotone" dataKey="Processing time (ms)" stroke={c.series[4]} strokeWidth={1.25} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>

          <Card title="System events" subtitle="Totals for the selected window">
            <dl className="divide-y divide-line">
              {eventRows.map((row) => (
                <div key={row.label} className="flex items-baseline justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
                  <dt className="text-[13px] text-muted">{row.label}</dt>
                  <dd className="text-right text-[13px] tabular-nums text-ink">{row.value}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>

        <Card title="Junction load baseline" subtitle="Reference wait-time limits per junction" padded={false}>
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Junction</th>
                  <th>Name</th>
                  <th>Wait-time limit</th>
                  <th>Status</th>
                  <th className="text-right">Efficiency</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="font-mono text-xs">junctionA</td>
                  <td>Northwest Square</td>
                  <td className="font-mono tabular-nums">90 s</td>
                  <td><Badge label="Optimized" variant="success" size="sm" /></td>
                  <td className="text-right font-mono tabular-nums">93%</td>
                </tr>
                <tr>
                  <td className="font-mono text-xs">junctionB</td>
                  <td>Northeast Plaza</td>
                  <td className="font-mono tabular-nums">105 s</td>
                  <td><Badge label="Normal load" variant="warning" size="sm" /></td>
                  <td className="text-right font-mono tabular-nums">82%</td>
                </tr>
                <tr>
                  <td className="font-mono text-xs">junctionC</td>
                  <td>Southeast Gateway</td>
                  <td className="font-mono tabular-nums">85 s</td>
                  <td><Badge label="Optimized" variant="success" size="sm" /></td>
                  <td className="text-right font-mono tabular-nums">91%</td>
                </tr>
                <tr>
                  <td className="font-mono text-xs">junctionD</td>
                  <td>Southwest Crossing</td>
                  <td className="font-mono tabular-nums">95 s</td>
                  <td><Badge label="Optimized" variant="success" size="sm" /></td>
                  <td className="text-right font-mono tabular-nums">89%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        <section className="overflow-hidden rounded-lg border border-line bg-surface">
          <button
            id="raw-tick-history-toggle"
            onClick={() => setHistoryOpen(!historyOpen)}
            className="flex w-full items-center justify-between px-4 py-3.5 text-left transition-colors hover:bg-subtle/60"
            aria-expanded={historyOpen}
          >
            <div>
              <p className="text-[13px] font-medium">Raw tick history</p>
              <p className="mt-0.5 text-xs text-faint">Per-tick performance snapshots and per-lane density readings from the database</p>
            </div>
            {historyOpen ? <ChevronDown size={16} className="text-faint" /> : <ChevronRight size={16} className="text-faint" />}
          </button>

          {historyOpen && (
            <div className="border-t border-line px-4 pb-4 pt-3">
              <div className="mb-4 inline-flex gap-0.5 rounded-md bg-subtle p-0.5" role="tablist">
                {(['performance', 'density'] as const).map((tab) => (
                  <button
                    key={tab}
                    id={`history-tab-${tab}`}
                    role="tab"
                    aria-selected={historyTab === tab}
                    onClick={() => setHistoryTab(tab)}
                    className={clsx(
                      'h-7 rounded px-3 text-[13px] font-medium transition-colors',
                      historyTab === tab ? 'border border-line bg-surface text-ink shadow-sm' : 'border border-transparent text-muted hover:text-ink',
                    )}
                  >
                    {tab === 'performance' ? 'Performance ticks' : 'Density readings'}
                  </button>
                ))}
              </div>

              {historyTab === 'performance' && (
                <div>
                  <div className="mb-3 flex items-center gap-3">
                    <label htmlFor="perf-history-limit" className="text-xs text-muted">Rows</label>
                    <select id="perf-history-limit" value={perfLimit} onChange={(e) => setPerfLimit(Number(e.target.value))} className="input w-auto">
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                      <option value={200}>200</option>
                    </select>
                    <button id="perf-history-refresh" onClick={loadHistoryData} className="btn ml-auto">Refresh</button>
                  </div>

                  {historyLoading ? (
                    <div className="flex justify-center py-10"><LoadingSpinner size="md" /></div>
                  ) : perfHistory.length === 0 ? (
                    <p className="py-10 text-center text-[13px] text-faint">No performance tick data yet. Start the simulation.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="tbl text-xs">
                        <thead>
                          <tr>
                            <th>Time</th>
                            <th>Sim time (s)</th>
                            <th>Wait (s)</th>
                            <th>Queue</th>
                            <th>Occupancy (%)</th>
                            <th>Throughput</th>
                            <th>Congestion events</th>
                            <th>Controller (ms)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {perfHistory.map((row, idx) => (
                            <tr key={idx} className="font-mono tabular-nums">
                              <td className="text-muted">{new Date(row.timestamp * 1000).toLocaleTimeString()}</td>
                              <td>{row.sim_time.toFixed(1)}</td>
                              <td>{row.avg_waiting_time.toFixed(2)}</td>
                              <td>{row.avg_queue_length.toFixed(2)}</td>
                              <td>{row.avg_occupancy.toFixed(2)}</td>
                              <td>{row.throughput_total}</td>
                              <td>{row.congestion_event_count}</td>
                              <td>{row.controller_response_time_ms.toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {historyTab === 'density' && (
                <div>
                  <div className="mb-3 flex flex-wrap items-end gap-3">
                    <div>
                      <label htmlFor="density-history-lane-filter" className="field-label">Lane</label>
                      <input id="density-history-lane-filter" type="text" placeholder="e.g. lane_A_west_in" value={densityLaneFilter} onChange={(e) => setDensityLaneFilter(e.target.value)} className="input w-44" />
                    </div>
                    <div>
                      <label htmlFor="density-history-level-filter" className="field-label">Level</label>
                      <select id="density-history-level-filter" value={densityLevelFilter} onChange={(e) => setDensityLevelFilter(e.target.value)} className="input w-auto">
                        <option value="ALL">All levels</option>
                        <option value="LOW">Low</option>
                        <option value="MEDIUM">Medium</option>
                        <option value="HIGH">High</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="density-history-limit" className="field-label">Rows</label>
                      <select id="density-history-limit" value={densityLimit} onChange={(e) => setDensityLimit(Number(e.target.value))} className="input w-auto">
                        <option value={25}>25</option>
                        <option value={50}>50</option>
                        <option value={100}>100</option>
                        <option value={200}>200</option>
                      </select>
                    </div>
                    <button id="density-history-refresh" onClick={loadHistoryData} className="btn ml-auto">Refresh</button>
                  </div>

                  {historyLoading ? (
                    <div className="flex justify-center py-10"><LoadingSpinner size="md" /></div>
                  ) : densityHistory.length === 0 ? (
                    <p className="py-10 text-center text-[13px] text-faint">No density history yet. Start the simulation or change the filters.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="tbl text-xs">
                        <thead>
                          <tr>
                            <th>Time</th>
                            <th>Sim time (s)</th>
                            <th>Lane</th>
                            <th>Vehicles</th>
                            <th>Density (veh/km)</th>
                            <th>Level</th>
                            <th>Queue</th>
                            <th>Avg wait (s)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {densityHistory.map((row, idx) => (
                            <tr key={idx} className="font-mono tabular-nums">
                              <td className="text-muted">{new Date(row.timestamp * 1000).toLocaleTimeString()}</td>
                              <td>{row.sim_time.toFixed(1)}</td>
                              <td>{row.lane_id}</td>
                              <td>{row.vehicle_count}</td>
                              <td>{row.density.toFixed(2)}</td>
                              <td className="font-sans">
                                <Badge
                                  label={row.level.charAt(0) + row.level.slice(1).toLowerCase()}
                                  variant={row.level === 'HIGH' ? 'danger' : row.level === 'MEDIUM' ? 'warning' : 'success'}
                                  size="sm"
                                />
                              </td>
                              <td>{row.queue_length}</td>
                              <td>{row.avg_waiting_time.toFixed(2)}</td>
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
        </section>
      </div>
    </div>
  );
}
