import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Info,
  X,
} from 'lucide-react';
import clsx from 'clsx';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  title?: string;
  durationMs?: number;
}

export interface ToastOptions {
  title?: string;
  type?: ToastType;
  durationMs?: number;
}

interface ToastContextValue {
  showToast: (message: string, options?: ToastOptions) => void;
  success: (message: string, title?: string) => void;
  error: (message: string, title?: string) => void;
  warning: (message: string, title?: string) => void;
  info: (message: string, title?: string) => void;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION = 4000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, options?: ToastOptions) => {
      const id = Math.random().toString(36).substring(2, 9);
      const type = options?.type || 'info';
      const title = options?.title;
      const durationMs = options?.durationMs ?? DEFAULT_DURATION;

      const newItem: ToastItem = { id, type, message, title, durationMs };

      setToasts((prev) => [...prev.slice(-4), newItem]); // Keep at most 5 toasts visible

      if (durationMs > 0) {
        setTimeout(() => {
          dismiss(id);
        }, durationMs);
      }
    },
    [dismiss],
  );

  const success = useCallback(
    (message: string, title?: string) => {
      showToast(message, { type: 'success', title });
    },
    [showToast],
  );

  const error = useCallback(
    (message: string, title?: string) => {
      showToast(message, { type: 'error', title, durationMs: 6000 });
    },
    [showToast],
  );

  const warning = useCallback(
    (message: string, title?: string) => {
      showToast(message, { type: 'warning', title });
    },
    [showToast],
  );

  const info = useCallback(
    (message: string, title?: string) => {
      showToast(message, { type: 'info', title });
    },
    [showToast],
  );

  const contextValue = useMemo(
    () => ({
      showToast,
      success,
      error,
      warning,
      info,
      dismiss,
    }),
    [showToast, success, error, warning, info, dismiss],
  );

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      {/* Toast notification container */}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex max-w-sm flex-col gap-2.5 p-2 sm:bottom-6 sm:right-6"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={clsx(
              'pointer-events-auto flex items-start gap-3 rounded-lg border p-3.5 shadow-lg backdrop-blur-sm transition-all animate-in fade-in slide-in-from-bottom-2',
              toast.type === 'success' && 'border-ok/30 bg-surface text-ink',
              toast.type === 'error' && 'border-bad/30 bg-surface text-ink',
              toast.type === 'warning' && 'border-warn/30 bg-surface text-ink',
              toast.type === 'info' && 'border-line bg-surface text-ink',
            )}
          >
            <div className="mt-0.5 flex-shrink-0">
              {toast.type === 'success' && <CheckCircle2 size={16} className="text-ok" />}
              {toast.type === 'error' && <AlertCircle size={16} className="text-bad" />}
              {toast.type === 'warning' && <AlertTriangle size={16} className="text-warn" />}
              {toast.type === 'info' && <Info size={16} className="text-brand" />}
            </div>

            <div className="min-w-0 flex-1">
              {toast.title && (
                <p className="text-xs font-semibold text-ink">{toast.title}</p>
              )}
              <p className="text-xs leading-relaxed text-muted">{toast.message}</p>
            </div>

            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              className="btn btn-ghost btn-icon -mr-1.5 -mt-1.5 h-6 w-6 text-faint hover:text-ink"
              aria-label="Dismiss notification"
            >
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
