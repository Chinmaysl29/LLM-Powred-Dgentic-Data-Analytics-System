import React, { useEffect, useRef } from 'react';
import type { PipelinePhase } from '../../hooks/useDataPipelineMotion';
import { PIPELINE_TIMING } from '../../hooks/useDataPipelineMotion';

interface AnimatedChartMorphProps {
  phase: PipelinePhase;
  elapsedMs: number;
  isReducedMotion?: boolean;
  subscribeToFrames?: (cb: (elapsedMs: number) => void) => () => void;
}

interface ChartSegmentConfig {
  label: string;
  category: string;
  value: number; // percentage (0-100)
  color: string;
  maxHeight: number;
  barX: number;
}

// Exactly matching suggested values: [42, 68, 55, 84, 62, 96]
const SEGMENTS: ChartSegmentConfig[] = [
  { label: 'Jan', category: 'UUID', value: 42, color: '#DCE5D4', maxHeight: 36, barX: 72 },
  { label: 'Feb', category: 'DEC', value: 68, color: '#A8EB2C', maxHeight: 58, barX: 124 },
  { label: 'Mar', category: 'TIME', value: 55, color: '#CBD7C3', maxHeight: 47, barX: 176 },
  { label: 'Apr', category: 'SKU', value: 84, color: '#B8F641', maxHeight: 72, barX: 228 }, // Primary Lime
  { label: 'May', category: 'VOL', value: 62, color: '#84CC16', maxHeight: 54, barX: 280 },
  { label: 'Jun', category: 'CONF', value: 96, color: '#151915', maxHeight: 82, barX: 332 }, // Tertiary Dark
];

