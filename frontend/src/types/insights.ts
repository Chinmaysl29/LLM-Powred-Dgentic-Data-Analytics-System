/**
 * insights.ts
 *
 * Strongly-typed data contracts for Phase 6: Insights & Decision Intelligence.
 * Distinguishes strictly between observed evidence, derived interpretations,
 * and what-if simulation outputs.
 */

export type InsightType = 'trend' | 'pattern' | 'anomaly' | 'driver' | 'change' | 'correlation';

export interface InsightMetric {
  label: string;
  value: string;
  change?: string;
  direction?: 'up' | 'down' | 'neutral';
}

export interface VisualizationReference {
  chartType: 'Line' | 'Bar' | 'Pie' | 'Area' | 'Scatter';
  xAxis?: string;
  yAxis?: string;
  title: string;
  description?: string;
}

export interface Insight {
  id: string;
  type: InsightType;
  title: string;
  summary: string;
  observedEvidence: string[];
  derivedInterpretation: string;
  metrics: InsightMetric[];
  drivers: string[];
  confidence?: number; // 0 to 1, only if supplied by backend model
  visualizationReference?: VisualizationReference;
  datasetName?: string;
  timePeriod?: string;
}

export interface Risk {
  id: string;
  title: string;
  summary: string;
  impact: 'High' | 'Medium' | 'Low';
  evidence: InsightMetric[];
  contributingFactors: string[];
  observedData: string[];
  confidence?: number;
  visualizationReference?: VisualizationReference;
  datasetName?: string;
  timePeriod?: string;
}

export interface Opportunity {
  id: string;
  title: string;
  summary: string;
  potentialImpact?: string;
  potentialUpside?: string;
  growth?: string;
  strongestSegments?: string[];
  targetRegions?: string[];
  evidence?: InsightMetric[];
  observedData: string[];
  confidence?: number;
  scenarioHint?: string;
  visualizationReference?: VisualizationReference;
  datasetName?: string;
  timePeriod?: string;
}

export interface Recommendation {
  id: string;
  title: string;
  summary?: string;
  rationale: string;
  evidence?: InsightMetric[];
  supportingEvidence: string[];
  expectedImpact?: string;
  effort?: 'Low' | 'Medium' | 'High';
  assumptions: string[];
  scenarioReference?: {
    scenarioName: string;
    defaultVariables: ScenarioInputVariables;
  };
  scenarioVariables?: Partial<ScenarioInputVariables>;
  confidence?: number;
  visualizationReference?: VisualizationReference;
  datasetName?: string;
  timePeriod?: string;
}

export interface BusinessHealthMetric {
  id: string;
  label: string;
  value: string;
  subValue: string;
  trend: string;
  direction: 'up' | 'down' | 'neutral';
  status: 'positive' | 'warning' | 'negative' | 'neutral';
}

export interface ScenarioInputVariables {
  marketingSpendDelta: number; // percentage (-50% to +100%)
  priceDelta: number; // percentage (-30% to +50%)
  churnDelta: number; // percentage (-20% to +30%)
  marketingSpendDeltaPct?: number; // alias
  priceAdjustmentPct?: number; // alias
  churnRateDeltaPct?: number; // alias
  region?: string;
  targetRegion?: string;
  productCategory?: string;
  targetCategory?: string;
  timeHorizon?: 'quarterly' | 'annual' | string;
}

export interface MetricDelta {
  baseline: number;
  projected: number;
  changePercent: number;
  formatPrefix?: string;
  formatSuffix?: string;
}

export interface ScenarioProjection {
  revenue: MetricDelta;
  orders: MetricDelta;
  customers: MetricDelta;
  conversionRate: MetricDelta;
  projectedRevenue: {
    baseline: string;
    projected: string;
    delta: string;
    direction: 'up' | 'down' | 'neutral';
  };
  netImpact: string;
  confidenceInterval: string;
  projectedCustomers: {
    baseline: string;
    projected: string;
    delta: string;
    direction: 'up' | 'down' | 'neutral';
  };
  projectedCac: {
    baseline: string;
    projected: string;
    delta: string;
    direction: 'up' | 'down' | 'neutral';
  };
  riskAssessment: 'Low' | 'Moderate' | 'Elevated';
  assumptions: string[];
  drivers: string[];
}

export interface WhatIfScenario {
  id: string;
  name: string;
  description: string;
  inputs: ScenarioInputVariables;
  projection: ScenarioProjection;
}
