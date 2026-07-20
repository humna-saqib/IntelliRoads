import clsx from 'clsx';

type Variant = 'success' | 'warning' | 'danger' | 'info' | 'neutral';
type Size    = 'sm' | 'md';

interface BadgeProps {
  label:    string;
  variant?: Variant;
  size?:    Size;
  pulse?:   boolean;
}

const variantStyles: Record<Variant, string> = {
  success: 'bg-success-500/20 text-success-400 border border-success-500/30 shadow-[0_0_8px_rgba(34,197,94,0.3)]',
  warning: 'bg-warning-500/20 text-warning-400 border border-warning-500/30 shadow-[0_0_8px_rgba(245,158,11,0.3)]',
  danger:  'bg-danger-500/20  text-danger-400  border border-danger-500/30  shadow-[0_0_8px_rgba(239,68,68,0.3)]',
  info:    'bg-accent-500/20  text-accent-400  border border-accent-500/30  shadow-[0_0_8px_rgba(6,182,212,0.3)]',
  neutral: 'bg-surface-600/40 text-slate-300   border border-white/10',
};

const sizeStyles: Record<Size, string> = {
  sm: 'px-1.5 py-0.5 text-[10px] font-semibold',
  md: 'px-2.5 py-1   text-xs     font-semibold',
};

export default function Badge({ label, variant = 'neutral', size = 'md', pulse = false }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full tracking-wide uppercase',
        variantStyles[variant],
        sizeStyles[size],
        pulse && 'animate-pulse',
      )}
    >
      {label}
    </span>
  );
}
