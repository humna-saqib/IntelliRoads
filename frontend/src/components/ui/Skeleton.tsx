import type { ReactNode } from 'react';
import clsx from 'clsx';

interface SkeletonProps {
  className?: string;
}

/** Base skeleton block with an animated shimmer pulse. */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={clsx('animate-pulse rounded bg-subtle/80', className)}
    />
  );
}

interface CardSkeletonProps {
  className?: string;
  hasHeader?: boolean;
  children?: ReactNode;
  height?: string | number;
}

/** Card container skeleton matching Card.tsx design tokens. */
export function CardSkeleton({
  className,
  hasHeader = true,
  children,
  height = 'h-48',
}: CardSkeletonProps) {
  return (
    <section
      aria-busy="true"
      aria-label="Loading card content"
      className={clsx(
        'rounded-xl border border-line bg-surface p-5 shadow-card',
        className,
      )}
    >
      {hasHeader && (
        <div className="mb-4 space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      )}
      {children || <Skeleton className={clsx('w-full', typeof height === 'string' ? height : '')} />}
    </section>
  );
}

interface ChartSkeletonProps {
  className?: string;
  height?: string;
}

/** Chart skeleton placeholder with axes and bars simulation. */
export function ChartSkeleton({ className, height = 'h-64' }: ChartSkeletonProps) {
  return (
    <div
      aria-busy="true"
      aria-label="Loading chart"
      className={clsx('flex flex-col justify-between rounded-lg p-2', height, className)}
    >
      {/* Title skeleton */}
      <div className="mb-4 flex items-center justify-between">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-3 w-20" />
      </div>

      {/* Bars/lines grid placeholder */}
      <div className="flex flex-1 items-end gap-3 px-2 pb-2">
        <Skeleton className="h-[40%] flex-1" />
        <Skeleton className="h-[75%] flex-1" />
        <Skeleton className="h-[55%] flex-1" />
        <Skeleton className="h-[90%] flex-1" />
        <Skeleton className="h-[60%] flex-1" />
        <Skeleton className="h-[80%] flex-1" />
        <Skeleton className="h-[45%] flex-1" />
        <Skeleton className="h-[65%] flex-1" />
      </div>

      {/* Axis line & labels */}
      <div className="border-t border-line/60 pt-2">
        <div className="flex justify-between gap-2 px-1">
          <Skeleton className="h-2.5 w-10" />
          <Skeleton className="h-2.5 w-10" />
          <Skeleton className="h-2.5 w-10" />
          <Skeleton className="h-2.5 w-10" />
        </div>
      </div>
    </div>
  );
}

interface TableRowSkeletonProps {
  columns?: number;
  className?: string;
}

/** A single table row skeleton with animated cells. */
export function TableRowSkeleton({ columns = 5, className }: TableRowSkeletonProps) {
  return (
    <tr className={clsx('border-b border-line/50', className)}>
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className={clsx('h-4', i === 0 ? 'w-20' : i === columns - 1 ? 'w-16 ml-auto' : 'w-full max-w-[120px]')} />
        </td>
      ))}
    </tr>
  );
}

interface TableSkeletonProps {
  columns?: number;
  rows?: number;
  className?: string;
}

/** Complete table skeleton for loading states in data tables. */
export function TableSkeleton({ columns = 5, rows = 5, className }: TableSkeletonProps) {
  return (
    <div
      aria-busy="true"
      aria-label="Loading table data"
      className={clsx('overflow-x-auto rounded-lg border border-line bg-surface', className)}
    >
      <table className="tbl w-full text-left text-xs">
        <thead>
          <tr className="border-b border-line bg-subtle/50">
            {Array.from({ length: columns }).map((_, i) => (
              <th key={i} className="px-4 py-3">
                <Skeleton className="h-3 w-16" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <TableRowSkeleton key={i} columns={columns} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default Skeleton;
