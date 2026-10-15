import React, { useEffect, useRef } from 'react';
import type { PipelinePhase } from '../../hooks/useDataPipelineMotion';
import { PIPELINE_TIMING } from '../../hooks/useDataPipelineMotion';
import { AlertTriangle, Layers } from 'lucide-react';

interface RawDataStageProps {
  phase: PipelinePhase;
  elapsedMs: number;
  isActive: boolean;
  isReducedMotion?: boolean;
  subscribeToFrames?: (cb: (elapsedMs: number) => void) => () => void;
}

interface RawToken {
  id: string;
  label: string;
  isDirty?: boolean;
  isDuplicate?: boolean;
  initialX: number;
  initialY: number;
  driftX: number;
  driftY: number;
  targetAlignY: number;
}

const RAW_TOKENS: RawToken[] = [
  { id: 't1', label: 'user_id: 84920', initialX: 18, initialY: 16, driftX: -4, driftY: 3, targetAlignY: 14 },
  { id: 't2', label: 'revenue: NaN', isDirty: true, initialX: 165, initialY: 12, driftX: 3, driftY: -4, targetAlignY: 14 },
  { id: 't3', label: 'country: US (mixed)', initialX: 275, initialY: 20, driftX: -3, driftY: -3, targetAlignY: 52 },
  { id: 't4', label: 'tx_date: 2024/13/99', isDirty: true, initialX: 22, initialY: 62, driftX: 5, driftY: 4, targetAlignY: 52 },
  { id: 't5', label: 'sku: PRD-901 [DUP]', isDuplicate: true, initialX: 180, initialY: 58, driftX: -4, driftY: -3, targetAlignY: 90 },
  { id: 't6', label: 'qty: 14', initialX: 320, initialY: 66, driftX: 4, driftY: 2, targetAlignY: 90 },
  { id: 't7', label: 'margin: NULL', isDirty: true, initialX: 38, initialY: 110, driftX: 3, driftY: -4, targetAlignY: 128 },
  { id: 't8', label: 'sku: PRD-901', initialX: 185, initialY: 106, driftX: -3, driftY: 4, targetAlignY: 128 },
];

