import React, { useState, useMemo } from 'react';
import {
  Sliders,
  RotateCcw,
  ArrowUpRight,
  ArrowDownRight,
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  Info,
  MessageSquare,
} from 'lucide-react';
import type { ScenarioInputVariables, ScenarioProjection } from '../../types/insights';
import { calculateScenarioProjection } from '../../services/insightsService';

interface WhatIfSimulatorProps {
  datasetId?: string;
  initialVariables?: Partial<ScenarioInputVariables>;
  onAskAI?: (projection: ScenarioProjection, variables: ScenarioInputVariables) => void;
  isCompact?: boolean;
}

const DEFAULT_VARIABLES: ScenarioInputVariables = {
  marketingSpendDelta: 0,
  priceDelta: 0,
  churnDelta: 0,
  marketingSpendDeltaPct: 0,
  priceAdjustmentPct: 0,
  churnRateDeltaPct: 0,
  targetRegion: 'All',
  targetCategory: 'All',
  timeHorizon: 'quarterly',
};

const PRESETS = [
  {
    name: 'Growth Push',
    desc: '+25% marketing, +5% price',
    vars: {
      marketingSpendDelta: 25,
      marketingSpendDeltaPct: 25,
      priceDelta: 5,
      priceAdjustmentPct: 5,
      churnDelta: 0,
      churnRateDeltaPct: 0,
    },
  },
  {
    name: 'Margin Expansion',
    desc: '+12% price, -10% churn',
    vars: {
      marketingSpendDelta: 0,
      marketingSpendDeltaPct: 0,
      priceDelta: 12,
      priceAdjustmentPct: 12,
      churnDelta: -10,
      churnRateDeltaPct: -10,
    },
  },
  {
    name: 'Retention Focus',
    desc: '-20% churn, -5% price',
    vars: {
      marketingSpendDelta: -10,
      marketingSpendDeltaPct: -10,
      priceDelta: -5,
      priceAdjustmentPct: -5,
      churnDelta: -20,
      churnRateDeltaPct: -20,
    },
  },
];

