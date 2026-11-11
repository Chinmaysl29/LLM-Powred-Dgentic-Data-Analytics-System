import React, { useEffect } from 'react';
import {
  X,
  Database,
  Calendar,
  Eye,
  Sparkles,
  BarChart2,
  MessageSquare,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import type {
  Insight,
  Risk,
  Opportunity,
  Recommendation,
  InsightMetric,
  VisualizationReference,
} from '../../types/insights';

export type ExplainableItem = Insight | Risk | Opportunity | Recommendation;

interface EvidencePanelProps {
  isOpen: boolean;
  item: ExplainableItem | null;
  datasetName?: string;
  timePeriod?: string;
  onClose: () => void;
  onOpenVisualization?: (ref: VisualizationReference) => void;
  onAskAI?: (item: ExplainableItem) => void;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  isOpen,
  item,
  datasetName = 'Sales Dataset',
  timePeriod = 'Last 30 Days',
  onClose,
  onOpenVisualization,
  onAskAI,
}) => {
  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen || !item) return null;

  // Type identification helpers
  const isInsight = 'type' in item;
  const isRisk = 'contributingFactors' in item && 'impact' in item && !('effort' in item);
  const isOpportunity = 'potentialUpside' in item;
  const isRecommendation = 'supportingEvidence' in item && 'effort' in item;

  // Extract observed evidence points
  const observedPoints: string[] = isInsight
    ? (item as Insight).observedEvidence
    : isRisk
      ? (item as Risk).observedData
      : isOpportunity
        ? (item as Opportunity).observedData
        : isRecommendation
          ? (item as Recommendation).supportingEvidence
          : [];

  // Extract interpretation or summary
  const interpretationText = isInsight ? (item as Insight).derivedInterpretation : item.summary;

  // Extract metrics table
  const metrics: InsightMetric[] = isInsight
    ? (item as Insight).metrics || []
    : isRisk
      ? (item as Risk).evidence || []
      : isOpportunity
        ? (item as Opportunity).evidence || []
        : [];

  // Extract visualization reference
  const visRef: VisualizationReference | undefined = item.visualizationReference;

  return (
    <div className="insights-drawer-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="insights-drawer" onClick={(e) => e.stopPropagation()} tabIndex={-1}>
        {/* Drawer Header */}
        <div className="insights-drawer-header">
          <div className="insights-drawer-meta">
            <span className="insights-drawer-tag">
              <Eye size={13} />
              <span>Evidence & Explainability</span>
            </span>
            {item.confidence !== undefined && (
              <span className="insights-confidence-pill">
                <Sparkles size={11} />
                {Math.round(item.confidence * 100)}% Confidence
              </span>
            )}
          </div>
          <button
            type="button"
            className="insights-drawer-close"
            onClick={onClose}
            aria-label="Close evidence drawer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Drawer Scrollable Content */}
        <div className="insights-drawer-body">
          <h2 className="insights-drawer-title">{item.title}</h2>

          {/* Data Provenance & Context Banner */}
          <div className="insights-provenance-box">
            <div className="insights-provenance-item">
              <Database size={13} className="insights-provenance-icon" />
              <div>
                <span className="insights-provenance-label">Data Source:</span>
                <span className="insights-provenance-val">{item.datasetName || datasetName}</span>
              </div>
            </div>
            <div className="insights-provenance-item">
              <Calendar size={13} className="insights-provenance-icon" />
              <div>
                <span className="insights-provenance-label">Time Scope:</span>
                <span className="insights-provenance-val">{item.timePeriod || timePeriod}</span>
              </div>
            </div>
          </div>

          {/* Section 1: Raw Observed Factual Data */}
          <div className="insights-drawer-section">
            <div className="insights-drawer-section-heading">
              <CheckCircle2 size={15} className="insights-box-icon text-cyan" />
              <h3>Directly Observed Data</h3>
            </div>
            <p className="insights-drawer-sub">
              Empirical measurements extracted directly from the verified dataset records without
              extrapolation:
            </p>
            <ul className="insights-drawer-list">
              {observedPoints.map((point, idx) => (
                <li key={idx} className="insights-drawer-list-item">
                  <span className="insights-bullet-dot" />
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Section 2: Model Interpretation & Explainability */}
          <div className="insights-drawer-section">
            <div className="insights-drawer-section-heading">
              <Sparkles size={15} className="insights-box-icon purple" />
              <h3>Derived Model Interpretation</h3>
            </div>
            <div className="insights-interpretation-drawer-box">
              <p>{interpretationText}</p>
            </div>
          </div>

          {/* Section 3: Supporting Metrics Table */}
          {metrics.length > 0 && (
            <div className="insights-drawer-section">
              <div className="insights-drawer-section-heading">
                <BarChart2 size={15} className="insights-box-icon text-blue" />
                <h3>Supporting Quantitative Metrics</h3>
              </div>
              <div className="insights-metrics-table-wrapper">
                <table className="insights-metrics-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Value</th>
                      <th>Period Shift</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.map((m, idx) => (
                      <tr key={idx}>
                        <td className="insights-metric-name">{m.label}</td>
                        <td className="insights-metric-value">{m.value}</td>
                        <td className="insights-metric-delta">
                          {m.change ? (
                            <span className={`insights-delta-chip ${m.direction || 'neutral'}`}>
                              {m.direction === 'up' && <ArrowUpRight size={11} />}
                              {m.direction === 'down' && <ArrowDownRight size={11} />}
                              {m.direction === 'neutral' && <Minus size={11} />}
                              {m.change}
                            </span>
                          ) : (
                            <span className="insights-delta-na">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Section 4: Underlying Drivers & Contributing Factors */}
          {isInsight && (item as Insight).drivers && (item as Insight).drivers.length > 0 && (
            <div className="insights-drawer-section">
              <div className="insights-drawer-section-heading">
                <AlertTriangle size={15} className="insights-box-icon text-amber" />
                <h3>Identified Drivers</h3>
              </div>
              <div className="insights-tags-container">
                {(item as Insight).drivers.map((d, idx) => (
                  <span key={idx} className="insights-tag-driver">
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Section 5: Connected Visualization Reference */}
          {visRef && (
            <div className="insights-drawer-section">
              <div className="insights-drawer-section-heading">
                <BarChart2 size={15} className="insights-box-icon text-indigo" />
                <h3>Connected Visualization</h3>
              </div>
              <div className="insights-vis-preview-box">
                <div>
                  <div className="insights-vis-preview-title">{visRef.title}</div>
                  <div className="insights-vis-preview-meta">
                    Type: <strong>{visRef.chartType} Chart</strong>
                    {visRef.xAxis && (
                      <>
                        {' '}
                        • X-Axis: <strong>{visRef.xAxis}</strong>
                      </>
                    )}
                    {visRef.yAxis && (
                      <>
                        {' '}
                        • Y-Axis: <strong>{visRef.yAxis}</strong>
                      </>
                    )}
                  </div>
                </div>
                {onOpenVisualization && (
                  <button
                    type="button"
                    className="insights-action-btn secondary"
                    onClick={() => {
                      onClose();
                      onOpenVisualization(visRef);
                    }}
                  >
                    <BarChart2 size={13} />
                    <span>Open in Visualizer</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Drawer Action Footer */}
        <div className="insights-drawer-footer">
          {onAskAI && (
            <button
              type="button"
              className="insights-drawer-btn ask-ai"
              onClick={() => {
                onClose();
                onAskAI(item);
              }}
            >
              <MessageSquare size={14} />
              <span>Ask AI About This Evidence</span>
            </button>
          )}

          <button type="button" className="insights-drawer-btn close" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
