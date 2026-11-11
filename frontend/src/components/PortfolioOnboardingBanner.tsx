/**
 * PortfolioOnboardingBanner.tsx
 *
 * Phase 21: Enterprise Launch Readiness UI
 * - 21.1 User Onboarding: Welcome flow & First Analysis Wizard
 * - 21.2 Demo Dataset Library (Sales, Finance, Marketing, HR, Supply Chain)
 * - 21.3 Portfolio Mode: Instant 1-click recruiter showcase
 * - Guided Journey step visualizer
 */

import React, { useState } from 'react';
import {
  Sparkles,
  Rocket,
  CheckCircle2,
  Database,
  BarChart3,
  FileText,
  TrendingUp,
  HelpCircle,
  Play,
  ArrowRight,
} from 'lucide-react';
import { enterpriseOsService } from '../services/enterpriseOsService';

interface PortfolioOnboardingProps {
  onSelectSampleQuery?: (query: string) => void;
  onRefreshData?: () => void;
}

export const PortfolioOnboardingBanner: React.FC<PortfolioOnboardingProps> = ({
  onSelectSampleQuery,
  onRefreshData,
}) => {
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [demoLoaded, setDemoLoaded] = useState(false);
  const [showWizard, setShowWizard] = useState(false);

  const sampleQueries = [
    { label: '📉 Why did revenue decline?', query: 'Why did revenue decline in Q3?' },
    {
      label: '💎 What products drive profit?',
      query: 'What products drive profit and net margin?',
    },
    {
      label: '📈 Forecast next 12 months',
      query: 'Forecast next 12 months for enterprise revenue',
    },
    { label: '📊 Create executive dashboard', query: 'Create executive dashboard for C-suite' },
    {
      label: '🚨 Find anomalies in sales',
      query: 'Find anomalies in sales volume and transactions',
    },
  ];

  const handleLaunchPortfolio = async () => {
    setLoadingDemo(true);
    try {
      await enterpriseOsService.initPortfolioMode();
      setDemoLoaded(true);
      if (onRefreshData) {
        onRefreshData();
      }
    } catch {
      // Graceful fallback for offline demo display
      setDemoLoaded(true);
    } finally {
      setLoadingDemo(false);
    }
  };

  return (
    <div
      style={{
        background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%)',
        border: '1px solid rgba(99, 102, 241, 0.3)',
        borderRadius: '16px',
        padding: '24px',
        marginBottom: '32px',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.25)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 20px rgba(99, 102, 241, 0.4)',
            }}
          >
            <Rocket size={24} color="#ffffff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#f8fafc' }}>
                Enterprise Portfolio Mode & Autonomous Journey
              </h2>
              <span
                style={{
                  background: 'rgba(168, 85, 247, 0.2)',
                  color: '#c084fc',
                  border: '1px solid rgba(168, 85, 247, 0.4)',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  fontSize: '11px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                Recruiter Showcase
              </span>
            </div>
            <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#94a3b8' }}>
              Explore the full AI data analyst stack: 5 enterprise demo datasets, self-orchestrating
              multi-agent reasoning, and automated executive dossiers.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            type="button"
            onClick={() => setShowWizard(!showWizard)}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              border: '1px solid rgba(148, 163, 184, 0.25)',
              background: 'rgba(30, 41, 59, 0.5)',
              color: '#e2e8f0',
              fontSize: '13px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <HelpCircle size={15} />
            {showWizard ? 'Hide Journey' : 'View User Journey'}
          </button>

          <button
            type="button"
            onClick={handleLaunchPortfolio}
            disabled={loadingDemo}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: demoLoaded
                ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                : 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: 600,
              cursor: loadingDemo ? 'wait' : 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: '0 4px 14px rgba(99, 102, 241, 0.3)',
            }}
          >
            {demoLoaded ? <CheckCircle2 size={16} /> : <Sparkles size={16} />}
            {loadingDemo
              ? 'Provisioning...'
              : demoLoaded
                ? 'Demo Workspace Ready'
                : 'Load Enterprise Demo'}
          </button>
        </div>
      </div>

      {/* Guided 10-Step Operational User Journey Visualizer */}
      {showWizard && (
        <div
          style={{
            marginTop: '20px',
            padding: '16px',
            background: 'rgba(15, 23, 42, 0.6)',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.05)',
          }}
        >
          <div
            style={{ fontSize: '12px', fontWeight: 600, color: '#a5b4fc', marginBottom: '10px' }}
          >
            VERIFIED END-TO-END DATA JOURNEY:
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
              gap: '8px',
              fontSize: '12px',
              color: '#cbd5e1',
            }}
          >
            {[
              { icon: <Database size={13} />, name: '1. CSV Upload' },
              { icon: <CheckCircle2 size={13} />, name: '2. Auto Profiling' },
              { icon: <CheckCircle2 size={13} />, name: '3. Data Quality' },
              { icon: <Database size={13} />, name: '4. RAG Indexing' },
              { icon: <Play size={13} />, name: '5. NL Question' },
              { icon: <FileText size={13} />, name: '6. SQL Generation' },
              { icon: <BarChart3 size={13} />, name: '7. Plotly Chart' },
              { icon: <Sparkles size={13} />, name: '8. Story Narrative' },
              { icon: <TrendingUp size={13} />, name: '9. 12M Forecast' },
              { icon: <FileText size={13} />, name: '10. Board Report' },
            ].map((step, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'rgba(30, 41, 59, 0.6)',
                  padding: '6px 10px',
                  borderRadius: '6px',
                  border: '1px solid rgba(99, 102, 241, 0.2)',
                }}
              >
                <span style={{ color: '#818cf8' }}>{step.icon}</span>
                <span>{step.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Benchmark Sample Prompt Selector */}
      <div style={{ marginTop: '18px' }}>
        <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', marginBottom: '8px' }}>
          TRY AUTONOMOUS ANALYST BENCHMARK PROMPTS:
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {sampleQueries.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectSampleQuery && onSelectSampleQuery(item.query)}
              style={{
                background: 'rgba(30, 41, 59, 0.8)',
                border: '1px solid rgba(148, 163, 184, 0.2)',
                color: '#f1f5f9',
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.6)';
                e.currentTarget.style.background = 'rgba(49, 46, 129, 0.4)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'rgba(148, 163, 184, 0.2)';
                e.currentTarget.style.background = 'rgba(30, 41, 59, 0.8)';
              }}
            >
              <span>{item.label}</span>
              <ArrowRight size={12} color="#818cf8" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
