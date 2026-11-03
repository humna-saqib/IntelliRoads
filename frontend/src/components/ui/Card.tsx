import type { ReactNode } from 'react';
import clsx from 'clsx';

interface CardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  /** set to false for content that should touch the card edges (tables, lists) */
  padded?: boolean;
}

/** A soft panel: surface fill, hairline border and a barely-there shadow. */
export default function Card({ title, subtitle, action, children, className, padded = true }: CardProps) {
  const hasHeader = Boolean(title || action);
  return (
    <section className={clsx('rounded-xl border border-line bg-surface shadow-card', className)}>
      {hasHeader && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <div className="min-w-0">
            {title && <h3 className="text-sm font-semibold tracking-tight text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {action && <div className="flex-shrink-0">{action}</div>}
        </header>
      )}
      <div className={clsx(padded ? (hasHeader ? 'px-5 pb-5 pt-4' : 'p-5') : hasHeader ? 'pt-3' : '')}>{children}</div>
    </section>
  );
}
