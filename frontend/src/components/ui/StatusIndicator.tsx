import clsx from 'clsx';

type Status = 'online' | 'offline' | 'warning' | 'connecting';

interface StatusIndicatorProps {
  status: Status;
  label?: string;
  size?: 'sm' | 'md';
}

const dotColor: Record<Status, string> = {
  online: 'bg-ok',
  offline: 'bg-bad',
  warning: 'bg-warn',
  connecting: 'bg-faint animate-pulse',
};

export default function StatusIndicator({ status, label, size = 'md' }: StatusIndicatorProps) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={clsx('rounded-full', dotColor[status], size === 'sm' ? 'h-1.5 w-1.5' : 'h-2 w-2')} />
      {label && <span className={clsx('text-muted', size === 'sm' ? 'text-xs' : 'text-[13px]')}>{label}</span>}
    </span>
  );
}
