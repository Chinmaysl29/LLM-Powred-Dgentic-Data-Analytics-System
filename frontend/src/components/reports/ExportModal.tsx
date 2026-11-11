import React, { useState } from 'react';
import {
  X,
  Download,
  FileText,
  FileSpreadsheet,
  Database,
  CheckCircle2,
  Loader2,
} from 'lucide-react';
import type { Report } from '../../types/reports';
import { exportReport } from '../../services/reportsService';

interface ExportModalProps {
  isOpen: boolean;
  report: Report | null;
  onClose: () => void;
}

export const ExportModal: React.FC<ExportModalProps> = ({ isOpen, report, onClose }) => {
  const [selectedFormat, setSelectedFormat] = useState<'pdf' | 'excel' | 'csv'>('pdf');
  const [isExporting, setIsExporting] = useState(false);
  const [exportedFile, setExportedFile] = useState<string | null>(null);

  if (!isOpen || !report) return null;

  const handleExport = async () => {
    setIsExporting(true);
    setExportedFile(null);
    try {
      const res = await exportReport(report.id, selectedFormat);
      setExportedFile(res.filename);
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setIsExporting(false);
    }
  };

  const handleResetAndClose = () => {
    setExportedFile(null);
    setIsExporting(false);
    onClose();
  };

  return (
    <div
      className="reports-modal-backdrop"
      onClick={handleResetAndClose}
      role="dialog"
      aria-modal="true"
    >
      <div className="reports-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="reports-modal-header">
          <div className="reports-modal-header-title">
            <Download size={18} className="reports-modal-icon" />
            <div>
              <h3>Export Business Report</h3>
              <p>{report.title}</p>
            </div>
          </div>
          <button
            type="button"
            className="reports-modal-close"
            onClick={handleResetAndClose}
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <div className="reports-modal-body">
          {!exportedFile ? (
            <>
              <div className="reports-format-selection-label">Select Output Format:</div>
              <div className="reports-format-grid">
                <button
                  type="button"
                  className={`reports-format-card ${selectedFormat === 'pdf' ? 'active' : ''}`}
                  onClick={() => setSelectedFormat('pdf')}
                >
                  <FileText size={24} className="reports-format-card-icon pdf" />
                  <div className="reports-format-name">Executive PDF</div>
                  <div className="reports-format-sub">
                    Formatted publication document with charts
                  </div>
                  <span className="reports-format-badge">Ready</span>
                </button>

                <button
                  type="button"
                  className={`reports-format-card ${selectedFormat === 'excel' ? 'active' : ''}`}
                  onClick={() => setSelectedFormat('excel')}
                >
                  <FileSpreadsheet size={24} className="reports-format-card-icon excel" />
                  <div className="reports-format-name">Excel (.xlsx)</div>
                  <div className="reports-format-sub">Raw structured metrics & scenario tables</div>
                  <span className="reports-format-badge">Contract Ready</span>
                </button>

                <button
                  type="button"
                  className={`reports-format-card ${selectedFormat === 'csv' ? 'active' : ''}`}
                  onClick={() => setSelectedFormat('csv')}
                >
                  <Database size={24} className="reports-format-card-icon csv" />
                  <div className="reports-format-name">CSV Data Tables</div>
                  <div className="reports-format-sub">Clean tabular data export for pipelines</div>
                  <span className="reports-format-badge">Contract Ready</span>
                </button>
              </div>

              <div className="reports-modal-note">
                Exports preserve verified evidence boundaries and underlying dataset provenance
                tags.
              </div>
            </>
          ) : (
            <div className="reports-export-success">
              <CheckCircle2 size={40} className="reports-success-icon" />
              <h4>Export Ready for Download</h4>
              <p>
                Your document <strong>{exportedFile}</strong> has been generated successfully.
              </p>
              <div className="reports-success-file-chip">
                <span>{exportedFile}</span>
              </div>
            </div>
          )}
        </div>

        <div className="reports-modal-footer">
          {!exportedFile ? (
            <>
              <button
                type="button"
                className="reports-btn-ghost"
                onClick={handleResetAndClose}
                disabled={isExporting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="reports-btn-primary"
                onClick={handleExport}
                disabled={isExporting}
              >
                {isExporting ? (
                  <>
                    <Loader2 size={14} className="reports-spinner" />
                    <span>Preparing Document...</span>
                  </>
                ) : (
                  <>
                    <Download size={14} />
                    <span>Download {selectedFormat.toUpperCase()}</span>
                  </>
                )}
              </button>
            </>
          ) : (
            <button type="button" className="reports-btn-primary" onClick={handleResetAndClose}>
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
