import clsx from 'clsx';

interface LoadingSpinnerProps {
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  center?: boolean;
}

const sizeMap = {
  sm: 'h-4 w-4',
  md: 'h-5 w-5',
  lg: 'h-6 w-6',
};

export default function LoadingSpinner({ label, size = 'md', center = false }: LoadingSpinnerProps) {
  return (
    <div className={clsx('flex flex-col items-center gap-3', center && 'min-h-[160px] justify-center')} role="status">
      <span className={clsx('animate-spin rounded-full border-2 border-line border-t-ink', sizeMap[size])} />
      {label && <p className="text-[13px] text-faint">{label}</p>}
    </div>
  );
}
