import React from 'react';
import {
  CheckCircle2,
  Clock,
  Zap,
  Sliders,
  Eye,
  MessageSquare,
  HelpCircle,
  FileCheck,
} from 'lucide-react';
import type { Recommendation } from '../../types/insights';

interface RecommendationCardProps {
  recommendation: Recommendation;
  onViewEvidence: (recommendation: Recommendation) => void;
  onRunScenario?: (recommendation: Recommendation) => void;
  onAskAI?: (recommendation: Recommendation) => void;
}

export const RecommendationCard: React.FC<RecommendationCardProps> = ({
  recommendation,
  onViewEvidence,
  onRunScenario,
  onAskAI,
}) => {
  const effortClass =
    recommendation.effort === 'Low'
      ? 'insights-effort-low'
      : recommendation.effort === 'Medium'
        ? 'insights-effort-med'
        : 'insights-effort-high';

  return (
    <div className="insights-recommendation-card">
      <div className="insights-card-header">
        <div className="insights-card-meta">
          <span className="insights-badge insights-badge-rec">
            <CheckCircle2 size={13} />
            <span>Recommended Action</span>
          </span>
          <span className="insights-impact-badge" title={recommendation.expectedImpact}>
            <Zap size={11} />
            <span>High Impact</span>
          </span>
        </div>
        {recommendation.effort && (
          <span className={`insights-effort-badge ${effortClass}`}>
            <Clock size={11} />
            <span>{recommendation.effort} Effort</span>
          </span>
        )}
      </div>

      <h4 className="insights-subcard-title">{recommendation.title}</h4>
      <p className="insights-card-summary">{recommendation.summary || recommendation.rationale}</p>

      {/* Supporting Evidence */}
      <div className="insights-subcard-section">
        <div className="insights-subcard-section-label">
          <FileCheck size={12} className="insights-box-icon" />
          <span>Underlying Evidence</span>
        </div>
        <ul className="insights-evidence-list">
          {recommendation.supportingEvidence.map((point, idx) => (
            <li key={idx} className="insights-evidence-item">
              {point}
            </li>
          ))}
        </ul>
      </div>

      {/* Assumptions & Caveats */}
      {recommendation.assumptions && recommendation.assumptions.length > 0 && (
        <div className="insights-assumptions-box">
          <div className="insights-assumptions-title">
            <HelpCircle size={11} />
            <span>Key Assumptions & Boundary Conditions</span>
          </div>
          <ul className="insights-assumptions-list">
            {recommendation.assumptions.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Card Action Footer */}
      <div className="insights-card-footer">
        {recommendation.scenarioVariables && onRunScenario && (
          <button
            type="button"
            className="insights-action-btn run-scenario"
            onClick={() => onRunScenario(recommendation)}
            title="Simulate outcome using recommended parameters"
          >
            <Sliders size={13} />
            <span>Simulate What-If</span>
          </button>
        )}

        <button
          type="button"
          className="insights-action-btn primary"
          onClick={() => onViewEvidence(recommendation)}
          title="Inspect full supporting evidence"
        >
          <Eye size={13} />
          <span>View Evidence</span>
        </button>

        {onAskAI && (
          <button
            type="button"
            className="insights-action-btn ghost"
            onClick={() => onAskAI(recommendation)}
            title="Ask AI to evaluate execution plan"
          >
            <MessageSquare size={13} />
            <span>Ask AI</span>
          </button>
        )}
      </div>
    </div>
  );
};
