import type { ReactNode } from 'react';
import { AlertCircle, RotateCcw, Loader2 } from 'lucide-react';
import clsx from 'clsx';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  isRetrying?: boolean;
  action?: ReactNode;
  className?: string;
}

/**
 * Friendly error state component for unreachable backends or failed fetches.
 * Uses conversational, non-technical language and an optional Retry button.
 */
export default function ErrorState({
  title = 'Connection problem',
  message = "We can't reach the traffic system right now. Retrying…",
  onRetry,
  isRetrying = false,
  action,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={clsx(
        'flex flex-col items-center justify-center rounded-xl border border-bad/30 bg-bad/5 px-6 py-12 text-center text-ink',
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-bad/10 text-bad">
        <AlertCircle size={22} strokeWidth={1.8} aria-hidden="true" />
      </div>

      <h4 className="mt-3.5 text-sm font-semibold tracking-tight text-ink">
        {title}
      </h4>

      <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted">
        {message}
      </p>

      {(onRetry || action) && (
        <div className="mt-5 flex items-center gap-3">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              disabled={isRetrying}
              className="btn btn-primary min-h-[44px] min-w-[120px] px-4"
            >
              {isRetrying ? (
                <>
                  <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                  <span>Retrying…</span>
                </>
              ) : (
                <>
                  <RotateCcw size={15} strokeWidth={1.75} aria-hidden="true" />
                  <span>Try again</span>
                </>
              )}
            </button>
          )}
          {action}
        </div>
      )}
    </div>
  );
}
