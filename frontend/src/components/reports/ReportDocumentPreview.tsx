import React, { useState } from 'react';
import {
  Building2,
  Database,
  Calendar,
  ShieldCheck,
  Sliders,
  CheckCircle2,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Sparkles,
  Info,
} from 'lucide-react';
import type { ReportSpecification, ReportSectionType } from '../../types/reports';
import type { Insight } from '../../types/insights';
import { InsightCard } from '../insights/InsightCard';
import { RiskCard, OpportunityCard } from '../insights/RiskAndOpportunityCards';
import { RecommendationCard } from '../insights/RecommendationCard';
import { EvidencePanel, type ExplainableItem } from '../insights/EvidencePanel';
import { SelfFormingLineChart, SelfFormingBarChart } from '../animatedGlowVisualizations';

interface ReportDocumentPreviewProps {
  spec: ReportSpecification;
  highlightSectionId?: string;
  onOpenVisualization?: (insight: Insight) => void;
  onAskAI?: (item: ExplainableItem) => void;
  isPrintMode?: boolean;
}

export const ReportDocumentPreview: React.FC<ReportDocumentPreviewProps> = ({
  spec,
  highlightSectionId,
  onOpenVisualization,
  onAskAI,
}) => {
  // Explainability drawer state
  const [drawerItem, setDrawerItem] = useState<ExplainableItem | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const handleOpenEvidence = (item: ExplainableItem) => {
    setDrawerItem(item);
    setIsDrawerOpen(true);
  };

  const handleCloseEvidence = () => {
    setIsDrawerOpen(false);
    setDrawerItem(null);
  };

  // Sort sections by their configured order
  const activeSections = [...spec.sections]
    .filter((s) => s.enabled)
    .sort((a, b) => a.order - b.order);

  // Section renderer helper
  const renderSection = (type: ReportSectionType, secId: string) => {
    const isHighlighted = highlightSectionId === secId;

    switch (type) {
      case 'cover':
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-cover ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-cover-brand">
              <div className="report-cover-badge">
                <Sparkles size={13} />
                <span>AI Data Analyst Publication</span>
              </div>
              <span className="report-cover-org">{spec.cover.organization}</span>
            </div>

            <h1 className="report-cover-title">{spec.cover.title}</h1>
            <p className="report-cover-subtitle">{spec.cover.subtitle}</p>

            <div className="report-cover-meta-grid">
              <div className="report-cover-meta-item">
                <Database size={14} className="report-meta-icon" />
                <div>
                  <span className="report-cover-meta-label">Data Source</span>
                  <span className="report-cover-meta-val">{spec.cover.datasetName}</span>
                </div>
              </div>

              <div className="report-cover-meta-item">
                <Calendar size={14} className="report-meta-icon" />
                <div>
                  <span className="report-cover-meta-label">Evaluation Period</span>
                  <span className="report-cover-meta-val">{spec.cover.periodLabel}</span>
                </div>
              </div>

              <div className="report-cover-meta-item">
                <Building2 size={14} className="report-meta-icon" />
                <div>
                  <span className="report-cover-meta-label">Prepared By</span>
                  <span className="report-cover-meta-val">{spec.author}</span>
                </div>
              </div>

              <div className="report-cover-meta-item">
                <ShieldCheck size={14} className="report-meta-icon" />
                <div>
                  <span className="report-cover-meta-label">Generated Date</span>
                  <span className="report-cover-meta-val">{spec.cover.generatedDate}</span>
                </div>
              </div>
            </div>

            <div className="report-cover-footer-note">
              <span>{spec.cover.confidentialityNotice}</span>
            </div>
          </div>
        );

      case 'summary':
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-section ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-doc-section-header">
              <span className="report-section-num">01</span>
              <div>
                <h2 className="report-doc-section-title">Executive Summary</h2>
                <p className="report-doc-section-desc">
                  Synthesized narrative overview of observed business trends and market drivers.
                </p>
              </div>
            </div>

            <div className="report-summary-box">
              <p className="report-summary-narrative">{spec.summary.narrative}</p>

              <div className="report-highlights-title">Key Executive Findings:</div>
              <ul className="report-highlights-list">
                {spec.summary.keyHighlights.map((hl, idx) => (
                  <li key={idx} className="report-highlight-item">
                    <CheckCircle2 size={14} className="report-highlight-check" />
                    <span>{hl}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        );

      case 'kpis':
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-section ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-doc-section-header">
              <span className="report-section-num">02</span>
              <div>
                <h2 className="report-doc-section-title">Business Health Summary</h2>
                <p className="report-doc-section-desc">
                  Audited quantitative performance indicators across the evaluation window.
                </p>
              </div>
            </div>

            <div className="report-doc-kpi-grid">
              {spec.kpis.map((kpi) => (
                <div key={kpi.id} className="report-doc-kpi-card">
                  <div className="report-doc-kpi-top">
                    <span className="report-doc-kpi-label">{kpi.label}</span>
                    {kpi.trend && (
                      <span className={`insights-kpi-trend ${kpi.direction || 'neutral'}`}>
                        {kpi.direction === 'up' && <ArrowUpRight size={12} />}
                        {kpi.direction === 'down' && <ArrowDownRight size={12} />}
                        {kpi.direction === 'neutral' && <Minus size={12} />}
                        {kpi.trend}
                      </span>
                    )}
                  </div>
                  <div className="report-doc-kpi-val">{kpi.value}</div>
                  {kpi.subValue && <div className="report-doc-kpi-sub">{kpi.subValue}</div>}
                </div>
              ))}
            </div>
          </div>
        );

      case 'visualizations':
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-section ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-doc-section-header">
              <span className="report-section-num">03</span>
              <div>
                <h2 className="report-doc-section-title">High-Signal Visualizations</h2>
                <p className="report-doc-section-desc">
                  Empirical trajectory trends and geographic distribution curves.
                </p>
              </div>
            </div>

            <div className="report-doc-viz-stack">
              {spec.visualizations.map((viz) => (
                <div key={viz.id} className="report-doc-viz-card">
                  <div className="report-doc-viz-header">
                    <div>
                      <h3 className="report-doc-viz-title">{viz.title}</h3>
                      {viz.description && <p className="report-doc-viz-desc">{viz.description}</p>}
                    </div>
                    <span className="report-viz-type-badge">{viz.chartType} Chart</span>
                  </div>

                  <div className="report-doc-chart-wrapper">
                    {viz.chartType === 'Line' && (
                      <SelfFormingLineChart
                        data={viz.dataPoints}
                        ariaLabel={viz.title}
                        isArea={true}
                      />
                    )}
                    {viz.chartType === 'Bar' && (
                      <SelfFormingBarChart data={viz.dataPoints} ariaLabel={viz.title} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );

      case 'insights':
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-section ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-doc-section-header">
              <span className="report-section-num">04</span>
              <div>
                <h2 className="report-doc-section-title">Key Business Insights</h2>
                <p className="report-doc-section-desc">
                  Empirical records paired with explainable model interpretations.
                </p>
              </div>
            </div>

            <div className="report-doc-cards-grid">
              {spec.insights.map((ins) => (
                <InsightCard
                  key={ins.id}
                  insight={ins}
                  onViewEvidence={handleOpenEvidence}
                  onOpenVisualization={onOpenVisualization}
                  onAskAI={onAskAI}
                />
              ))}
            </div>
          </div>
        );

      case 'risks':
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-section ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-doc-section-header">
              <span className="report-section-num">05</span>
              <div>
                <h2 className="report-doc-section-title">Detected Risks & Vulnerabilities</h2>
                <p className="report-doc-section-desc">
                  Structural revenue leakage and retention vulnerabilities identified by anomaly
                  models.
                </p>
              </div>
            </div>

            <div className="report-doc-cards-grid">
              {spec.risks.map((risk) => (
                <RiskCard
                  key={risk.id}
                  risk={risk}
                  onViewEvidence={handleOpenEvidence}
                  onAskAI={onAskAI}
                />
              ))}
            </div>
          </div>
        );

      case 'opportunities':
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-section ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-doc-section-header">
              <span className="report-section-num">06</span>
              <div>
                <h2 className="report-doc-section-title">Strategic Growth Opportunities</h2>
                <p className="report-doc-section-desc">
                  High-leverage expansion vectors and addressable enterprise market pockets.
                </p>
              </div>
            </div>

            <div className="report-doc-cards-grid">
              {spec.opportunities.map((opp) => (
                <OpportunityCard
                  key={opp.id}
                  opportunity={opp}
                  onViewEvidence={handleOpenEvidence}
                  onAskAI={onAskAI}
                />
              ))}
            </div>
          </div>
        );

      case 'recommendations':
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-section ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-doc-section-header">
              <span className="report-section-num">07</span>
              <div>
                <h2 className="report-doc-section-title">Action Recommendations</h2>
                <p className="report-doc-section-desc">
                  Evidence-backed execution steps with transparent boundary assumptions.
                </p>
              </div>
            </div>

            <div className="report-doc-cards-grid">
              {spec.recommendations.map((rec) => (
                <RecommendationCard
                  key={rec.id}
                  recommendation={rec}
                  onViewEvidence={handleOpenEvidence}
                  onAskAI={onAskAI}
                />
              ))}
            </div>
          </div>
        );

      case 'what_if':
        if (!spec.scenario) return null;
        return (
          <div
            key={secId}
            id={secId}
            className={`report-doc-section ${isHighlighted ? 'doc-highlight' : ''}`}
          >
            <div className="report-doc-section-header">
              <span className="report-section-num">08</span>
              <div>
                <h2 className="report-doc-section-title">What-If Scenario Simulation</h2>
                <p className="report-doc-section-desc">
                  Forward-looking decision modeling based on price elasticity & CAC curves.
                </p>
              </div>
            </div>

            <div className="report-doc-scenario-box">
              <div className="report-scenario-header">
                <div className="report-scenario-title-wrap">
                  <Sliders size={16} className="report-scenario-icon" />
                  <h3>{spec.scenario.scenarioName}</h3>
                </div>
                <span className="report-scenario-badge">Model Output / Projected Outcome</span>
              </div>

              <p className="report-scenario-narrative">{spec.scenario.narrative}</p>

              {/* Scenario KPI Comparison Cards */}
              <div className="report-scenario-kpis">
                <div className="report-scenario-kpi-item highlight">
                  <span className="report-scenario-kpi-lbl">Projected Revenue</span>
                  <span className="report-scenario-kpi-val">
                    {spec.scenario.projection.projectedRevenue.projected}
                  </span>
                  <div className="report-scenario-kpi-sub">
                    <span>Baseline: {spec.scenario.projection.projectedRevenue.baseline}</span>
                    <span className="report-scenario-kpi-delta up">
                      {spec.scenario.projection.projectedRevenue.delta}
                    </span>
                  </div>
                </div>

                <div className="report-scenario-kpi-item">
                  <span className="report-scenario-kpi-lbl">Estimated Net Financial Impact</span>
                  <span className="report-scenario-kpi-val text-green">
                    {spec.scenario.projection.netImpact}
                  </span>
                  <div className="report-scenario-kpi-sub">
                    <span>Confidence: {spec.scenario.projection.confidenceInterval}</span>
                  </div>
                </div>

                <div className="report-scenario-kpi-item">
                  <span className="report-scenario-kpi-lbl">Projected Customer Volume</span>
                  <span className="report-scenario-kpi-val">
                    {spec.scenario.projection.projectedCustomers.projected}
                  </span>
                  <div className="report-scenario-kpi-sub">
                    <span>Baseline: {spec.scenario.projection.projectedCustomers.baseline}</span>
                    <span className="report-scenario-kpi-delta up">
                      {spec.scenario.projection.projectedCustomers.delta}
                    </span>
                  </div>
                </div>
              </div>

              {/* Explicit Disclaimer */}
              <div className="report-scenario-disclaimer">
                <Info size={13} className="report-scenario-disc-icon" />
                <span>
                  <strong>Scenario Notice:</strong> Figures reflect simulated model projections
                  generated by calibrated elasticity coefficients. They represent estimated
                  directional outcomes under stable macroeconomic assumptions, not guaranteed
                  business results.
                </span>
              </div>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <article className="report-doc-surface" aria-label={`Report Document: ${spec.title}`}>
      {activeSections.map((sec) => renderSection(sec.type, sec.id))}

      {/* Embedded Explainability Drawer */}
      <EvidencePanel
        isOpen={isDrawerOpen}
        item={drawerItem}
        datasetName={spec.dataset}
        timePeriod={spec.dateRange.label}
        onClose={handleCloseEvidence}
        onAskAI={onAskAI}
      />
    </article>
  );
};
