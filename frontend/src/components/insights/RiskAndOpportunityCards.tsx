import React from 'react';
import {
  AlertOctagon,
  TrendingUp,
  Eye,
  MessageSquare,
  Sliders,
  ArrowUpRight,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import type { Risk, Opportunity } from '../../types/insights';

interface RiskCardProps {
  risk: Risk;
  onViewEvidence: (risk: Risk) => void;
  onAskAI?: (risk: Risk) => void;
}

interface OpportunityCardProps {
  opportunity: Opportunity;
  onViewEvidence: (opportunity: Opportunity) => void;
  onRunScenario?: (opportunity: Opportunity) => void;
  onAskAI?: (opportunity: Opportunity) => void;
}

export const RiskCard: React.FC<RiskCardProps> = ({ risk, onViewEvidence, onAskAI }) => {
  const severityClass =
    risk.impact === 'High'
      ? 'insights-severity-high'
      : risk.impact === 'Medium'
        ? 'insights-severity-med'
        : 'insights-severity-low';

  return (
    <div className="insights-risk-card">
      <div className="insights-card-header">
        <span className={`insights-badge ${severityClass}`}>
          <AlertOctagon size={13} />
          <span>{risk.impact} Severity Risk</span>
        </span>
        {risk.confidence !== undefined && (
          <span className="insights-confidence-pill">
            <ShieldAlert size={11} />
            {Math.round(risk.confidence * 100)}% detection certainty
          </span>
        )}
      </div>

      <h4 className="insights-subcard-title">{risk.title}</h4>
      <p className="insights-card-summary">{risk.summary}</p>

      {/* Observed factual triggers */}
      <div className="insights-subcard-section">
        <div className="insights-subcard-section-label">Observed Data Patterns</div>
        <ul className="insights-evidence-list">
          {risk.observedData.map((pt, idx) => (
            <li key={idx} className="insights-evidence-item warning">
              {pt}
            </li>
          ))}
        </ul>
      </div>

      {/* Contributing Factors */}
      {risk.contributingFactors && risk.contributingFactors.length > 0 && (
        <div className="insights-tags-group">
          <span className="insights-tags-label">Contributing Factors:</span>
          <div className="insights-tags-container">
            {risk.contributingFactors.map((factor, idx) => (
              <span key={idx} className="insights-tag-risk">
                {factor}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="insights-card-footer">
        <button
          type="button"
          className="insights-action-btn primary"
          onClick={() => onViewEvidence(risk)}
        >
          <Eye size={13} />
          <span>View Evidence</span>
        </button>

        {onAskAI && (
          <button type="button" className="insights-action-btn ghost" onClick={() => onAskAI(risk)}>
            <MessageSquare size={13} />
            <span>Investigate</span>
          </button>
        )}
      </div>
    </div>
  );
};

export const OpportunityCard: React.FC<OpportunityCardProps> = ({
  opportunity,
  onViewEvidence,
  onRunScenario,
  onAskAI,
}) => {
  return (
    <div className="insights-opportunity-card">
      <div className="insights-card-header">
        <span className="insights-badge insights-badge-opportunity">
          <TrendingUp size={13} />
          <span>Growth Opportunity</span>
        </span>
        {opportunity.potentialUpside && (
          <span className="insights-upside-pill">
            <ArrowUpRight size={12} />
            {opportunity.potentialUpside}
          </span>
        )}
      </div>

      <h4 className="insights-subcard-title">{opportunity.title}</h4>
      <p className="insights-card-summary">{opportunity.summary}</p>

      {/* Supporting Data Points */}
      <div className="insights-subcard-section">
        <div className="insights-subcard-section-label">Observed Evidence</div>
        <ul className="insights-evidence-list">
          {opportunity.observedData.map((pt, idx) => (
            <li key={idx} className="insights-evidence-item success">
              {pt}
            </li>
          ))}
        </ul>
      </div>

      {/* Key Drivers & Regions */}
      {opportunity.targetRegions && opportunity.targetRegions.length > 0 && (
        <div className="insights-tags-group">
          <span className="insights-tags-label">Target Segments:</span>
          <div className="insights-tags-container">
            {opportunity.targetRegions.map((region, idx) => (
              <span key={idx} className="insights-tag-opp">
                {region}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="insights-card-footer">
        {onRunScenario && (
          <button
            type="button"
            className="insights-action-btn run-scenario"
            onClick={() => onRunScenario(opportunity)}
          >
            <Sliders size={13} />
            <span>Simulate Scenario</span>
          </button>
        )}

        <button
          type="button"
          className="insights-action-btn secondary"
          onClick={() => onViewEvidence(opportunity)}
        >
          <Eye size={13} />
          <span>Evidence</span>
        </button>

        {onAskAI && (
          <button
            type="button"
            className="insights-action-btn ghost"
            onClick={() => onAskAI(opportunity)}
          >
            <Sparkles size={13} />
            <span>Ask AI</span>
          </button>
        )}
      </div>
    </div>
  );
};