export const RawDataStage: React.FC<RawDataStageProps> = ({
  isReducedMotion = false,
  subscribeToFrames,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  const tokenRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  useEffect(() => {
    if (!subscribeToFrames || isReducedMotion) {
      if (containerRef.current) {
        containerRef.current.style.opacity = isReducedMotion ? '0' : '1';
        containerRef.current.style.pointerEvents = 'none';
      }
      return;
    }

    const unsubscribe = subscribeToFrames((elapsedMs: number) => {
      const container = containerRef.current;
      if (!container) return;

      const t = elapsedMs;
      let layerOpacity: number;
      let transitionProgress = 0;
      let isDrifting = false;

      // 0.00–1.50s: Stage 1 active (opacity 1.0, subtle drift)
      if (t < PIPELINE_TIMING.raw[1]) {
        layerOpacity = 1;
        transitionProgress = 0;
        isDrifting = true;
      }
      // 1.50–2.25s: Transition 1 (crossfades out 1.0 -> 0.0, dirty items dissolve earlier)
      else if (t < PIPELINE_TIMING.rawToClean[1]) {
        const p = (t - PIPELINE_TIMING.rawToClean[0]) / (PIPELINE_TIMING.rawToClean[1] - PIPELINE_TIMING.rawToClean[0]);
        layerOpacity = Math.max(0, 1 - p);
        transitionProgress = p;
        isDrifting = false;
      }
      // 2.25–6.55s: Hidden while Stage 2 and Stage 3 dominate viewport
      else if (t < PIPELINE_TIMING.loopReset[0]) {
        layerOpacity = 0;
        transitionProgress = 1;
        isDrifting = false;
      }
      // 6.55–7.00s: Infinite Loop Reset (fade in 0.0 -> 1.0 to seamlessly connect to next cycle)
      else {
        const resetProgress = (t - PIPELINE_TIMING.loopReset[0]) / (PIPELINE_TIMING.loopReset[1] - PIPELINE_TIMING.loopReset[0]);
        layerOpacity = resetProgress;
        transitionProgress = 0;
        isDrifting = true;
      }

      container.style.opacity = layerOpacity.toFixed(3);
      

      if (layerOpacity > 0.001) {
        // Continuous harmonic drift: exactly 2 full cycles per 7 seconds ensures drift(7000ms) == drift(0ms)
        const driftPhase = (t / 7000) * (4 * Math.PI);

        RAW_TOKENS.forEach((token) => {
          const el = tokenRefs.current.get(token.id);
          if (!el) return;

          const isAnomaly = token.isDirty || token.isDuplicate;
          const anomalyOpacity = isAnomaly
            ? Math.max(0, 1 - transitionProgress * 2.0)
            : 1;

          const driftEnvelope = isDrifting ? (t < 1500 ? Math.max(0, 1 - t / 1500) : (t - 6550) / 450) : 0;
          const currentDriftX = Math.sin(driftPhase + token.initialX) * token.driftX * driftEnvelope;
          const currentDriftY = Math.cos(driftPhase + token.initialY) * token.driftY * driftEnvelope;

          const currentY = transitionProgress > 0 && !isAnomaly
            ? token.initialY + (token.targetAlignY - token.initialY) * transitionProgress
            : token.initialY + currentDriftY;
          const currentX = token.initialX + (isAnomaly ? 0 : (18 - token.initialX) * transitionProgress) + currentDriftX;

          const scale = isAnomaly && transitionProgress > 0 ? Math.max(0.6, 1 - transitionProgress * 0.4) : 1;

          el.style.transform = `translate3d(${currentX.toFixed(1)}px, ${currentY.toFixed(1)}px, 0) scale(${scale.toFixed(2)})`;
          el.style.opacity = anomalyOpacity.toFixed(2);
        });


      }
    });

    return unsubscribe;
  }, [subscribeToFrames, isReducedMotion]);

  return (
    <div
      ref={containerRef}
      className="raw-stage-layer"
      style={{
        opacity: isReducedMotion ? 0 : 1,
        position: 'absolute',
        inset: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
        willChange: 'opacity',
      }}
    >
      {/* Scattered Tokens Matrix */}
      <div
        className="raw-token-board"
        style={{
          position: 'relative',
          width: '100%',
          height: '100%',
          overflow: 'hidden',
        }}
      >
        {RAW_TOKENS.map((token) => {
          const chipBg = token.isDirty
            ? '#FFF9F2'
            : token.isDuplicate
            ? '#FEF2F2'
            : '#FFFFFF';
          const chipBorder = token.isDirty
            ? '#FED7AA'
            : token.isDuplicate
            ? '#FECACA'
            : '#E5EBDD';
          const chipColor = token.isDirty
            ? '#B45309'
            : token.isDuplicate
            ? '#B91C1C'
            : '#151915';

          return (
            <div
              key={token.id}
              ref={(el) => {
                if (el) tokenRefs.current.set(token.id, el);
                else tokenRefs.current.delete(token.id);
              }}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                transform: `translate3d(${token.initialX}px, ${token.initialY}px, 0)`,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.375rem',
                padding: '0.25rem 0.5rem',
                borderRadius: '6px',
                fontSize: '0.625rem',
                fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                backgroundColor: chipBg,
                border: `1px solid ${chipBorder}`,
                color: chipColor,
                boxShadow: '0 1px 2px rgba(21, 25, 21, 0.04)',
                whiteSpace: 'nowrap',
                willChange: 'transform, opacity',
              }}
            >
              {token.isDirty && <AlertTriangle style={{ width: 11, height: 11, color: '#F59E0B' }} />}
              {token.isDuplicate && <Layers style={{ width: 11, height: 11, color: '#EF4444' }} />}
              <span>{token.label}</span>
            </div>
          );
        })}


      </div>
    </div>
  );
};
