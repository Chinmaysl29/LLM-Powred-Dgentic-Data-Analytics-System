/**
 * Skeleton loaders � Phase 23.12
 * Shimmer-animated placeholder components for loading states.
 */

interface SkeletonProps {
  width?: string;
  height?: string;
  borderRadius?: string;
  className?: string;
}

export function Skeleton({
  width = '100%',
  height = '16px',
  borderRadius = '6px',
  className = '',
}: SkeletonProps) {
  return (
    <span
      className={`skeleton ${className}`}
      style={{ width, height, borderRadius, display: 'block' }}
      aria-hidden="true"
    />
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-card" aria-hidden="true">
      <Skeleton height="20px" width="60%" />
      <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} height="14px" width={i === lines - 1 ? '75%' : '100%'} />
        ))}
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="skeleton-table" aria-hidden="true">
      <div
        className="skeleton-table-header"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: '8px',
          marginBottom: '12px',
        }}
      >
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} height="14px" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${cols}, 1fr)`,
            gap: '8px',
            marginBottom: '8px',
          }}
        >
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} height="12px" width={c === 0 ? '80%' : '60%'} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart({ height = '280px' }: { height?: string }) {
  return (
    <div className="skeleton-chart" style={{ height }} aria-hidden="true">
      <Skeleton height="20px" width="40%" />
      <div
        style={{
          marginTop: '20px',
          height: 'calc(100% - 40px)',
          display: 'flex',
          alignItems: 'flex-end',
          gap: '8px',
        }}
      >
        {[60, 85, 45, 92, 70, 55, 80, 65, 90, 75].map((h, i) => (
          <Skeleton key={i} height={`${h}%`} width="100%" borderRadius="4px 4px 0 0" />
        ))}
      </div>
    </div>
  );
}

export function SkeletonKPI() {
  return (
    <div className="skeleton-kpi" aria-hidden="true">
      <Skeleton height="12px" width="50%" />
      <Skeleton height="32px" width="70%" />
      <Skeleton height="12px" width="40%" />
    </div>
  );
}
