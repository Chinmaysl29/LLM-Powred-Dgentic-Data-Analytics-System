import React, { useEffect, useRef } from 'react';
import type { PipelinePhase } from '../../hooks/useDataPipelineMotion';
import { PIPELINE_TIMING } from '../../hooks/useDataPipelineMotion';
import { CheckCircle2 } from 'lucide-react';

interface CleaningStageProps {
  phase: PipelinePhase;
  elapsedMs: number;
  isActive: boolean;
  isReducedMotion?: boolean;
  subscribeToFrames?: (cb: (elapsedMs: number) => void) => () => void;
}

interface CleanRow {
  id: string;
  field: string;
  type: string;
  value: string;
  revealCheckAtMs: number;
}

const CLEAN_ROWS: CleanRow[] = [
  { id: 'c1', field: 'cust_account', type: 'UUID', value: '0x84920_valid', revealCheckAtMs: 2350 },
  { id: 'c2', field: 'revenue_usd', type: 'Decimal', value: '$14,250.00', revealCheckAtMs: 2550 },
  { id: 'c3', field: 'timestamp_utc', type: 'DateTime', value: '2026-10-12T00:00Z', revealCheckAtMs: 2750 },
  { id: 'c4', field: 'product_sku', type: 'String', value: 'PRD-901-CLEAN', revealCheckAtMs: 2950 },
];

export const CleaningStage: React.FC<CleaningStageProps> = ({
  isReducedMotion = false,
  subscribeToFrames,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const checkRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  useEffect(() => {
    if (!subscribeToFrames || isReducedMotion) {
      if (containerRef.current) {
        containerRef.current.style.opacity = '0';
        
      }
      return;
    }

    const unsubscribe = subscribeToFrames((elapsedMs: number) => {
      const container = containerRef.current;
      if (!container) return;

      const t = elapsedMs;
      let layerOpacity: number;
      let rowsProgress = 0;

      // 0.00–1.50s: Invisible
      if (t < PIPELINE_TIMING.rawToClean[0]) {
        layerOpacity = 0;
        rowsProgress = 0;
      }
      // 1.50–2.25s: Crossfades in (0.0 -> 1.0) while RawData fades out
      else if (t < PIPELINE_TIMING.rawToClean[1]) {
        const p = (t - PIPELINE_TIMING.rawToClean[0]) / (PIPELINE_TIMING.rawToClean[1] - PIPELINE_TIMING.rawToClean[0]);
        layerOpacity = p;
        rowsProgress = p;
      }
      // 2.25–3.35s: Stage 2 active (opacity 1.0, rows locked, checks reveal)
      else if (t < PIPELINE_TIMING.cleanToChart[0]) {
        layerOpacity = 1;
        rowsProgress = 1;
      }
      // 3.35–4.00s: Transition 2 (crossfades out 1.0 -> 0.0 into Chart visualization)
      else if (t < PIPELINE_TIMING.cleanToChart[1]) {
        const exitProgress = (t - PIPELINE_TIMING.cleanToChart[0]) / (PIPELINE_TIMING.cleanToChart[1] - PIPELINE_TIMING.cleanToChart[0]);
        layerOpacity = Math.max(0, 1 - exitProgress);
        rowsProgress = 1;
      }
      // 4.00–7.00s: Invisible
      else {
        layerOpacity = 0;
        rowsProgress = 0;
      }

      container.style.opacity = layerOpacity.toFixed(3);
      

      if (layerOpacity > 0.001) {
        CLEAN_ROWS.forEach((row, index) => {
          const rowEl = rowRefs.current.get(row.id);
          const checkEl = checkRefs.current.get(row.id);

          if (rowEl) {
            const slideOffset = (1 - rowsProgress) * (index + 1) * 8;
            rowEl.style.transform = `translate3d(${slideOffset.toFixed(1)}px, 0, 0)`;
          }

          if (checkEl) {
            const reveal = Math.min(1, Math.max(0, (t - row.revealCheckAtMs) / 180));
            const isRevealed = reveal > 0;
            checkEl.style.backgroundColor = isRevealed ? '#B8F641' : '#F5F9ED';
            checkEl.style.transform = `scale(${0.85 + 0.15 * reveal})`;
            checkEl.style.opacity = String(reveal);
          }
        });
      }
    });

    return unsubscribe;
  }, [subscribeToFrames, isReducedMotion]);

  return (
    <div
      ref={containerRef}
      className="cleaning-stage-layer"
      style={{
        opacity: 0,
        display: 'flex',
        position: 'absolute',
        inset: 0,
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '0.25rem 0.75rem',
        boxSizing: 'border-box',
        pointerEvents: 'none',
        gap: '0.375rem',
        willChange: 'opacity',
      }}
    >
      {CLEAN_ROWS.map((row) => (
        <div
          key={row.id}
          ref={(el) => {
            if (el) rowRefs.current.set(row.id, el);
            else rowRefs.current.delete(row.id);
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.35rem 0.625rem',
            borderRadius: '6px',
            backgroundColor: '#FAFBF7',
            border: '1px solid #E5EBDD',
            boxShadow: '0 1px 2px rgba(21, 25, 21, 0.02)',
            willChange: 'transform',
          }}
        >
          {/* Field name and column type */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              style={{
                fontSize: '0.6875rem',
                fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                fontWeight: 650,
                color: '#151915',
              }}
            >
              {row.field}
            </span>
            <span
              style={{
                fontSize: '0.5625rem',
                fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                padding: '0.0625rem 0.3125rem',
                borderRadius: '4px',
                backgroundColor: '#FFFFFF',
                border: '1px solid #E5EBDD',
                color: '#737D6E',
                fontWeight: 600,
              }}
            >
              {row.type}
            </span>
          </div>

          {/* Value and animated validation checkmark */}
          <div className="clean-value-cell" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              style={{
                fontSize: '0.6875rem',
                fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                color: '#151915',
                fontWeight: 500,
              }}
            >
              {row.value}
            </span>

            <div
              ref={(el) => {
                if (el) checkRefs.current.set(row.id, el);
                else checkRefs.current.delete(row.id);
              }}
              style={{
                width: 15,
                height: 15,
                borderRadius: '50%',
                backgroundColor: '#F5F9ED',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transform: 'scale(0.6)',
                opacity: 0,

                willChange: 'transform, opacity, background-color',
              }}
            >
              <CheckCircle2 style={{ width: 11, height: 11, color: '#151915' }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
