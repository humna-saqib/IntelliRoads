import React, { useEffect, useState, useCallback } from 'react';
import { fetchAllThresholds, updateJunctionThresholds, type JunctionThresholds } from '../services/api';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { Settings2, Save, RotateCcw, CheckCircle, AlertTriangle } from 'lucide-react';

const JUNCTION_LABELS: Record<string, string> = {
  junctionA: 'Junction A',
  junctionB: 'Junction B',
  junctionC: 'Junction C',
  junctionD: 'Junction D',
};

type FormState = Record<string, JunctionThresholds>;
type SaveState = Record<string, 'idle' | 'saving' | 'saved' | 'error'>;

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [original, setOriginal] = useState<FormState>({});
  const [form, setForm] = useState<FormState>({});
  const [saveState, setSaveState] = useState<SaveState>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchAllThresholds();
      setOriginal(data);
      setForm(data);
    } catch (err) {
      console.error('Failed to fetch thresholds:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleChange = (junctionId: string, field: keyof JunctionThresholds, value: string) => {
    const num = parseFloat(value);
    setForm((prev) => ({
      ...prev,
      [junctionId]: { ...prev[junctionId], [field]: isNaN(num) ? 0 : num },
    }));
    setSaveState((prev) => ({ ...prev, [junctionId]: 'idle' }));
  };

  const isDirty = (junctionId: string) =>
    JSON.stringify(form[junctionId]) !== JSON.stringify(original[junctionId]);

  const handleReset = (junctionId: string) => {
    setForm((prev) => ({ ...prev, [junctionId]: original[junctionId] }));
    setErrors((prev) => ({ ...prev, [junctionId]: '' }));
    setSaveState((prev) => ({ ...prev, [junctionId]: 'idle' }));
  };

  const handleSave = async (junctionId: string) => {
    const values = form[junctionId];
    if (values.low_threshold >= values.medium_threshold) {
      setErrors((prev) => ({
        ...prev,
        [junctionId]: 'Low threshold must be less than medium threshold.',
      }));
      return;
    }
    setErrors((prev) => ({ ...prev, [junctionId]: '' }));
    setSaveState((prev) => ({ ...prev, [junctionId]: 'saving' }));
    try {
      const saved = await updateJunctionThresholds(junctionId, values);
      setOriginal((prev) => ({ ...prev, [junctionId]: saved }));
      setForm((prev) => ({ ...prev, [junctionId]: saved }));
      setSaveState((prev) => ({ ...prev, [junctionId]: 'saved' }));
      setTimeout(() => {
        setSaveState((prev) => ({ ...prev, [junctionId]: 'idle' }));
      }, 2000);
    } catch (err) {
      console.error(`Failed to save thresholds for ${junctionId}:`, err);
      setErrors((prev) => ({
        ...prev,
        [junctionId]: 'Failed to save — please try again.',
      }));
      setSaveState((prev) => ({ ...prev, [junctionId]: 'error' }));
    }
  };

  if (loading) {
    return <LoadingSpinner label="Loading threshold settings…" center />;
  }

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-slate-900/40 p-5 rounded-2xl border border-white/5 backdrop-blur-md">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Settings2 className="h-6 w-6 text-primary-400" />
            Intersection Settings
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Configure density and congestion thresholds per intersection
          </p>
        </div>
      </div>

      {/* Per-junction threshold cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {Object.keys(form)
          .sort()
          .map((junctionId) => {
            const values = form[junctionId];
            const dirty = isDirty(junctionId);
            const state = saveState[junctionId] ?? 'idle';
            const error = errors[junctionId];

            return (
              <div
                key={junctionId}
                className="rounded-2xl border border-white/5 bg-slate-900/40 backdrop-blur-md p-5"
              >
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-semibold text-white">
                    {JUNCTION_LABELS[junctionId] ?? junctionId}
                  </h2>
                  {!dirty && state === 'idle' && (
                    <span className="text-[10px] text-slate-500 uppercase tracking-wide">
                      No unsaved changes
                    </span>
                  )}
                </div>

                <div className="space-y-3">
                  <ThresholdField
                    label="Low density threshold"
                    hint="Below this, density is LOW (veh/km)"
                    value={values.low_threshold}
                    onChange={(v) => handleChange(junctionId, 'low_threshold', v)}
                  />
                  <ThresholdField
                    label="Medium density threshold"
                    hint="Below this, density is MEDIUM; at/above is HIGH (veh/km)"
                    value={values.medium_threshold}
                    onChange={(v) => handleChange(junctionId, 'medium_threshold', v)}
                  />
                  <ThresholdField
                    label="Congestion threshold"
                    hint="Density above this triggers a congestion alert (veh/km)"
                    value={values.congestion_threshold}
                    onChange={(v) => handleChange(junctionId, 'congestion_threshold', v)}
                  />
                </div>

                {error && (
                  <div className="flex items-center gap-1.5 mt-3 text-[11px] text-danger-400">
                    <AlertTriangle size={12} />
                    {error}
                  </div>
                )}

                <div className="flex items-center gap-2 mt-4">
                  <button
                    type="button"
                    disabled={!dirty || state === 'saving'}
                    onClick={() => handleSave(junctionId)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-primary-600/20 text-primary-300 border border-primary-500/30 hover:bg-primary-600/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    {state === 'saved' ? <CheckCircle size={13} /> : <Save size={13} />}
                    {state === 'saving' ? 'Saving…' : state === 'saved' ? 'Saved' : 'Save changes'}
                  </button>
                  <button
                    type="button"
                    disabled={!dirty}
                    onClick={() => handleReset(junctionId)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <RotateCcw size={13} />
                    Reset
                  </button>
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}

function ThresholdField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-300 mb-1">{label}</label>
      <input
        type="number"
        step="0.1"
        min="0"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/8 text-sm text-white focus:outline-none focus:border-primary-500/50 focus:bg-white/[0.05] transition-colors"
      />
      <p className="text-[10px] text-slate-500 mt-1">{hint}</p>
    </div>
  );
}
