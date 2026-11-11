import React from 'react';
import type { ReportStatus } from '../../types/reports';

interface ReportStatusBadgeProps {
  status: ReportStatus;
}

const STATUS_CONFIG: Record<ReportStatus, { label: string; className: string }> = {
  draft: {
    label: 'Draft',
    className: 'reports-status-draft',
  },
  generating: {
    label: 'Generating',
    className: 'reports-status-generating',
  },
  generated: {
    label: 'Generated',
    className: 'reports-status-generated',
  },
  failed: {
    label: 'Failed',
    className: 'reports-status-failed',
  },
  archived: {
    label: 'Archived',
    className: 'reports-status-archived',
  },
};

export const ReportStatusBadge: React.FC<ReportStatusBadgeProps> = ({ status }) => {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;

  return (
    <span
      className={`reports-status-badge ${config.className}`}
      aria-label={`Status: ${config.label}`}
    >
      <span className="reports-status-dot" aria-hidden="true" />
      <span>{config.label}</span>
    </span>
  );
};
