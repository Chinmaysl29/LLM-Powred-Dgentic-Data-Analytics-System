import React from 'react';
import { Check, Circle } from 'lucide-react';
import { TextShimmer } from '../ui/shimmer-text';

import { REPORT_GENERATION_STEPS } from './reportSteps';

interface ReportGenerationProgressProps {
  activeStep: number;
}

export const ReportGenerationProgress: React.FC<ReportGenerationProgressProps> = ({
  activeStep,
}) => {
  return (
    <section
      className="reports-gen-container"
      aria-live="polite"
      aria-label="Report generation progress"
    >
      {/* Visual Animation Graphic matching AI Analysis */}
      <div className="reports-gen-viz-animation" aria-hidden="true">
        <svg viewBox="0 0 420 210">
          <defs>
            <linearGradient id="reportLoaderLine" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#c084fc" />
              <stop offset="50%" stopColor="#60a5fa" />
              <stop offset="100%" stopColor="#22d3ee" />
            </linearGradient>
            <radialGradient id="reportLoaderGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#60a5fa" stopOpacity="0.45" />
              <stop offset="100%" stopColor="#60a5fa" stopOpacity="0" />
            </radialGradient>
          </defs>
          <circle
            className="analysis-loader-radial"
            cx="210"
            cy="104"
            r="85"
            fill="url(#reportLoaderGlow)"
          />
          <path
            className="analysis-loader-grid"
            d="M40 50H380M40 95H380M40 140H380M95 26V168M155 26V168M215 26V168M275 26V168M335 26V168"
          />
          <path
            className="analysis-loader-flow"
            d="M42 132 C92 54 136 54 184 111 S278 169 378 62"
            stroke="url(#reportLoaderLine)"
          />
          <g className="analysis-loader-points">
            {[72, 116, 160, 204, 248, 292, 336].map((x, index) => (
              <circle
                key={x}
                cx={x}
                cy={index % 2 ? 82 : 122}
                r={index === activeStep ? 7 : 4}
                fill={index <= activeStep ? '#22d3ee' : '#94a3b8'}
              />
            ))}
          </g>
        </svg>
      </div>

      <div className="reports-gen-copy">
        <TextShimmer className="reports-gen-title">
          Generating Comprehensive Business Report...
        </TextShimmer>
        <p className="reports-gen-sub">
          Synthesizing verified empirical records, interactive charts, and strategic decision
          intelligence.
        </p>
      </div>

      {/* Stepper Workflow List */}
      <ol className="reports-workflow-list">
        {REPORT_GENERATION_STEPS.map((step, index) => {
          const isComplete = index < activeStep;
          const isActive = index === activeStep;
          const stateClass = isComplete ? 'complete' : isActive ? 'active' : 'upcoming';

          return (
            <li key={step} className={`reports-workflow-step reports-workflow-step--${stateClass}`}>
              <span className="reports-step-indicator">
                {isComplete ? (
                  <Check size={13} aria-hidden="true" className="reports-check-icon" />
                ) : (
                  <Circle size={10} aria-hidden="true" className="reports-circle-icon" />
                )}
              </span>
              <span className="reports-step-text">{step}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
};
