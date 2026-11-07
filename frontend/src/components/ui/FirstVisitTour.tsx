import { useState, useEffect } from 'react';
import { X, ArrowRight, ArrowLeft, Check, Sparkles, Sliders, Layers, Activity } from 'lucide-react';
import clsx from 'clsx';

const TOUR_STORAGE_KEY = 'intelliroads_tour_completed';

const TOUR_STEPS = [
  {
    title: 'Welcome to IntelliRoads',
    subtitle: 'Step 1 of 4: Live Status',
    icon: Activity,
    content:
      'The top status banner gives you an immediate plain-language summary of traffic flow ("Flowing smoothly" or "Heavy congestion"), practical recommendations, and real-time 5-minute trends.',
  },
  {
    title: 'Monitored Junction Cards',
    subtitle: 'Step 2 of 4: Junction Insights',
    icon: Sparkles,
    content:
      'Every junction (Northwest Square, Northeast Plaza, Southeast Gateway, Southwest Crossing) shows live queue counts, active light colors with live countdowns, and what the control system just did.',
  },
  {
    title: 'Signal Timing Switch',
    subtitle: 'Step 3 of 4: Standard Timing vs Smart AI',
    icon: Sliders,
    content:
      'Easily toggle between Standard Timing (fixed threshold schedules) and Smart AI (reinforcement learning that dynamically clears bottlenecks) with a single click.',
  },
  {
    title: 'Detailed Data & Warnings',
    subtitle: 'Step 4 of 4: Full Diagnostics',
    icon: Layers,
    content:
      'Click "Open warnings" to view congestion alert history, or expand the "Detailed data" section at the bottom for comprehensive diagnostic charts and vehicle tables.',
  },
];

interface FirstVisitTourProps {
  forceOpen?: boolean;
  onClose?: () => void;
}

export default function FirstVisitTour({ forceOpen = false, onClose }: FirstVisitTourProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    if (forceOpen) {
      setIsOpen(true);
      setCurrentStep(0);
      return;
    }
    const completed = localStorage.getItem(TOUR_STORAGE_KEY);
    if (!completed) {
      setIsOpen(true);
    }
  }, [forceOpen]);

  const dismissTour = () => {
    localStorage.setItem(TOUR_STORAGE_KEY, 'true');
    setIsOpen(false);
    onClose?.();
  };

  const handleNext = () => {
    if (currentStep < TOUR_STEPS.length - 1) {
      setCurrentStep((prev) => prev + 1);
    } else {
      dismissTour();
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep((prev) => prev - 1);
    }
  };

  if (!isOpen) return null;

  const step = TOUR_STEPS[currentStep];
  const StepIcon = step.icon;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="First-visit guided tour"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in"
    >
      <div className="w-full max-w-lg rounded-2xl border border-line bg-surface p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-line pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-brand/20 bg-brand/10 text-brand">
              <StepIcon size={18} />
            </div>
            <div>
              <span className="text-2xs font-semibold uppercase tracking-wider text-brand">
                {step.subtitle}
              </span>
              <h2 className="text-base font-semibold tracking-tight text-ink">
                {step.title}
              </h2>
            </div>
          </div>
          <button
            type="button"
            onClick={dismissTour}
            className="btn btn-ghost btn-icon"
            aria-label="Skip tour"
          >
            <X size={16} />
          </button>
        </div>

        <p className="mt-4 min-h-[4rem] text-sm leading-relaxed text-muted">
          {step.content}
        </p>

        {/* Step dots */}
        <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
          <div className="flex items-center gap-1.5" aria-hidden="true">
            {TOUR_STEPS.map((_, idx) => (
              <span
                key={idx}
                className={clsx(
                  'h-1.5 rounded-full transition-all',
                  idx === currentStep ? 'w-6 bg-brand' : 'w-1.5 bg-line-strong',
                )}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={dismissTour}
              className="btn btn-ghost min-h-[36px] text-xs font-medium text-muted hover:text-ink"
            >
              Skip
            </button>

            {currentStep > 0 && (
              <button
                type="button"
                onClick={handleBack}
                className="btn btn-secondary min-h-[36px] flex items-center gap-1 text-xs font-medium"
              >
                <ArrowLeft size={13} />
                <span>Back</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleNext}
              className="btn btn-brand min-h-[36px] flex items-center gap-1 text-xs font-medium"
            >
              <span>{currentStep === TOUR_STEPS.length - 1 ? 'Got it' : 'Next'}</span>
              {currentStep === TOUR_STEPS.length - 1 ? <Check size={13} /> : <ArrowRight size={13} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
