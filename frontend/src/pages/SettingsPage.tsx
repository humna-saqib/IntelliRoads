import { useEffect, useState, useCallback } from 'react';
import { fetchAllThresholds, updateJunctionThresholds, type JunctionThresholds } from '../services/api';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import PageIntro from '../components/ui/PageIntro';
import Card from '../components/ui/Card';
import { Check } from 'lucide-react';
import { getJunctionName } from '../constants/plainWords';

type FormState = Record<string, JunctionThresholds>;
type SaveState = Record<string, 'idle' | 'saving' | 'saved' | 'error'>;

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.title = 'Settings · IntelliRoads';
  }, []);
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
    setForm((prev) => ({ ...prev, [junctionId]: { ...prev[junctionId], [field]: isNaN(num) ? 0 : num } }));
    setSaveState((prev) => ({ ...prev, [junctionId]: 'idle' }));
  };

  const isDirty = (junctionId: string) => JSON.stringify(form[junctionId]) !== JSON.stringify(original[junctionId]);

  const handleReset = (junctionId: string) => {
    setForm((prev) => ({ ...prev, [junctionId]: original[junctionId] }));
    setErrors((prev) => ({ ...prev, [junctionId]: '' }));
    setSaveState((prev) => ({ ...prev, [junctionId]: 'idle' }));
  };

  const handleSave = async (junctionId: string) => {
    const values = form[junctionId];
    if (values.low_threshold >= values.medium_threshold) {
      setErrors((prev) => ({ ...prev, [junctionId]: 'The low threshold must be less than the medium threshold.' }));
      return;
    }
    setErrors((prev) => ({ ...prev, [junctionId]: '' }));
    setSaveState((prev) => ({ ...prev, [junctionId]: 'saving' }));
    try {
      const saved = await updateJunctionThresholds(junctionId, values);
      setOriginal((prev) => ({ ...prev, [junctionId]: saved }));
      setForm((prev) => ({ ...prev, [junctionId]: saved }));
      setSaveState((prev) => ({ ...prev, [junctionId]: 'saved' }));
      setTimeout(() => setSaveState((prev) => ({ ...prev, [junctionId]: 'idle' })), 2000);
    } catch (err) {
      console.error(`Failed to save thresholds for ${junctionId}:`, err);
      setErrors((prev) => ({ ...prev, [junctionId]: 'Could not save. Please try again.' }));
      setSaveState((prev) => ({ ...prev, [junctionId]: 'error' }));
    }
  };

  if (loading) {
    return <LoadingSpinner label="Loading settings…" center />;
  }

  if (Object.keys(form).length === 0) {
    return (
      <div className="py-12">
        <ErrorState
          title="Threshold settings unavailable"
          message="We can't connect to the server right now to load the junction thresholds."
          onRetry={load}
        />
      </div>
    );
  }

  return (
    <div>
      <PageIntro description="Set the car-density levels (cars per km) that decide when a road is 'light', 'moderate', or 'too busy'. Warnings appear when density passes the congestion limit." />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {Object.keys(form)
          .sort()
          .map((junctionId) => {
            const values = form[junctionId];
            const dirty = isDirty(junctionId);
            const state = saveState[junctionId] ?? 'idle';
            const error = errors[junctionId];

            return (
              <Card
                key={junctionId}
                title={getJunctionName(junctionId)}
                action={dirty ? <span className="text-xs text-warn">Unsaved changes</span> : undefined}
              >
                <div className="space-y-3.5">
                  <ThresholdField
                    id={`${junctionId}-low`}
                    label="Low density threshold"
                    hint="Roads are considered lightly trafficked below this many cars per km — no warning will appear."
                    value={values.low_threshold}
                    onChange={(v) => handleChange(junctionId, 'low_threshold', v)}
                  />
                  <ThresholdField
                    id={`${junctionId}-medium`}
                    label="Medium density threshold"
                    hint="Above this limit the road is classed as moderately busy. The signal gets more time for heavy approaches."
                    value={values.medium_threshold}
                    onChange={(v) => handleChange(junctionId, 'medium_threshold', v)}
                  />
                  <ThresholdField
                    id={`${junctionId}-congestion`}
                    label="Congestion threshold"
                    hint="A warning appears when the road carries more than this many cars per km."
                    value={values.congestion_threshold}
                    onChange={(v) => handleChange(junctionId, 'congestion_threshold', v)}
                  />
                </div>

                {error && <p className="mt-3 text-xs text-bad">{error}</p>}

                <div className="mt-4 flex items-center gap-2">
                  <button type="button" disabled={!dirty || state === 'saving'} onClick={() => handleSave(junctionId)} className="btn btn-primary">
                    {state === 'saved' && <Check size={14} />}
                    {state === 'saving' ? 'Saving…' : state === 'saved' ? 'Saved' : 'Save changes'}
                  </button>
                  <button type="button" disabled={!dirty} onClick={() => handleReset(junctionId)} className="btn btn-ghost">
                    Reset
                  </button>
                </div>
              </Card>
            );
          })}
      </div>
    </div>
  );
}

function ThresholdField({
  id,
  label,
  hint,
  value,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  value: number;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="field-label">{label}</label>
      <input id={id} type="number" step="0.1" min="0" value={value} onChange={(e) => onChange(e.target.value)} className="input font-mono tabular-nums" />
      <p className="mt-1 text-xs text-faint">{hint}</p>
    </div>
  );
}
