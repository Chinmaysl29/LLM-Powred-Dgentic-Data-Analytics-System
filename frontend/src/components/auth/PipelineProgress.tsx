import React, { useEffect, useRef } from 'react';
import type { PipelinePhase } from '../../hooks/useDataPipelineMotion';
import { Clock } from 'lucide-react';

interface PipelineProgressProps {
  phase: PipelinePhase;
  progress: number; // 0 to 1
  elapsedMs: number;
  activeStage: 1 | 2 | 3;
  statusText: string;
  isReducedMotion?: boolean;
  subscribeToFrames?: (cb: (elapsedMs: number) => void) => () => void;
}

export const PipelineProgress: React.FC<PipelineProgressProps> = ({
  activeStage,
  statusText,
  isReducedMotion = false,
  subscribeToFrames,
  elapsedMs,
}) => {
  const progressFillRef = useRef<HTMLDivElement>(null);
  const clockTextRef = useRef<HTMLSpanElement>(null);
  const percentBadgeRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (isReducedMotion) {
      if (progressFillRef.current) progressFillRef.current.style.transform = 'scaleX(1)';
      if (clockTextRef.current) clockTextRef.current.textContent = 'Motion reduced';
      if (percentBadgeRef.current) percentBadgeRef.current.textContent = '100%';
      return;
    }

    if (!subscribeToFrames) return;

    let lastSecStr = '';
    let lastPctStr = '';

    const unsubscribe = subscribeToFrames((currentElapsedMs: number) => {
      const pct = Math.min(Math.round((currentElapsedMs / 7000) * 100), 100);
      const pctStr = `${pct}%`;
      const secStr = `${(currentElapsedMs / 1000).toFixed(1)}s / 7.0s`;

      if (progressFillRef.current) {
        progressFillRef.current.style.transform = `scaleX(${currentElapsedMs < 6550 ? currentElapsedMs / 6550 : (7000 - currentElapsedMs) / 450})`;
      }

      if (clockTextRef.current && secStr !== lastSecStr) {
        lastSecStr = secStr;
        clockTextRef.current.textContent = secStr;
      }

      if (percentBadgeRef.current && pctStr !== lastPctStr) {
        lastPctStr = pctStr;
        percentBadgeRef.current.textContent = pctStr;
      }
    });

    return unsubscribe;
  }, [subscribeToFrames, isReducedMotion]);

  const initialPercent = isReducedMotion ? 100 : Math.min(Math.round((elapsedMs / 7000) * 100), 100);
  const initialSeconds = (elapsedMs / 1000).toFixed(1);

  return (
    <div className="pipeline-progress" style={{ marginTop: '0.75rem' }}>
      {/* Progress Info Header */}
      <div className="progress-header">
        <div className="progress-title-left">
          <span
            className="progress-pulse-dot"
            style={{
              backgroundColor: '#B8F641',
              boxShadow: '0 0 0 3px rgba(184, 246, 65, 0.25)',
            }}
          />
          <span style={{ fontSize: '0.75rem', fontWeight: 650, color: '#151915' }}>
            {statusText}
          </span>
        </div>

        <div className="progress-meta-right">
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.25rem',
              fontFamily: 'ui-monospace, monospace',
              fontSize: '0.6875rem',
              color: '#737D6E',
            }}
          >
            <Clock style={{ width: 11, height: 11 }} />
            <span ref={clockTextRef}>
              {isReducedMotion ? 'Motion reduced' : `${initialSeconds}s / 7.0s`}
            </span>
          </span>
          <span className="progress-percent-badge" ref={percentBadgeRef}>
            {initialPercent}%
          </span>
        </div>
      </div>

      {/* Continuous 7.0s Progress Bar Track */}
      <div
        className="progress-track"
        style={{
          height: 5,
          borderRadius: 9999,
          backgroundColor: '#E5EBDD',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          ref={progressFillRef}
          className="progress-fill"
          style={{
            width: '100%',
            transform: `scaleX(${isReducedMotion ? 1 : 0})`,
            transformOrigin: 'left',
            height: '100%',
            backgroundColor: '#151915',
            borderRadius: 9999,
            willChange: 'transform',
          }}
        />
      </div>

      {/* 3 Synchronized Stages */}
      <div
        className="progress-steps"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginTop: '0.5rem',
          fontSize: '0.6875rem',
        }}
      >
        <span
          style={{
            fontWeight: activeStage === 1 ? 750 : 500,
            color: activeStage === 1 ? '#151915' : '#737D6E',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            transition: 'color 0.2s ease',
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              backgroundColor: activeStage === 1 ? '#B8F641' : '#DCE5D4',
              boxShadow: activeStage === 1 ? '0 0 0 2px rgba(184, 246, 65, 0.3)' : 'none',
              transition: 'background-color 0.2s ease',
            }}
          />
          01 Raw Data
        </span>

        <span
          style={{
            fontWeight: activeStage === 2 ? 750 : 500,
            color: activeStage === 2 ? '#151915' : '#737D6E',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            transition: 'color 0.2s ease',
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              backgroundColor: activeStage === 2 ? '#B8F641' : '#DCE5D4',
              boxShadow: activeStage === 2 ? '0 0 0 2px rgba(184, 246, 65, 0.3)' : 'none',
              transition: 'background-color 0.2s ease',
            }}
          />
          02 Clean Data
        </span>

        <span
          style={{
            fontWeight: activeStage === 3 ? 750 : 500,
            color: activeStage === 3 ? '#151915' : '#737D6E',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            transition: 'color 0.2s ease',
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              backgroundColor: activeStage === 3 ? '#B8F641' : '#DCE5D4',
              boxShadow: activeStage === 3 ? '0 0 0 2px rgba(184, 246, 65, 0.3)' : 'none',
              transition: 'background-color 0.2s ease',
            }}
          />
          03 Bars → Donut
        </span>
      </div>
    </div>
  );
};
