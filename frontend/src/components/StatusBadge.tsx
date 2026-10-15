/**
 * StatusBadge.tsx
 *
 * Reusable dataset processing status badge component.
 * Used in both DatasetsPage (list) and DatasetDetailPage (detail).
 *
 * Kept in a dedicated file to comply with the ESLint
 * react-refresh/only-export-components rule: this file exports
 * ONLY a React component.
 *
 * Renders a dot + text label - does not rely on color alone (accessibility).
 * The status-badge--{status} CSS modifier maps to classes in index.css.
 */

import type { DatasetStatus } from '../types/datasets';
import { STATUS_LABELS } from '../datasetUtils';

export function StatusBadge({ status }: { status: DatasetStatus }) {
  const label = STATUS_LABELS[status] || status || 'Unknown';
  return (
    <span
      className={`status-badge status-badge--${status}`}
      aria-label={`Status: ${label}`}
    >
      {label}
    </span>
  );
}
