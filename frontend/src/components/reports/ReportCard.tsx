import React, { useState, useRef, useEffect } from 'react';
import {
  FileText,
  Database,
  Calendar,
  ExternalLink,
  Edit3,
  Download,
  MoreVertical,
  Copy,
  Archive,
  Trash2,
  Clock,
} from 'lucide-react';
import type { Report } from '../../types/reports';
import { ReportStatusBadge } from './ReportStatusBadge';

interface ReportCardProps {
  report: Report;
  onOpen: (reportId: string) => void;
  onEdit: (reportId: string) => void;
  onExport: (report: Report) => void;
  onDuplicate: (reportId: string) => void;
  onArchive: (reportId: string) => void;
  onDelete: (reportId: string) => void;
}

const TYPE_LABELS: Record<string, string> = {
  business_performance: 'Business Performance',
  sales_analysis: 'Sales Analysis',
  customer_analysis: 'Customer Analysis',
  marketing_analysis: 'Marketing Analysis',
  custom: 'Custom Report',
};

export const ReportCard: React.FC<ReportCardProps> = ({
  report,
  onOpen,
  onEdit,
  onExport,
  onDuplicate,
  onArchive,
  onDelete,
}) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close overflow menu on outside click
  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) {
      document.addEventListener('mousedown', handleOutside);
    }
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [menuOpen]);

  const typeLabel = TYPE_LABELS[report.reportType] || 'Business Report';

  // Format updated timestamp relative
  const updatedDate = new Date(report.updatedAt);
  const dateFormatted = updatedDate.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="reports-card">
      {/* Top Header Strip */}
      <div className="reports-card-header">
        <div className="reports-card-header-left">
          <div className="reports-card-icon-wrap" aria-hidden="true">
            <FileText size={18} />
          </div>
          <div>
            <span className="reports-type-pill">{typeLabel}</span>
          </div>
        </div>
        <div className="reports-card-header-right">
          <ReportStatusBadge status={report.status} />
          {/* Action overflow menu */}
          <div className="reports-card-menu-anchor" ref={menuRef}>
            <button
              type="button"
              className="reports-icon-btn"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label="More actions"
            >
              <MoreVertical size={16} />
            </button>
            {menuOpen && (
              <div className="reports-dropdown-menu" role="menu">
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onOpen(report.id);
                  }}
                  role="menuitem"
                >
                  <ExternalLink size={14} />
                  <span>Open Report</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onEdit(report.id);
                  }}
                  role="menuitem"
                >
                  <Edit3 size={14} />
                  <span>Edit in Builder</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onDuplicate(report.id);
                  }}
                  role="menuitem"
                >
                  <Copy size={14} />
                  <span>Duplicate</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onArchive(report.id);
                  }}
                  role="menuitem"
                >
                  <Archive size={14} />
                  <span>Archive</span>
                </button>
                <div className="reports-menu-divider" />
                <button
                  type="button"
                  className="reports-menu-delete"
                  onClick={() => {
                    setMenuOpen(false);
                    onDelete(report.id);
                  }}
                  role="menuitem"
                >
                  <Trash2 size={14} />
                  <span>Delete</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Title & Description */}
      <div
        className="reports-card-body"
        onClick={() => onOpen(report.id)}
        role="button"
        tabIndex={0}
      >
        <h3 className="reports-card-title">{report.title}</h3>
        {report.description && <p className="reports-card-desc">{report.description}</p>}
      </div>

      {/* Meta Attributes Strip */}
      <div className="reports-card-meta-strip">
        <div className="reports-meta-chip">
          <Database size={13} className="reports-meta-icon" />
          <span className="reports-meta-val" title={report.dataset}>
            {report.dataset}
          </span>
        </div>
        <div className="reports-meta-chip">
          <Calendar size={13} className="reports-meta-icon" />
          <span className="reports-meta-val">
            {report.dateRange.label || `${report.dateRange.start} – ${report.dateRange.end}`}
          </span>
        </div>
      </div>

      {/* Footer Info & Quick Actions */}
      <div className="reports-card-footer">
        <div className="reports-updated-text">
          <Clock size={12} />
          <span>Updated {dateFormatted}</span>
        </div>

        <div className="reports-card-actions">
          <button
            type="button"
            className="reports-btn-ghost"
            onClick={() => onExport(report)}
            title="Export Report"
          >
            <Download size={13} />
            <span>Export</span>
          </button>
          <button
            type="button"
            className="reports-btn-secondary"
            onClick={() => onEdit(report.id)}
            title="Edit in Builder"
          >
            <Edit3 size={13} />
            <span>Edit</span>
          </button>
          <button
            type="button"
            className="reports-btn-primary"
            onClick={() => onOpen(report.id)}
            title="View Full Report"
          >
            <span>Open</span>
            <ExternalLink size={13} />
          </button>
        </div>
      </div>
    </div>
  );
};
