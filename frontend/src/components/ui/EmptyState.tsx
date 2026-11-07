import type { ReactNode } from 'react';
import { Inbox, type LucideIcon } from 'lucide-react';
import clsx from 'clsx';

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: LucideIcon;
  action?: ReactNode;
  className?: string;
}

/** Friendly empty state component for lists, charts, and tables without records. */
export default function EmptyState({
  title = 'No traffic activity yet',
  description = 'As vehicles move through the network, data will appear here automatically.',
  icon: Icon = Inbox,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      role="status"
      className={clsx(
        'flex flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface/50 px-6 py-12 text-center',
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-subtle text-muted">
        <Icon size={22} strokeWidth={1.75} aria-hidden="true" />
      </div>
      <h4 className="mt-3.5 text-sm font-semibold tracking-tight text-ink">
        {title}
      </h4>
      <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted">
        {description}
      </p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
