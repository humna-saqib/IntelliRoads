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

/** A flat panel: white surface, hairline border, no shadow. */
export default function Card({ title, subtitle, action, children, className, padded = true }: CardProps) {
  const hasHeader = Boolean(title || action);
  return (
    <section className={clsx('rounded-lg border border-line bg-surface', className)}>
      {hasHeader && (
        <header className="flex items-start justify-between gap-3 px-4 pt-3.5">
          <div className="min-w-0">
            {title && <h3 className="text-[13px] font-medium text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-faint">{subtitle}</p>}
          </div>
          {action && <div className="flex-shrink-0">{action}</div>}
        </header>
      )}
      <div className={clsx(padded ? (hasHeader ? 'px-4 pb-4 pt-3' : 'p-4') : hasHeader ? 'pt-3' : '')}>{children}</div>
    </section>
  );
}
