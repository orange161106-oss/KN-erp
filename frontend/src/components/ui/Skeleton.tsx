import React from 'react';

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export function Skeleton({ className = '', ...props }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded bg-slate-200 ${className}`}
      {...props}
    />
  );
}

export interface TableSkeletonProps {
  rows?: number;
  columns?: number;
  className?: string;
}

export function TableSkeleton({ rows = 5, columns = 6, className = '' }: TableSkeletonProps) {
  return (
    <div
      className={`w-full overflow-hidden rounded-lg border border-ink-text/10 bg-white shadow-2xs ${className}`}
      role="status"
      aria-label="Loading table data"
    >
      {/* Table Header Skeleton */}
      <div className="border-b border-ink-text/10 bg-vanilla-surface px-4 py-3.5 flex items-center gap-4">
        {Array.from({ length: columns }).map((_, i) => (
          <div
            key={`th-${i}`}
            className={`h-4 bg-ink-text/10 rounded animate-pulse ${
              i === 0 ? 'w-36' : i === columns - 1 ? 'w-20 ml-auto' : 'w-24'
            }`}
          />
        ))}
      </div>

      {/* Table Rows Skeleton */}
      <div className="divide-y divide-ink-text/10">
        {Array.from({ length: rows }).map((_, rIdx) => (
          <div key={`row-${rIdx}`} className="px-4 py-4 flex items-center gap-4">
            {Array.from({ length: columns }).map((_, cIdx) => (
              <div
                key={`cell-${rIdx}-${cIdx}`}
                className={`h-4 bg-slate-200 rounded animate-pulse ${
                  cIdx === 0
                    ? 'w-40'
                    : cIdx === 1
                    ? 'w-24'
                    : cIdx === columns - 1
                    ? 'w-16 ml-auto'
                    : 'w-28'
                }`}
                style={{ animationDelay: `${rIdx * 75}ms` }}
              />
            ))}
          </div>
        ))}
      </div>
      <span className="sr-only">Loading...</span>
    </div>
  );
}

export default Skeleton;
