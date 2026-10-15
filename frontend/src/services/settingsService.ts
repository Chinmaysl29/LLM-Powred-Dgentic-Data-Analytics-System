/**
 * settingsService.ts
 *
 * Centralized service boundary for application settings and preferences.
 *
 * BACKEND INTEGRATION POINT:
 * When backend settings endpoints are implemented (e.g. GET/PUT /api/settings,
 * POST /api/settings/reset), update these methods to execute real API requests
 * without altering the frontend component contract.
 */

import type { AppSettings } from '../types/settings';

const DEFAULT_SETTINGS: AppSettings = {
  general: {
    language: 'en',
    dateFormat: 'DD/MM/YYYY',
    numberFormat: '1,234.56',
    defaultLandingPage: '/dashboard',
  },
  appearance: {
    theme: 'dark',
    density: 'comfortable',
    animations: true,
    reduceMotion: false,
  },
  ai: {
    defaultModel: 'Automatic',
    responseStyle: 'Detailed',
    analysisDepth: 'Balanced',
    explainReasoning: true,
    showEvidence: true,
    showAssumptions: true,
    showConfidence: true,
    generateRecommendations: true,
  },
  data: {
    previewRows: 100,
    autoDetectTypes: true,
    autoGenerateInsights: true,
    autoGenerateVisualizations: true,
    saveAnalysisHistory: true,
    retainDatasets: true,
  },
  notifications: {
    analysisCompleted: true,
    datasetProcessing: true,
    reportGenerated: true,
    reportGenerationFailed: true,
    systemNotifications: true,
    productUpdates: false,
  },
  privacy: {
    saveAnalysisHistory: true,
    saveConversationHistory: true,
    usePreviousAnalysisContext: true,
  },
  advanced: {
    optimizedRendering: true,
    experimentalFeatures: false,
  },
};

function unavailable(): never { throw new Error('Settings APIs are unavailable. No changes were saved or applied.'); }
export const settingsService = {
 async getSettings(): Promise<AppSettings> { return unavailable(); },
 async updateSettings(_partial: Partial<AppSettings>): Promise<AppSettings> { return unavailable(); },
 async resetSettings(): Promise<AppSettings> { return unavailable(); },
 getDefaultSettings(): AppSettings { return structuredClone(DEFAULT_SETTINGS); },
};
