import React from 'react';
import { useDataPipelineMotion } from '../../hooks/useDataPipelineMotion';
import { RawDataStage } from './RawDataStage';
import { CleaningStage } from './CleaningStage';
import { VisualizationStage } from './VisualizationStage';
import { PipelineProgress } from './PipelineProgress';
import { Sparkles, TrendingUp, Check, Shuffle } from 'lucide-react';

/**
 * Autonomous Analytics Engine — Single-Frame Infinite Motion Viewport
 *
 * Implements the approved single-viewport architecture:
 * - One fixed animation frame in one fixed stationary location
 * - No vertical card stacking; zero layout shifts; stationary outer container
 * - Continuous 7.0-second 1× synchronized timeline:
 *   Stage 1: Unstructured Raw Data (0.00–1.50s)
 *   Transition 1: Raw to Clean Crossfade (1.50–2.25s)
 *   Stage 2: Cleaning & Schema Validation (2.25–3.35s)
 *   Transition 2: Clean to Chart Fade (3.35–4.00s)
 *   Stage 3A: Growing Bar Chart from baseline (4.00–4.95s)
 *   Stage 3B: Continuous Bar → Donut Morph (4.95–5.95s)
 *   Stage 3C: Completed Settled Donut (5.95–6.55s)
 *   Loop Reset: Seamless Crossfade to Raw Scene (6.55–7.00s)
 * - Infinite continuous loop repeating forever without user intervention
 * - Verified running runtime detection for authentic ● LIVE badge display
 * - Full prefers-reduced-motion accessibility support
 */
export const DataTransformationAnimation: React.FC = () => {
  const {
    phase,
    progress,
    elapsedMs,
    activeStage,
    statusText,
    stageTag,
    stageTitle,
    statusBadge,
    footerLeft,
    footerRight,
    isReducedMotion,
    isVerifiedRunning,
    systemReduced,
    toggleMotion,
    subscribeToFrames,
  } = useDataPipelineMotion();

  const StatusIcon =
    activeStage === 1
      ? Shuffle
      : activeStage === 2
      ? Sparkles
      : phase === 'donut-complete'
      ? Check
      : TrendingUp;

  return (
    <section
      className="pipeline-card"
      data-motion={isReducedMotion ? "reduced" : isVerifiedRunning ? "running" : "waiting"}
      aria-label="Interactive Autonomous Data Transformation Pipeline"
    >
      {/* Top Banner Identity */}
      <div className="pipeline-header">
        <div className="pipeline-header-left">
          <span className="pipeline-status-dot" />
          <span className="pipeline-header-title">
            Autonomous Analytics Engine
          </span>
        </div>
        <div className="pipeline-header-right">
          <span
            className={`pipeline-header-badge ${
              isVerifiedRunning && !isReducedMotion
                ? 'pipeline-header-badge--live'
                : 'pipeline-header-badge--static'
            }`}
          >
            {isVerifiedRunning && !isReducedMotion ? (
              <>
                <span className="live-pulse-dot" aria-hidden="true" />
                LIVE ANIMATION
              </>
            ) : (
              isReducedMotion ? 'MOTION REDUCED' : 'WAITING FOR MOTION'
            )}
          </span>
          <button
            type="button"
            onClick={toggleMotion}
            disabled={systemReduced}
            className="pipeline-motion-toggle-btn"
            title={systemReduced ? 'Motion reduced by your system preference' : isReducedMotion ? 'Resume animation' : 'Pause animation'}
            aria-label={isReducedMotion ? 'Enable live animation' : 'Enable static preview'}
          >
            {systemReduced ? 'System preference' : isReducedMotion ? 'Resume Motion' : 'Pause Motion'}
          </button>
        </div>
      </div>

      {/* Screen reader polite live announcement */}
      <p className="sr-only">Illustrative data transforms from raw records to validated rows, then bars and a donut chart, in a repeating seven-second cycle.</p>

      {/* SINGLE MOTION VIEWPORT — Fixed bounding box, stationary frame */}
      <div className="single-motion-viewport" aria-hidden="true">
        {/* Unified Viewport Subheader */}
        <div className="viewport-subheader-bar">
          <div className="viewport-subheader-left">
            <span className="viewport-stage-tag">{stageTag}</span>
            <span className="viewport-stage-title">{stageTitle}</span>
          </div>
          <div className="viewport-status-badge">
            <StatusIcon style={{ width: 11, height: 11, color: '#151915' }} />
            <span>{statusBadge}</span>
          </div>
        </div>

        {/* Viewport Canvas Area — Shared fixed coordinates for all 3 overlapping layers */}
        <div className="viewport-canvas-area">
          <RawDataStage
            phase={phase}
            elapsedMs={elapsedMs}
            isActive={activeStage === 1}
            isReducedMotion={isReducedMotion}
            subscribeToFrames={subscribeToFrames}
          />

          <CleaningStage
            phase={phase}
            elapsedMs={elapsedMs}
            isActive={activeStage === 2}
            isReducedMotion={isReducedMotion}
            subscribeToFrames={subscribeToFrames}
          />

          <VisualizationStage
            phase={phase}
            elapsedMs={elapsedMs}
            isActive={activeStage === 3}
            isReducedMotion={isReducedMotion}
            subscribeToFrames={subscribeToFrames}
          />
        </div>

        {/* Unified Viewport Footer Bar */}
        <div className="viewport-footer-bar">
          <div className="viewport-footer-left">
            <span
              className={`viewport-footer-dot ${
                activeStage === 1
                  ? 'viewport-footer-dot--amber'
                  : 'viewport-footer-dot--lime'
              }`}
            />
            <span>{footerLeft}</span>
          </div>
          <span className="viewport-footer-right">{footerRight}</span>
        </div>
      </div>

      {/* Synchronized Master Progress Timeline */}
      <PipelineProgress
        phase={phase}
        progress={progress}
        elapsedMs={elapsedMs}
        activeStage={activeStage}
        statusText={statusText}
        isReducedMotion={isReducedMotion}
        subscribeToFrames={subscribeToFrames}
      />
    </section>
  );
};