export const WhatIfSimulator: React.FC<WhatIfSimulatorProps> = ({
  datasetId = 'sales',
  initialVariables,
  onAskAI,
  isCompact = false,
}) => {
  const [variables, setVariables] = useState<ScenarioInputVariables>({
    ...DEFAULT_VARIABLES,
    ...initialVariables,
  });

  const spendPct = variables.marketingSpendDeltaPct ?? variables.marketingSpendDelta ?? 0;
  const pricePct = variables.priceAdjustmentPct ?? variables.priceDelta ?? 0;
  const churnPct = variables.churnRateDeltaPct ?? variables.churnDelta ?? 0;

  const projection: ScenarioProjection = useMemo(() => {
    return calculateScenarioProjection(datasetId, variables);
  }, [datasetId, variables]);

  const handleSliderChange = (field: keyof ScenarioInputVariables, val: number) => {
    setVariables((prev) => ({ ...prev, [field]: val }));
  };

  const handleSelectChange = (field: keyof ScenarioInputVariables, val: string) => {
    setVariables((prev) => ({ ...prev, [field]: val }));
  };

  const handleReset = () => {
    setVariables(DEFAULT_VARIABLES);
  };

  const handleApplyPreset = (presetVars: Partial<ScenarioInputVariables>) => {
    setVariables((prev) => ({ ...prev, ...presetVars }));
  };

  const isNetPositive = projection.netImpact.startsWith('+');

  return (
    <div className={`insights-simulator-container ${isCompact ? 'compact' : 'full'}`}>
      {/* Simulator Header */}
      <div className="insights-sim-header">
        <div className="insights-sim-header-title">
          <div className="insights-sim-icon-box">
            <Sliders size={18} />
          </div>
          <div>
            <h3>What-If Scenario Simulator</h3>
            <p>
              Model forward-looking business outcomes using verified price elasticity & CAC response
              curves.
            </p>
          </div>
        </div>

        {/* Quick Presets */}
        <div className="insights-sim-preset-bar">
          <span className="insights-sim-preset-label">Quick Presets:</span>
          {PRESETS.map((p, idx) => (
            <button
              key={idx}
              type="button"
              className="insights-sim-preset-btn"
              onClick={() => handleApplyPreset(p.vars)}
              title={p.desc}
            >
              {p.name}
            </button>
          ))}
          <button
            type="button"
            className="insights-sim-reset-btn"
            onClick={handleReset}
            title="Reset variables to zero"
          >
            <RotateCcw size={12} />
            <span>Reset</span>
          </button>
        </div>
      </div>

      {/* Main Simulation Workspace Grid */}
      <div className="insights-sim-grid">
        {/* Left Column: Decision Variables / Sliders */}
        <div className="insights-sim-controls-pane">
          <div className="insights-sim-pane-title">Scenario Variables</div>

          {/* Slider 1: Marketing Spend Delta */}
          <div className="insights-slider-group">
            <div className="insights-slider-header">
              <label htmlFor="spend-slider">Marketing Spend Shift</label>
              <span
                className={`insights-slider-val ${spendPct > 0 ? 'pos' : spendPct < 0 ? 'neg' : ''}`}
              >
                {spendPct > 0 ? `+${spendPct}%` : `${spendPct}%`}
              </span>
            </div>
            <input
              id="spend-slider"
              type="range"
              min="-50"
              max="100"
              step="5"
              value={spendPct}
              onChange={(e) => handleSliderChange('marketingSpendDeltaPct', Number(e.target.value))}
              className="insights-slider"
            />
            <div className="insights-slider-scale">
              <span>-50%</span>
              <span>0% (Baseline)</span>
              <span>+100%</span>
            </div>
          </div>

          {/* Slider 2: Price Adjustment */}
          <div className="insights-slider-group">
            <div className="insights-slider-header">
              <label htmlFor="price-slider">Price Adjustment</label>
              <span
                className={`insights-slider-val ${pricePct > 0 ? 'pos' : pricePct < 0 ? 'neg' : ''}`}
              >
                {pricePct > 0 ? `+${pricePct}%` : `${pricePct}%`}
              </span>
            </div>
            <input
              id="price-slider"
              type="range"
              min="-30"
              max="50"
              step="2.5"
              value={pricePct}
              onChange={(e) => handleSliderChange('priceAdjustmentPct', Number(e.target.value))}
              className="insights-slider"
            />
            <div className="insights-slider-scale">
              <span>-30%</span>
              <span>0% (Current)</span>
              <span>+50%</span>
            </div>
          </div>

          {/* Slider 3: Churn Rate Delta */}
          <div className="insights-slider-group">
            <div className="insights-slider-header">
              <label htmlFor="churn-slider">Target Churn Shift</label>
              <span
                className={`insights-slider-val ${churnPct < 0 ? 'pos' : churnPct > 0 ? 'neg' : ''}`}
              >
                {churnPct > 0 ? `+${churnPct}%` : `${churnPct}%`}
              </span>
            </div>
            <input
              id="churn-slider"
              type="range"
              min="-50"
              max="50"
              step="5"
              value={churnPct}
              onChange={(e) => handleSliderChange('churnRateDeltaPct', Number(e.target.value))}
              className="insights-slider"
            />
            <div className="insights-slider-scale">
              <span>-50% (Retention)</span>
              <span>0%</span>
              <span>+50% (At Risk)</span>
            </div>
          </div>

          {/* Segment Dropdowns */}
          <div className="insights-sim-dropdowns-row">
            <div className="insights-sim-field">
              <label htmlFor="sim-region">Target Region</label>
              <select
                id="sim-region"
                className="insights-select"
                value={variables.targetRegion}
                onChange={(e) => handleSelectChange('targetRegion', e.target.value)}
              >
                <option value="All">All Regions</option>
                <option value="North America">North America</option>
                <option value="Europe">Europe</option>
                <option value="Asia Pacific">Asia Pacific</option>
                <option value="Latin America">Latin America</option>
              </select>
            </div>

            <div className="insights-sim-field">
              <label htmlFor="sim-horizon">Simulation Horizon</label>
              <select
                id="sim-horizon"
                className="insights-select"
                value={variables.timeHorizon}
                onChange={(e) => handleSelectChange('timeHorizon', e.target.value)}
              >
                <option value="quarterly">Quarterly (3 Months)</option>
                <option value="annual">Annual (12 Months)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Right Column: Projected Outcomes & Impact Cards */}
        <div className="insights-sim-results-pane">
          <div className="insights-sim-pane-title">
            <span>Projected Business Outcomes</span>
            <span
              className={`insights-sim-risk-badge risk-${projection.riskAssessment.toLowerCase()}`}
            >
              {projection.riskAssessment === 'Low' && <CheckCircle2 size={12} />}
              {projection.riskAssessment === 'Moderate' && <AlertTriangle size={12} />}
              {projection.riskAssessment === 'Elevated' && <ShieldAlert size={12} />}
              <span>{projection.riskAssessment} Volatility Risk</span>
            </span>
          </div>

          {/* Outcome KPI Cards */}
          <div className="insights-sim-kpi-grid">
            {/* Projected Revenue */}
            <div className="insights-sim-kpi-card highlight">
              <div className="insights-sim-kpi-label">Projected Revenue</div>
              <div className="insights-sim-kpi-val">{projection.projectedRevenue.projected}</div>
              <div className="insights-sim-kpi-footer">
                <span className="insights-sim-kpi-base">
                  Baseline: {projection.projectedRevenue.baseline}
                </span>
                <span className={`insights-delta-chip ${projection.projectedRevenue.direction}`}>
                  {projection.projectedRevenue.direction === 'up' && <ArrowUpRight size={11} />}
                  {projection.projectedRevenue.direction === 'down' && <ArrowDownRight size={11} />}
                  {projection.projectedRevenue.delta}
                </span>
              </div>
            </div>

            {/* Net Impact */}
            <div className="insights-sim-kpi-card">
              <div className="insights-sim-kpi-label">Estimated Net Impact</div>
              <div className={`insights-sim-kpi-val ${isNetPositive ? 'text-green' : 'text-red'}`}>
                {projection.netImpact}
              </div>
              <div className="insights-sim-kpi-footer">
                <span className="insights-sim-kpi-base">Confidence Interval</span>
                <span className="insights-sim-kpi-ci">{projection.confidenceInterval}</span>
              </div>
            </div>

            {/* Projected Customers */}
            <div className="insights-sim-kpi-card">
              <div className="insights-sim-kpi-label">Projected Customers</div>
              <div className="insights-sim-kpi-val">{projection.projectedCustomers.projected}</div>
              <div className="insights-sim-kpi-footer">
                <span className="insights-sim-kpi-base">
                  Baseline: {projection.projectedCustomers.baseline}
                </span>
                <span className={`insights-delta-chip ${projection.projectedCustomers.direction}`}>
                  {projection.projectedCustomers.direction === 'up' && <ArrowUpRight size={11} />}
                  {projection.projectedCustomers.direction === 'down' && (
                    <ArrowDownRight size={11} />
                  )}
                  {projection.projectedCustomers.delta}
                </span>
              </div>
            </div>

            {/* Projected CAC */}
            <div className="insights-sim-kpi-card">
              <div className="insights-sim-kpi-label">Projected CAC</div>
              <div className="insights-sim-kpi-val">{projection.projectedCac.projected}</div>
              <div className="insights-sim-kpi-footer">
                <span className="insights-sim-kpi-base">
                  Baseline: {projection.projectedCac.baseline}
                </span>
                <span
                  className={`insights-delta-chip ${projection.projectedCac.direction === 'up' ? 'down' : 'up'}`}
                >
                  {projection.projectedCac.delta}
                </span>
              </div>
            </div>
          </div>

          {/* Model Assumptions & Methodology */}
          <div className="insights-sim-assumptions">
            <div className="insights-sim-assumptions-title">
              <Info size={13} />
              <span>Simulation Mechanics & Underlying Assumptions</span>
            </div>
            <ul className="insights-sim-assumptions-list">
              {projection.assumptions.map((asm, idx) => (
                <li key={idx}>{asm}</li>
              ))}
            </ul>
          </div>

          {/* Action to transfer to AI analysis */}
          {onAskAI && (
            <div className="insights-sim-actions">
              <button
                type="button"
                className="insights-sim-ai-btn"
                onClick={() => onAskAI(projection, variables)}
              >
                <MessageSquare size={14} />
                <span>Deep Dive with AI Assistant</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
