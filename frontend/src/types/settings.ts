/**
 * Application Settings domain types.
 *
 * BACKEND INTEGRATION POINT:
 * When backend settings endpoints are available (e.g. GET/PUT /api/settings),
 * reconcile these types with the backend schema.
 */

export type SettingsCategory =
  | 'general'
  | 'appearance'
  | 'ai'
  | 'data'
  | 'notifications'
  | 'integrations'
  | 'privacy'
  | 'advanced';

export type LanguageCode = 'en';
export type DateFormatOption = 'DD/MM/YYYY' | 'MM/DD/YYYY' | 'YYYY-MM-DD';
export type NumberFormatOption = '1,234.56' | '1.234,56';
export type LandingPageOption =
  '/dashboard' | '/analysis' | '/datasets' | '/visualizations' | '/insights' | '/reports';

export interface GeneralSettings {
  language: LanguageCode;
  dateFormat: DateFormatOption;
  numberFormat: NumberFormatOption;
  defaultLandingPage: LandingPageOption;
}

export type InterfaceDensity = 'comfortable' | 'compact';

export interface AppearanceSettings {
  theme: 'dark';
  density: InterfaceDensity;
  animations: boolean;
  reduceMotion: boolean;
}

export type AIModelOption = 'Automatic';
export type AIResponseStyleOption = 'Concise' | 'Balanced' | 'Detailed';
export type AIAnalysisDepthOption = 'Quick' | 'Balanced' | 'Deep';

export interface AISettings {
  defaultModel: AIModelOption;
  responseStyle: AIResponseStyleOption;
  analysisDepth: AIAnalysisDepthOption;
  explainReasoning: boolean;
  showEvidence: boolean;
  showAssumptions: boolean;
  showConfidence: boolean;
  generateRecommendations: boolean;
}

export type PreviewRowsOption = 50 | 100 | 250 | 500;

export interface DataAnalysisSettings {
  previewRows: PreviewRowsOption;
  autoDetectTypes: boolean;
  autoGenerateInsights: boolean;
  autoGenerateVisualizations: boolean;
  saveAnalysisHistory: boolean;
  retainDatasets: boolean;
}

export interface NotificationSettings {
  analysisCompleted: boolean;
  datasetProcessing: boolean;
  reportGenerated: boolean;
  reportGenerationFailed: boolean;
  systemNotifications: boolean;
  productUpdates: boolean;
}

export interface PrivacySettings {
  saveAnalysisHistory: boolean;
  saveConversationHistory: boolean;
  usePreviousAnalysisContext: boolean;
}

export interface AdvancedSettings {
  optimizedRendering: boolean;
  experimentalFeatures: boolean;
}

export interface AppSettings {
  general: GeneralSettings;
  appearance: AppearanceSettings;
  ai: AISettings;
  data: DataAnalysisSettings;
  notifications: NotificationSettings;
  privacy: PrivacySettings;
  advanced: AdvancedSettings;
}
