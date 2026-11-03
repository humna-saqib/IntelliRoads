import clsx from 'clsx';

type Variant = 'success' | 'warning' | 'danger' | 'info' | 'neutral';
type Size = 'sm' | 'md';

interface BadgeProps {
  label: string;
  variant?: Variant;
  size?: Size;
}

const variantStyles: Record<Variant, string> = {
  success: 'bg-ok/10 text-ok',
  warning: 'bg-warn/10 text-warn',
  danger: 'bg-bad/10 text-bad',
  info: 'bg-info/10 text-info',
  neutral: 'bg-subtle text-muted',
};

const sizeStyles: Record<Size, string> = {
  sm: 'px-1.5 py-0.5 text-2xs',
  md: 'px-2 py-0.5 text-xs',
};

/** Small status label: a coloured dot and sentence-case text on a faint tint. */
export default function Badge({ label, variant = 'neutral', size = 'md' }: BadgeProps) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-md font-medium', variantStyles[variant], sizeStyles[size])}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}
