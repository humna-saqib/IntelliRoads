import { X, BookOpen, Sparkles, Sliders, MapPin, Gauge } from 'lucide-react';
import { PLAIN_TERMS } from '../../constants/plainWords';

interface GlossaryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const GLOSSARY_ENTRIES = [
  {
    term: PLAIN_TERMS.dqn,
    category: 'Signal Control',
    icon: Sparkles,
    meaning:
      'A reinforcement learning model (Double DQN) that continuously monitors traffic queues across approaches and dynamically changes traffic lights to reduce overall wait times.',
  },
  {
    term: PLAIN_TERMS.ruleBased,
    category: 'Signal Control',
    icon: Sliders,
    meaning:
      'Traditional traffic signal timing that changes lights using fixed schedules and preset queue thresholds.',
  },
  {
    term: 'Monitored Intersections',
    category: 'Network',
    icon: MapPin,
    meaning:
      'The four monitored grid junctions: Northwest Square (junction A), Northeast Plaza (junction B), Southeast Gateway (junction C), and Southwest Crossing (junction D).',
  },
  {
    term: PLAIN_TERMS.occupancyLabel,
    category: 'Metrics',
    icon: Gauge,
    meaning:
      'How full the road currently is, shown as a percentage. Higher fullness indicates vehicles are packed closely together.',
  },
  {
    term: 'Cars per km',
    category: 'Metrics',
    icon: Gauge,
    meaning:
      'Traffic density measuring how many vehicles occupy a single kilometer of road. Over 40 cars/km indicates heavy congestion.',
  },
  {
    term: 'Flowing smoothly / Traffic jam',
    category: 'Traffic Status',
    icon: Gauge,
    meaning:
      'Human-friendly traffic conditions: "Flowing smoothly" means vehicles move freely with minimal delay; "Traffic jam" means severe queues require prioritized signal clearance.',
  },
];

export default function GlossaryModal({ isOpen, onClose }: GlossaryModalProps) {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="glossary-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl border border-line bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-subtle text-brand">
              <BookOpen size={16} />
            </div>
            <div>
              <h2 id="glossary-title" className="text-base font-semibold tracking-tight text-ink">
                Plain-Language Glossary
              </h2>
              <p className="text-xs text-muted">Clear explanations of traffic system terminology</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-icon"
            aria-label="Close glossary"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {GLOSSARY_ENTRIES.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.term}
                className="rounded-xl border border-line bg-subtle/50 p-4 transition-colors hover:bg-subtle"
              >
                <div className="flex items-center gap-2">
                  <Icon size={14} className="text-brand flex-shrink-0" />
                  <h3 className="text-sm font-semibold text-ink">{item.term}</h3>
                  <span className="ml-auto rounded-md bg-surface px-2 py-0.5 text-2xs font-medium text-faint border border-line">
                    {item.category}
                  </span>
                </div>
                <p className="mt-1.5 text-xs text-muted leading-relaxed">{item.meaning}</p>
              </div>
            );
          })}
        </div>

        <div className="border-t border-line px-6 py-3 flex justify-end bg-subtle/30 rounded-b-2xl">
          <button
            type="button"
            onClick={onClose}
            className="btn btn-secondary min-h-[36px] text-xs font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
