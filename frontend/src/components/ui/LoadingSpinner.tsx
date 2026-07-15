import clsx from 'clsx';

interface LoadingSpinnerProps {
  label?:  string;
  size?:   'sm' | 'md' | 'lg';
  center?: boolean;
}

const sizeMap = {
  sm:  'w-4 h-4 border-2',
  md:  'w-8 h-8 border-2',
  lg:  'w-12 h-12 border-3',
};

export default function LoadingSpinner({ label, size = 'md', center = false }: LoadingSpinnerProps) {
  return (
    <div className={clsx('flex flex-col items-center gap-3', center && 'justify-center h-full min-h-[120px]')}>
      <div
        className={clsx(
          'rounded-full border-t-transparent animate-spin',
          'border-primary-500',
          sizeMap[size],
          'shadow-[0_0_12px_rgba(124,58,237,0.6)]',
        )}
        style={{ borderStyle: 'solid' }}
      />
      {label && (
        <p className="text-sm text-slate-400 font-medium animate-pulse">{label}</p>
      )}
    </div>
  );
}
