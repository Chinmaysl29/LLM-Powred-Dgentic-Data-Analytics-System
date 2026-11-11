import React from 'react';
import {
  TrendingUp,
  Workflow,
  AlertTriangle,
  Sliders,
  RefreshCw,
  GitFork,
  Eye,
  BarChart2,
  MessageSquare,
  Sparkles,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from 'lucide-react';
import type { Insight, InsightType } from '../../types/insights';

interface InsightCardProps {
  insight: Insight;
  onViewEvidence: (insight: Insight) => void;
  onOpenVisualization?: (insight: Insight) => void;
  onAskAI?: (insight: Insight) => void;
}

const TYPE_CONFIG: Record<
  InsightType,
  { label: string; icon: React.ReactNode; badgeClass: string }
> = {
  trend: {
    label: 'Trend',
    icon: <TrendingUp size={13} />,
    badgeClass: 'insights-badge-trend',
  },
  pattern: {
    label: 'Pattern',
    icon: <Workflow size={13} />,
    badgeClass: 'insights-badge-pattern',
  },
  anomaly: {
    label: 'Anomaly',
    icon: <AlertTriangle size={13} />,
    badgeClass: 'insights-badge-anomaly',
  },
  driver: {
    label: 'Driver',
    icon: <Sliders size={13} />,
    badgeClass: 'insights-badge-driver',
  },
  change: {
    label: 'Change',
    icon: <RefreshCw size={13} />,
    badgeClass: 'insights-badge-change',
  },
  correlation: {
    label: 'Correlation',
    icon: <GitFork size={13} />,
    badgeClass: 'insights-badge-correlation',
  },
};

export const InsightCard: React.FC<InsightCardProps> = ({
  insight,
  onViewEvidence,
  onOpenVisualization,
  onAskAI,
}) => {
  const config = TYPE_CONFIG[insight.type] || TYPE_CONFIG.trend;

  return (
    <div className="insights-card">
      {/* Top Meta Bar */}
      <div className="insights-card-header">
        <div className="insights-card-meta">
          <span className={`insights-badge ${config.badgeClass}`}>
            {config.icon}
            <span>{config.label}</span>
          </span>
          {insight.confidence !== undefined && (
            <span className="insights-confidence-pill" title="Model confidence score">
              <Sparkles size={11} className="insights-sparkle-icon" />
              {Math.round(insight.confidence * 100)}% confidence
            </span>
          )}
        </div>
        {insight.timePeriod && <span className="insights-card-period">{insight.timePeriod}</span>}
      </div>

      {/* Main Title & Executive Summary */}
      <h3 className="insights-card-title">{insight.title}</h3>
      <p className="insights-card-summary">{insight.summary}</p>

      {/* Key Supporting Metric Chips */}
      {insight.metrics && insight.metrics.length > 0 && (
        <div className="insights-metric-strip">
          {insight.metrics.map((metric, idx) => (
            <div key={idx} className="insights-metric-pill">
              <span className="insights-metric-pill-label">{metric.label}:</span>
              <span className="insights-metric-pill-val">{metric.value}</span>
              {metric.change && (
                <span className={`insights-metric-pill-change ${metric.direction || 'neutral'}`}>
                  {metric.direction === 'up' && <ArrowUpRight size={11} />}
                  {metric.direction === 'down' && <ArrowDownRight size={11} />}
                  {metric.direction === 'neutral' && <Minus size={11} />}
                  {metric.change}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Structured Evidence vs. Interpretation Split */}
      <div className="insights-evidence-box">
        <div className="insights-evidence-header">
          <Eye size={13} className="insights-box-icon" />
          <span>Observed Evidence</span>
        </div>
        <ul className="insights-evidence-list">
          {insight.observedEvidence.map((point, idx) => (
            <li key={idx} className="insights-evidence-item">
              {point}
            </li>
          ))}
        </ul>
      </div>

      <div className="insights-interpretation-box">
        <div className="insights-interpretation-header">
          <Sparkles size={13} className="insights-box-icon purple" />
          <span>Derived Interpretation</span>
        </div>
        <p className="insights-interpretation-text">{insight.derivedInterpretation}</p>
      </div>

      {/* Card Action Footer */}
      <div className="insights-card-footer">
        <button
          type="button"
          className="insights-action-btn primary"
          onClick={() => onViewEvidence(insight)}
          title="Open explainability & evidence drawer"
        >
          <Eye size={13} />
          <span>View Evidence</span>
        </button>

        {insight.visualizationReference && onOpenVisualization && (
          <button
            type="button"
            className="insights-action-btn secondary"
            onClick={() => onOpenVisualization(insight)}
            title="Open interactive chart in Visualizations page"
          >
            <BarChart2 size={13} />
            <span>Open Chart</span>
          </button>
        )}

        {onAskAI && (
          <button
            type="button"
            className="insights-action-btn ghost"
            onClick={() => onAskAI(insight)}
            title="Deep dive in AI Analysis"
          >
            <MessageSquare size={13} />
            <span>Ask AI</span>
          </button>
        )}
      </div>
    </div>
  );
};
