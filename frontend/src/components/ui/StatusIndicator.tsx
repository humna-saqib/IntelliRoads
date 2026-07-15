import clsx from 'clsx';

type Status = 'online' | 'offline' | 'warning' | 'connecting';

interface StatusIndicatorProps {
  status:    Status;
  label?:    string;
  size?:     'sm' | 'md' | 'lg';
}

const colorMap: Record<Status, { dot: string; ring: string; label: string }> = {
  online:     { dot: 'bg-success-500', ring: 'bg-success-500/30',  label: 'text-success-400' },
  offline:    { dot: 'bg-danger-500',  ring: 'bg-danger-500/30',   label: 'text-danger-400'  },
  warning:    { dot: 'bg-warning-500', ring: 'bg-warning-500/30',  label: 'text-warning-400' },
  connecting: { dot: 'bg-accent-500',  ring: 'bg-accent-500/30',   label: 'text-accent-400'  },
};

const sizeMap = {
  sm:  { dot: 'w-1.5 h-1.5', ring: 'w-3.5 h-3.5', text: 'text-xs' },
  md:  { dot: 'w-2   h-2',   ring: 'w-4   h-4',   text: 'text-sm' },
  lg:  { dot: 'w-3   h-3',   ring: 'w-6   h-6',   text: 'text-base' },
};

export default function StatusIndicator({ status, label, size = 'md' }: StatusIndicatorProps) {
  const colors = colorMap[status];
  const sizes  = sizeMap[size];

  return (
    <div className="flex items-center gap-2">
      {/* Pulsing ring */}
      <div className="relative flex items-center justify-center">
        <span
          className={clsx(
            'absolute rounded-full animate-ping opacity-75',
            colors.ring,
            sizes.ring,
            status === 'offline' && 'animation-duration-1000',
          )}
        />
        <span className={clsx('relative rounded-full', colors.dot, sizes.dot)} />
      </div>
      {label && (
        <span className={clsx('font-medium', colors.label, sizes.text)}>
          {label}
        </span>
      )}
    </div>
  );
}
