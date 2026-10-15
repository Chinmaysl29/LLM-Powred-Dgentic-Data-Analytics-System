import type { BusinessHealthMetric, Insight, Risk, Opportunity, Recommendation, ScenarioInputVariables, ScenarioProjection } from '../types/insights';
function unavailable(): never { throw new Error('Business insights and scenarios require a completed dataset-backed analysis. This endpoint is not available.'); }
export async function getBusinessHealth(_datasetId?: string): Promise<BusinessHealthMetric[]> { return unavailable(); }
export async function getInsights(_datasetId?: string, _dateRange?: string): Promise<Insight[]> { return unavailable(); }
export async function getRisks(_datasetId?: string): Promise<Risk[]> { return unavailable(); }
export async function getOpportunities(_datasetId?: string): Promise<Opportunity[]> { return unavailable(); }
export async function getRecommendations(_datasetId?: string): Promise<Recommendation[]> { return unavailable(); }
export function calculateScenarioProjection(_datasetId: string, _inputs: ScenarioInputVariables): ScenarioProjection { return unavailable(); }
export async function runWhatIfScenario(_datasetId: string, _inputs: ScenarioInputVariables): Promise<ScenarioProjection> { return unavailable(); }