const CX = 200;
const CY = 86;
const R_OUT = 58;
const R_IN = 33;
const BAR_WIDTH = 25;
const Y_BASE = 148;

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function smoothStep(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function computeSegmentPath(seg: ChartSegmentConfig, i: number, barGrowth: number, morphT: number): { d: string; yTop: number } {
  // 1. Donut arc geometry (m = 1)
  const total = SEGMENTS.reduce((sum, item) => sum + item.value, 0);
  const preceding = SEGMENTS.slice(0, i).reduce((sum, item) => sum + item.value, 0);
  const span = (seg.value / total) * 360;
  const midAngleDeg = -90 + (preceding / total) * 360 + span / 2;
  const spanHalfDeg = (span - 3) / 2;
  const startAngleRad = ((midAngleDeg - spanHalfDeg) * Math.PI) / 180;
  const endAngleRad = ((midAngleDeg + spanHalfDeg) * Math.PI) / 180;
  const deltaAngle = endAngleRad - startAngleRad;

  // Bezier curve control point factor for circular arc
  const k = (4 / 3) * Math.tan(deltaAngle / 4);

  // Donut outer arc
  const Do1 = { x: CX + R_OUT * Math.cos(startAngleRad), y: CY + R_OUT * Math.sin(startAngleRad) };
  const Do2 = { x: CX + R_OUT * Math.cos(endAngleRad), y: CY + R_OUT * Math.sin(endAngleRad) };
  const To1 = { x: -Math.sin(startAngleRad), y: Math.cos(startAngleRad) };
  const To2 = { x: -Math.sin(endAngleRad), y: Math.cos(endAngleRad) };
  const Cdo1 = { x: Do1.x + k * R_OUT * To1.x, y: Do1.y + k * R_OUT * To1.y };
  const Cdo2 = { x: Do2.x - k * R_OUT * To2.x, y: Do2.y - k * R_OUT * To2.y };

  // Donut inner arc (reversed)
  const Di2 = { x: CX + R_IN * Math.cos(endAngleRad), y: CY + R_IN * Math.sin(endAngleRad) };
  const Di1 = { x: CX + R_IN * Math.cos(startAngleRad), y: CY + R_IN * Math.sin(startAngleRad) };
  const Cdi2 = { x: Di2.x - k * R_IN * To2.x, y: Di2.y - k * R_IN * To2.y };
  const Cdi1 = { x: Di1.x + k * R_IN * To1.x, y: Di1.y + k * R_IN * To1.y };

  // 2. Bar geometry (m = 0)
  const currentHeight = seg.maxHeight * barGrowth;
  const yTop = Y_BASE - currentHeight;
  const halfW = BAR_WIDTH / 2;
  const thirdW = BAR_WIDTH / 6;

  const TL = { x: seg.barX - halfW, y: yTop };
  const TR = { x: seg.barX + halfW, y: yTop };
  const BR = { x: seg.barX + halfW, y: Y_BASE };
  const BL = { x: seg.barX - halfW, y: Y_BASE };

  // Orient bar rectangle to match donut arc quadrant to prevent figure-8 inversion/pinching
  // Seg 0 (top-right) & Seg 5 (top-left): Top edge outer
  // Seg 1 (right) & Seg 2 (lower-right): Right edge outer
  // Seg 3 (bottom): Bottom edge reversed
  // Seg 4 (lower-left): Left edge outer
  let Bo1: { x: number; y: number }, Bo2: { x: number; y: number }, Cbo1: { x: number; y: number }, Cbo2: { x: number; y: number };
  let Bi2: { x: number; y: number }, Bi1: { x: number; y: number }, Cbi2: { x: number; y: number }, Cbi1: { x: number; y: number };

  if (i === 0 || i === 5) {
    Bo1 = TL; Bo2 = TR; Cbo1 = { x: seg.barX - thirdW, y: yTop }; Cbo2 = { x: seg.barX + thirdW, y: yTop };
    Bi2 = BR; Bi1 = BL; Cbi2 = { x: seg.barX + thirdW, y: Y_BASE }; Cbi1 = { x: seg.barX - thirdW, y: Y_BASE };
  } else if (i === 1 || i === 2) {
    Bo1 = TR; Bo2 = BR; Cbo1 = { x: seg.barX + halfW, y: yTop + currentHeight / 3 }; Cbo2 = { x: seg.barX + halfW, y: Y_BASE - currentHeight / 3 };
    Bi2 = BL; Bi1 = TL; Cbi2 = { x: seg.barX - halfW, y: Y_BASE - currentHeight / 3 }; Cbi1 = { x: seg.barX - halfW, y: yTop + currentHeight / 3 };
  } else if (i === 3) {
    Bo1 = BR; Bo2 = BL; Cbo1 = { x: seg.barX + thirdW, y: Y_BASE }; Cbo2 = { x: seg.barX - thirdW, y: Y_BASE };
    Bi2 = TL; Bi1 = TR; Cbi2 = { x: seg.barX - thirdW, y: yTop }; Cbi1 = { x: seg.barX + thirdW, y: yTop };
  } else {
    Bo1 = BL; Bo2 = TL; Cbo1 = { x: seg.barX - halfW, y: Y_BASE - currentHeight / 3 }; Cbo2 = { x: seg.barX - halfW, y: yTop + currentHeight / 3 };
    Bi2 = TR; Bi1 = BR; Cbi2 = { x: seg.barX + halfW, y: yTop + currentHeight / 3 }; Cbi1 = { x: seg.barX + halfW, y: Y_BASE - currentHeight / 3 };
  }

  // 3. Interpolate points at current morph factor
  const Po1 = { x: lerp(Bo1.x, Do1.x, morphT), y: lerp(Bo1.y, Do1.y, morphT) };
  const Co1 = { x: lerp(Cbo1.x, Cdo1.x, morphT), y: lerp(Cbo1.y, Cdo1.y, morphT) };
  const Co2 = { x: lerp(Cbo2.x, Cdo2.x, morphT), y: lerp(Cbo2.y, Cdo2.y, morphT) };
  const Po2 = { x: lerp(Bo2.x, Do2.x, morphT), y: lerp(Bo2.y, Do2.y, morphT) };

  const Pi2 = { x: lerp(Bi2.x, Di2.x, morphT), y: lerp(Bi2.y, Di2.y, morphT) };
  const Ci2 = { x: lerp(Cbi2.x, Cdi2.x, morphT), y: lerp(Cbi2.y, Cdi2.y, morphT) };
  const Ci1 = { x: lerp(Cbi1.x, Cdi1.x, morphT), y: lerp(Cbi1.y, Cdi1.y, morphT) };
  const Pi1 = { x: lerp(Bi1.x, Di1.x, morphT), y: lerp(Bi1.y, Di1.y, morphT) };

  const d = `M ${Po1.x.toFixed(2)} ${Po1.y.toFixed(2)} C ${Co1.x.toFixed(2)} ${Co1.y.toFixed(2)}, ${Co2.x.toFixed(2)} ${Co2.y.toFixed(2)}, ${Po2.x.toFixed(2)} ${Po2.y.toFixed(2)} L ${Pi2.x.toFixed(2)} ${Pi2.y.toFixed(2)} C ${Ci2.x.toFixed(2)} ${Ci2.y.toFixed(2)}, ${Ci1.x.toFixed(2)} ${Ci1.y.toFixed(2)}, ${Pi1.x.toFixed(2)} ${Pi1.y.toFixed(2)} Z`;

  return { d, yTop };
}

export const AnimatedChartMorph: React.FC<AnimatedChartMorphProps> = ({
  isReducedMotion = false,
  subscribeToFrames,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const pathRefs = useRef<(SVGPathElement | null)[]>([]);
  const valueTextRefs = useRef<(SVGTextElement | null)[]>([]);
  const labelsGroupRef = useRef<SVGGElement>(null);
  const gridGroupRef = useRef<SVGGElement>(null);
  const centerBadgeRef = useRef<SVGGElement>(null);

  useEffect(() => {
    if (isReducedMotion) {
      if (containerRef.current) {
        containerRef.current.style.opacity = '1';
        containerRef.current.style.display = 'flex';
      }
      SEGMENTS.forEach((seg, i) => {
        const pathEl = pathRefs.current[i];
        if (pathEl) {
          const { d } = computeSegmentPath(seg, i, 1, 1);
          pathEl.setAttribute('d', d);
        }
      });
      if (labelsGroupRef.current) labelsGroupRef.current.style.opacity = '0';
      if (gridGroupRef.current) gridGroupRef.current.style.opacity = '0';
      if (centerBadgeRef.current) {
        centerBadgeRef.current.style.opacity = '1';
        centerBadgeRef.current.style.transform = 'scale(1)';
      }
      return;
    }

    if (!subscribeToFrames) return;

    const unsubscribe = subscribeToFrames((elapsedMs: number) => {
      const container = containerRef.current;
      if (!container) return;

      const t = elapsedMs;
      let layerOpacity: number;
      let morphT = 0;
      let labelsOpacity: number;
      let showDonutCenter: boolean;

      // 0.00–3.35s: Invisible
      if (t < PIPELINE_TIMING.cleanToChart[0]) {
        layerOpacity = 0;
        morphT = 0;
        labelsOpacity = 0;
        showDonutCenter = false;
      }
      // 3.35–4.00s: Transition from Structured Data into Chart Visualization
      else if (t < PIPELINE_TIMING.cleanToChart[1]) {
        const enterProgress = (t - PIPELINE_TIMING.cleanToChart[0]) / (PIPELINE_TIMING.cleanToChart[1] - PIPELINE_TIMING.cleanToChart[0]);
        layerOpacity = enterProgress;
        morphT = 0;
        labelsOpacity = enterProgress;
        showDonutCenter = false;
      }
      // 4.00–4.95s: Bar Chart Growth (Linear staggered upward growth)
      else if (t < PIPELINE_TIMING.barChart[1]) {
        layerOpacity = 1;
        morphT = 0;
        labelsOpacity = 1;
        showDonutCenter = false;
      }
      // 4.95–5.95s: Bar to Donut Morph (Continuous shape morphing)
      else if (t < PIPELINE_TIMING.barToDonut[1]) {
        const morphProgress = (t - PIPELINE_TIMING.barToDonut[0]) / (PIPELINE_TIMING.barToDonut[1] - PIPELINE_TIMING.barToDonut[0]);
        layerOpacity = 1;
        morphT = smoothStep(morphProgress);
        labelsOpacity = Math.max(0, 1 - morphProgress * 2.5);
        showDonutCenter = morphProgress > 0.7;
      }
      // 5.95–6.55s: Completed Donut State (Fully settled)
      else if (t < PIPELINE_TIMING.donutComplete[1]) {
        layerOpacity = 1;
        morphT = 1;
        labelsOpacity = 0;
        showDonutCenter = true;
      }
      // 6.55–7.00s: Infinite Loop Reset (Dissolves back toward raw scene)
      else {
        const resetProgress = (t - PIPELINE_TIMING.loopReset[0]) / (PIPELINE_TIMING.loopReset[1] - PIPELINE_TIMING.loopReset[0]);
        layerOpacity = Math.max(0, 1 - resetProgress);
        morphT = 1;
        labelsOpacity = 0;
        showDonutCenter = true;
      }

      container.style.opacity = layerOpacity.toFixed(3);
      

      if (layerOpacity > 0.001) {
        // Calculate each bar's individual growth
        SEGMENTS.forEach((seg, i) => {
          let segGrowth: number;

          if (t < PIPELINE_TIMING.barChart[0]) {
            segGrowth = 0;
          } else if (t < PIPELINE_TIMING.barChart[1]) {
            // Linear height growth with staggered bar introduction (45ms stagger per bar, 600ms growth duration)
            const staggerDelay = i * 45;
            const segElapsed = t - (PIPELINE_TIMING.barChart[0] + staggerDelay);
            segGrowth = Math.min(1, Math.max(0, segElapsed / 600));
          } else {
            segGrowth = 1;
          }

          const { d, yTop } = computeSegmentPath(seg, i, segGrowth, morphT);

          const pathEl = pathRefs.current[i];
          if (pathEl) {
            pathEl.setAttribute('d', d);
            pathEl.setAttribute('filter', morphT > 0.5 ? 'url(#donut-segment-shadow)' : '');
          }

          const valEl = valueTextRefs.current[i];
          if (valEl) {
            valEl.setAttribute('y', (yTop - 6).toFixed(1));
            valEl.style.opacity = segGrowth > 0.1 ? '1' : '0';
          }
        });

        if (labelsGroupRef.current) {
          labelsGroupRef.current.style.opacity = labelsOpacity.toFixed(3);
        }
        if (gridGroupRef.current) {
          gridGroupRef.current.style.opacity = labelsOpacity.toFixed(3);
        }
        if (centerBadgeRef.current) {
          const badgeOpacity = showDonutCenter ? Math.min(1, Math.max(0, (morphT - 0.75) / 0.25)) : 0;
          const badgeScale = 0.85 + 0.15 * badgeOpacity;
          centerBadgeRef.current.style.opacity = badgeOpacity.toFixed(2);
          centerBadgeRef.current.style.transform = `scale(${badgeScale})`;
        }
      }
    });

    return unsubscribe;
  }, [subscribeToFrames, isReducedMotion]);

  // Initial path values computed for first render
  const initialPaths = SEGMENTS.map((seg, i) =>
    computeSegmentPath(seg, i, isReducedMotion ? 1 : 0, isReducedMotion ? 1 : 0)
  );

  return (
    <div
      ref={containerRef}
      className="chart-morph-container"
      style={{
        opacity: isReducedMotion ? 1 : 0,
        display: 'flex',
        position: 'absolute',
        inset: 0,
        alignItems: 'center',
        justifyContent: 'center',
        pointerEvents: 'none',
        overflow: 'hidden',
        willChange: 'opacity',
      }}
    >
      <svg
        viewBox="0 0 400 176"
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%', overflow: 'visible' }}
      >
        <defs>
          <filter id="donut-segment-shadow" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="2" stdDeviation="2" floodColor="#151915" floodOpacity="0.08" />
          </filter>
        </defs>

        {/* Gridlines & Baseline */}
        <g ref={gridGroupRef} style={{ opacity: isReducedMotion ? 0 : 0 }}>
          <line x1="45" y1={Y_BASE} x2="355" y2={Y_BASE} stroke="#E5EBDD" strokeWidth="1.5" />
          <line x1="45" y1="110" x2="355" y2="110" stroke="#F0F4EC" strokeWidth="1" strokeDasharray="3 3" />
          <line x1="45" y1="72" x2="355" y2="72" stroke="#F0F4EC" strokeWidth="1" strokeDasharray="3 3" />
        </g>

        {/* Morphed Segments (Existing SVG paths are updated directly, never recreated!) */}
        {SEGMENTS.map((seg, i) => (
          <path
            key={seg.label}
            ref={(el) => {
              pathRefs.current[i] = el;
            }}
            d={initialPaths[i].d}
            fill={seg.color}
            filter={isReducedMotion ? 'url(#donut-segment-shadow)' : undefined}
          />
        ))}

        {/* Bar Values & Axis Labels */}
        <g ref={labelsGroupRef} style={{ opacity: isReducedMotion ? 0 : 0 }}>
          {SEGMENTS.map((seg, i) => (
            <g key={`label-${seg.label}`}>
              {/* Value label above bar */}
              <text
                ref={(el) => {
                  valueTextRefs.current[i] = el;
                }}
                x={seg.barX}
                y={initialPaths[i].yTop - 6}
                textAnchor="middle"
                fill="#151915"
                fontSize="8.5"
                fontWeight="700"
                fontFamily="ui-monospace, SFMono-Regular, monospace"
              >
                {seg.value}%
              </text>
              {/* Category label below baseline */}
              <text
                x={seg.barX}
                y="161"
                textAnchor="middle"
                fill="#737D6E"
                fontSize="8"
                fontWeight="600"
                fontFamily="ui-monospace, SFMono-Regular, monospace"
              >
                {seg.category}
              </text>
            </g>
          ))}
        </g>

        {/* Donut Center Metric Badge */}
        <g
          ref={centerBadgeRef}
          style={{
            opacity: isReducedMotion ? 1 : 0,
            transform: isReducedMotion ? 'scale(1)' : 'scale(0.85)',
            transformOrigin: `${CX}px ${CY}px`,

            willChange: 'opacity, transform',
          }}
        >
          <circle cx={CX} cy={CY} r={R_IN - 3} fill="#FAFBF7" />

          <text
            x={CX}
            y={CY - 2}
            textAnchor="middle"
            fill="#151915"
            fontSize="12.5"
            fontWeight="800"
            fontFamily="-apple-system, BlinkMacSystemFont, sans-serif"
          >
            99.8%
          </text>
          <text
            x={CX}
            y={CY + 10}
            textAnchor="middle"
            fill="#737D6E"
            fontSize="7"
            fontWeight="700"
            letterSpacing="0.06em"
            fontFamily="ui-monospace, SFMono-Regular, monospace"
          >
            VALID
          </text>
        </g>
      </svg>
    </div>
  );
};
