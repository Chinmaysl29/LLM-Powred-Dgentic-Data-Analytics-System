import { useState, useEffect, useRef, useMemo, useId } from 'react';
import { motion, useReducedMotion, useInView, animate } from 'motion/react';
import { useAppearance } from '../hooks/useAppearance';
function useChartReducedMotion() { const system = useReducedMotion(); const { appearance } = useAppearance(); return system || appearance.reducedMotion; }
import { AlertCircle, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import type {
  ChartPoint,
  ScatterPoint,
  HeatmapData,
  TreemapData,
  TableData,
} from '../lib/chartDataTransforms';
import { parseNumeric } from '../lib/chartDataTransforms';
import {
  WORLD_MAP_COUNTRIES,
  normalizeGeoLocation,
  getPinkChoroplethColor,
} from '../lib/worldMapData';
import type { WorldCountryShape } from '../lib/worldMapData';

export type { ChartPoint, ScatterPoint, HeatmapData, TreemapData, TableData };

const VIZ_PALETTE = ['#b3d779', '#789b48', '#a0b69a', '#52755b', '#c8fd39', '#829b8b', '#d5ddc9', '#42604a'];

function formatCompactNumber(value: number, prefix = ''): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${prefix}${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${prefix}${(value / 1_000).toFixed(1)}K`;
  return `${prefix}${Math.round(value).toLocaleString()}`;
}

// ---------------------------------------------------------------------------
// 0. INVALID CONFIGURATION MESSAGE
// ---------------------------------------------------------------------------

export function InvalidConfigMessage({
  message,
  onReset,
}: {
  message?: string;
  onReset?: () => void;
}) {
  return (
    <div className="viz-invalid-config" role="alert">
      <div className="viz-invalid-config-icon">
        <AlertCircle size={22} aria-hidden="true" />
      </div>
      <strong>Configuration Notice</strong>
      <p>{message || 'The selected field combination is incompatible with this chart type.'}</p>
      {onReset && (
        <button type="button" onClick={onReset}>
          Auto-Fix Field Mapping
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1. ANIMATED COUNT-UP (KPI & METRICS)
// ---------------------------------------------------------------------------

interface AnimatedCountUpProps {
  targetValue: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  decimals?: number;
  formatAsCompact?: boolean;
  className?: string;
  replayKey?: string | number;
}

export function AnimatedCountUp({
  targetValue,
  prefix = '',
  suffix = '',
  duration = 1000,
  decimals = 0,
  formatAsCompact = false,
  className = '',
  replayKey,
}: AnimatedCountUpProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const containerRef = useRef<HTMLSpanElement>(null);
  const inView = useInView(containerRef, { amount: 0.15 });
  const [animatedValue, setAnimatedValue] = useState<number>(0);

  useEffect(() => {
    if (prefersReducedMotion || !inView) return;

    const controls = animate(0, targetValue, {
      duration: duration / 1000,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest) => {
        setAnimatedValue(latest);
      },
      onComplete: () => {
        setAnimatedValue(targetValue);
      },
    });

    return () => controls.stop();
  }, [inView, targetValue, duration, prefersReducedMotion, replayKey]);

  const displayValue = prefersReducedMotion ? targetValue : (inView ? animatedValue : 0);

  const formatted = formatAsCompact
    ? formatCompactNumber(displayValue, prefix) + suffix
    : `${prefix}${decimals > 0 ? displayValue.toFixed(decimals) : Math.round(displayValue).toLocaleString()}${suffix}`;

  return (
    <span ref={containerRef} className={`viz-glow-countup ${className}`}>
      {formatted}
    </span>
  );
}

// ---------------------------------------------------------------------------
// 2. SELF-FORMING TREND / LINE & AREA CHART (MODE B & MODE C COMET)
// ---------------------------------------------------------------------------

interface SelfFormingLineChartProps {
  data: ChartPoint[];
  ariaLabel: string;
  isArea?: boolean;
  replayKey?: string | number;
}

export function SelfFormingLineChart({
  data,
  ariaLabel,
  isArea = false,
  replayKey,
}: SelfFormingLineChartProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const width = 540;
  const height = 190;
  const filterId = useId().replace(/:/g, '');

  const [activeHoverPoint, setActiveHoverPoint] = useState<{
    x: number;
    y: number;
    label: string;
    value: number;
    group?: string;
  } | null>(null);

  const containerRef = useRef<SVGSVGElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });

  const max = Math.max(...data.map((item) => item.value), 1);
  const plotted = data.slice(0, 16);
  const points = useMemo(() => {
    return plotted.map((item, index) => {
      const x = plotted.length <= 1 ? width / 2 : (index / (plotted.length - 1)) * (width - 40) + 20;
      const y = height - 34 - (item.value / max) * 128;
      return { ...item, x, y };
    });
  }, [plotted, max, width, height]);

  // Find peak point for Glow Highlight
  const peakIndex = useMemo(() => {
    let bestIdx = 0;
    let bestVal = -Infinity;
    points.forEach((p, idx) => {
      if (p.value > bestVal) {
        bestVal = p.value;
        bestIdx = idx;
      }
    });
    return bestIdx;
  }, [points]);

  // Build SVG path string
  const pathD = useMemo(() => {
    if (points.length === 0) return '';
    return points.reduce((acc, curr, idx) => {
      return idx === 0 ? `M ${curr.x} ${curr.y}` : `${acc} L ${curr.x} ${curr.y}`;
    }, '');
  }, [points]);

  // Area path closing down to bottom
  const areaD = useMemo(() => {
    if (points.length === 0) return '';
    const lastX = points[points.length - 1]?.x ?? width;
    const firstX = points[0]?.x ?? 20;
    return `${pathD} L ${lastX} ${height} L ${firstX} ${height} Z`;
  }, [pathD, points, width, height]);

  const animDuration = prefersReducedMotion ? 0 : 1.1;
  const animDelay = prefersReducedMotion ? 0 : 0.2;
  const highlightDelay = prefersReducedMotion ? 0 : animDelay + animDuration + 0.15;

  return (
    <div key={replayKey} className="viz-chart-wrapper" style={{ position: 'relative' }}>
      <svg
        ref={containerRef}
        className="viz-line-chart viz-animated-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
        onMouseLeave={() => setActiveHoverPoint(null)}
      >
        <defs>
          <linearGradient id={`vizRevenueLine-${filterId}`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#35d9ff" />
            <stop offset="50%" stopColor="#64f2ff" />
            <stop offset="100%" stopColor="#9b5cff" />
          </linearGradient>
          <linearGradient id={`vizRevenueArea-${filterId}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#5d6dff" stopOpacity="0.45" />
            <stop offset="50%" stopColor="#35d9ff" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#5d6dff" stopOpacity="0" />
          </linearGradient>
          <filter id={`lineGlow-${filterId}`} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Chart Grid Lines */}
        <motion.path
          className="viz-chart-grid"
          d="M0 35H540M0 80H540M0 125H540M90 0V190M180 0V190M270 0V190M360 0V190M450 0V190"
          initial={{ opacity: prefersReducedMotion ? 1 : 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5 }}
        />

        {/* Area fill */}
        {isArea && (
          <motion.path
            key={`area-${replayKey}`}
            className="viz-chart-area"
            fill={`url(#vizRevenueArea-${filterId})`}
            d={areaD}
            initial={{ opacity: prefersReducedMotion ? 1 : 0 }}
            animate={{ opacity: 1 }}
            transition={{
              duration: animDuration * 1.1,
              delay: animDelay,
              ease: 'easeOut',
            }}
          />
        )}

        {/* Ambient Glow behind main line */}
        <motion.path
          key={`ambient-line-${replayKey}`}
          d={pathD}
          fill="none"
          stroke="#64f2ff"
          strokeWidth="7"
          strokeOpacity="0.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          filter={`url(#lineGlow-${filterId})`}
          initial={{ pathLength: prefersReducedMotion ? 1 : 0, opacity: prefersReducedMotion ? 0.6 : 0 }}
          animate={{ pathLength: 1, opacity: 0.6 }}
          transition={{
            duration: animDuration,
            delay: animDelay,
            ease: [0.16, 1, 0.3, 1],
          }}
        />

        {/* Progressive Trend Line Draw */}
        <motion.path
          key={`line-${replayKey}`}
          d={pathD}
          fill="none"
          stroke={`url(#vizRevenueLine-${filterId})`}
          strokeWidth="3.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: prefersReducedMotion ? 1 : 0 }}
          animate={{ pathLength: 1 }}
          transition={{
            duration: animDuration,
            delay: animDelay,
            ease: [0.16, 1, 0.3, 1],
          }}
        />

        {/* Comet / Flow leading bead */}
        {!prefersReducedMotion && points.length > 1 && (
          <motion.circle
            r="4.5"
            fill="#ffffff"
            stroke="#64f2ff"
            strokeWidth="2.5"
            className="viz-comet-head"
            initial={{ offsetDistance: '0%', opacity: 1, scale: 1.4 }}
            animate={{ offsetDistance: '100%', opacity: [1, 1, 0], scale: [1.4, 1.2, 0.8] }}
            transition={{
              duration: animDuration,
              delay: animDelay,
              ease: [0.16, 1, 0.3, 1],
            }}
            style={{
              offsetPath: `path('${pathD}')`,
              filter: 'drop-shadow(0 0 8px #64f2ff) drop-shadow(0 0 14px #35d9ff)',
            }}
          />
        )}

        {/* Data points reveal */}
        {points.map((point, index) => {
          const isPeak = index === peakIndex;
          const pointDelay = prefersReducedMotion
            ? 0
            : animDelay + (index / (points.length - 1 || 1)) * animDuration * 0.9;

          return (
            <g key={`${point.label}-${index}`}>
              {isPeak && (
                <motion.circle
                  cx={point.x}
                  cy={point.y}
                  r="13"
                  fill="none"
                  stroke="#64f2ff"
                  strokeWidth="1.5"
                  className="viz-peak-halo"
                  initial={{ scale: prefersReducedMotion ? 1 : 0, opacity: prefersReducedMotion ? 0.6 : 0 }}
                  animate={{ scale: [0.8, 1.4, 1.1], opacity: [0, 0.9, 0.6] }}
                  transition={{
                    delay: highlightDelay,
                    duration: 1.4,
                    repeat: Infinity,
                    repeatType: 'reverse',
                  }}
                />
              )}

              <motion.circle
                cx={point.x}
                cy={point.y}
                r={isPeak ? 5.5 : 4}
                className={isPeak ? 'viz-chart-point viz-chart-point--peak' : 'viz-chart-point'}
                initial={{ scale: prefersReducedMotion ? 1 : 0, opacity: prefersReducedMotion ? 1 : 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{
                  delay: pointDelay,
                  duration: 0.3,
                  type: 'spring',
                  stiffness: 400,
                  damping: 20,
                }}
                whileHover={{ scale: 1.6 }}
                style={{
                  cursor: 'pointer',
                  filter: isPeak ? 'drop-shadow(0 0 6px #64f2ff)' : undefined,
                }}
                onMouseEnter={() => setActiveHoverPoint(point)}
              />

              {isPeak && (
                <motion.g
                  initial={{ opacity: prefersReducedMotion ? 1 : 0, y: prefersReducedMotion ? 0 : 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: highlightDelay + 0.1, duration: 0.4 }}
                >
                  <rect
                    x={point.x - 30}
                    y={Math.max(point.y - 28, 4)}
                    width="60"
                    height="20"
                    rx="10"
                    fill="rgba(10, 18, 32, 0.92)"
                    stroke="#64f2ff"
                    strokeWidth="1"
                    filter="drop-shadow(0 2px 6px rgba(0,0,0,0.4))"
                  />
                  <text
                    x={point.x}
                    y={Math.max(point.y - 14, 18)}
                    textAnchor="middle"
                    fill="#64f2ff"
                    fontSize="9.5"
                    fontWeight="700"
                  >
                    {formatCompactNumber(point.value)}
                  </text>
                </motion.g>
              )}
            </g>
          );
        })}

        {/* X-axis labels */}
        <g className="viz-axis-labels">
          {points.map((point, index) => {
            const labelDelay = prefersReducedMotion
              ? 0
              : animDelay + animDuration * 0.4 + index * 0.04;
            return (
              <motion.text
                key={`label-${point.label}-${index}`}
                x={point.x}
                y="182"
                textAnchor="middle"
                initial={{ opacity: prefersReducedMotion ? 1 : 0, y: prefersReducedMotion ? 0 : 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: labelDelay, duration: 0.35 }}
              >
                {point.label.slice(0, 7)}
              </motion.text>
            );
          })}
        </g>
      </svg>

      {/* Floating Tooltip */}
      {activeHoverPoint && (
        <div
          className="viz-floating-tooltip"
          style={{
            position: 'absolute',
            left: `${(activeHoverPoint.x / width) * 100}%`,
            top: `${(activeHoverPoint.y / height) * 100}%`,
            transform: 'translate(-50%, -125%)',
            pointerEvents: 'none',
            zIndex: 10,
          }}
        >
          <div className="viz-tooltip-card">
            <span className="viz-tooltip-label">{activeHoverPoint.label}</span>
            <strong className="viz-tooltip-val">
              {formatCompactNumber(activeHoverPoint.value)}
            </strong>
            {activeHoverPoint.group && (
              <em className="viz-tooltip-group">{activeHoverPoint.group}</em>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3. SELF-FORMING BAR / COLUMN CHART (MODE A — COLUMNS)
// ---------------------------------------------------------------------------

interface SelfFormingBarChartProps {
  data: ChartPoint[];
  ariaLabel: string;
  replayKey?: string | number;
}

export function SelfFormingBarChart({
  data,
  ariaLabel,
  replayKey,
}: SelfFormingBarChartProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const validData = Array.isArray(data)
    ? data.filter((d) => d && typeof d.label === 'string' && Number.isFinite(d.value))
    : [];

  if (validData.length === 0) {
    return <div className="viz-empty">No bar chart data available.</div>;
  }

  const max = Math.max(...validData.map((item) => item.value), 1);
  const plotted = validData.slice(0, 16);

  return (
    <div
      key={replayKey}
      ref={containerRef}
      className="viz-bar-chart viz-animated-bars"
      role="img"
      aria-label={ariaLabel}
      onMouseLeave={() => setHoveredIdx(null)}
    >
      {plotted.map((item, index) => {
        const heightPercent = Math.max(8, (item.value / max) * 100);
        const barDelay = prefersReducedMotion ? 0 : 0.12 + index * 0.06;
        const color = VIZ_PALETTE[index % VIZ_PALETTE.length];
        const isHovered = hoveredIdx === index;

        return (
          <div
            key={`${item.label}-${item.group ?? index}`}
            onMouseEnter={() => setHoveredIdx(index)}
            style={{ cursor: 'pointer' }}
          >
            {/* Value Label */}
            <motion.b
              initial={{ opacity: prefersReducedMotion ? 1 : 0, y: prefersReducedMotion ? 0 : 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: barDelay + 0.2, duration: 0.25 }}
              style={{
                color: isHovered ? '#64f2ff' : 'rgba(246, 250, 255, 0.9)',
                transform: isHovered ? 'scale(1.08)' : 'scale(1)',
                transition: 'color 0.2s, transform 0.2s',
              }}
            >
              {formatCompactNumber(item.value)}
            </motion.b>

            {/* Rising Bar */}
            <div className="viz-bar-track" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'flex-end' }}>
              <motion.span
                className="viz-bar-fill"
                initial={{ height: prefersReducedMotion ? `${heightPercent}%` : '0%' }}
                animate={{ height: `${heightPercent}%` }}
                transition={{
                  delay: barDelay,
                  duration: prefersReducedMotion ? 0 : 0.65,
                  ease: [0.22, 1, 0.36, 1],
                }}
                style={{
                  width: '100%',
                  height: `${heightPercent}%`,
                  background: isHovered
                    ? `linear-gradient(180deg, #64f2ff, ${color})`
                    : `linear-gradient(180deg, ${color}, #1f4bbd)`,
                  borderRadius: '5px 5px 0 0',
                  boxShadow: isHovered
                    ? `0 0 16px ${color}, 0 -2px 8px rgba(100, 242, 255, 0.5)`
                    : `0 0 10px rgba(66, 148, 255, 0.15)`,
                  transition: 'box-shadow 0.25s, background 0.25s',
                  position: 'relative',
                }}
              >
                <span
                  className="viz-bar-highlight-cap"
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: '2px',
                    background: 'rgba(255, 255, 255, 0.65)',
                    borderRadius: '5px 5px 0 0',
                    boxShadow: '0 0 8px rgba(255, 255, 255, 0.8)',
                  }}
                />
              </motion.span>
            </div>

            {/* X-axis Label & Group */}
            <motion.em
              initial={{ opacity: prefersReducedMotion ? 1 : 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: barDelay + 0.25, duration: 0.25 }}
              style={{
                color: isHovered ? '#ffffff' : 'rgba(220, 231, 246, 0.6)',
                fontWeight: isHovered ? 600 : 400,
              }}
            >
              {item.label}
              {item.group && <span style={{ display: 'block', fontSize: '8.5px', color: '#9b5cff' }}>{item.group}</span>}
            </motion.em>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 4. SELF-FORMING DONUT & PIE CHART
// ---------------------------------------------------------------------------

interface SelfFormingDonutChartProps {
  data: ChartPoint[];
  ariaLabel: string;
  isPie?: boolean;
  replayKey?: string | number;
}

export function SelfFormingDonutChart({
  data,
  ariaLabel,
  isPie = false,
  replayKey,
}: SelfFormingDonutChartProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const validData = Array.isArray(data)
    ? data.filter((d) => d && typeof d.label === 'string' && Number.isFinite(d.value) && d.value >= 0)
    : [];

  const containerRef = useRef<HTMLDivElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (validData.length === 0) {
    return <div className="viz-empty">No pie chart data available.</div>;
  }

  const total = validData.reduce((sum, item) => sum + item.value, 0) || 1;
  const plotted = validData.slice(0, 6);

  const segments = plotted.reduce<{ stops: string[]; offset: number }>(
    (acc, item, index) => {
      const start = acc.offset;
      const percent = (item.value / total) * 100;
      const nextOffset = start + percent;
      const color = VIZ_PALETTE[index % VIZ_PALETTE.length];
      return {
        stops: [...acc.stops, `${color} ${start}% ${nextOffset}%`],
        offset: nextOffset,
      };
    },
    { stops: [], offset: 0 }
  ).stops;

  return (
    <div
      key={replayKey}
      ref={containerRef}
      className="viz-donut-wrap viz-animated-donut"
      role="img"
      aria-label={ariaLabel}
    >
      <div style={{ position: 'relative', display: 'grid', placeItems: 'center' }}>
        <motion.div
          style={{
            position: 'absolute',
            width: '144px',
            height: '144px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(100, 242, 255, 0.22) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
          initial={{ opacity: prefersReducedMotion ? 1 : 0, scale: prefersReducedMotion ? 1 : 0.8 }}
          animate={{ opacity: 1, scale: 1.15 }}
          transition={{ delay: 0.3, duration: 0.6 }}
        />

        <motion.div
          className={isPie ? 'viz-donut viz-donut--pie' : 'viz-donut'}
          style={{
            background: `conic-gradient(${segments.join(', ')})`,
            boxShadow: '0 4px 20px rgba(0, 0, 0, 0.35)',
          }}
          initial={{
            scale: prefersReducedMotion ? 1 : 0.8,
            rotate: prefersReducedMotion ? 0 : -45,
            opacity: prefersReducedMotion ? 1 : 0,
          }}
          animate={{ scale: 1, rotate: 0, opacity: 1 }}
          transition={{
            duration: prefersReducedMotion ? 0 : 0.75,
            ease: [0.16, 1, 0.3, 1],
          }}
        >
          {!isPie && (
            <div>
              <strong>
                <AnimatedCountUp
                  targetValue={total}
                  formatAsCompact
                  prefix="$"
                  duration={900}
                  replayKey={replayKey}
                />
              </strong>
              <span>Total</span>
            </div>
          )}
        </motion.div>
      </div>

      <ul className="viz-legend" onMouseLeave={() => setHoveredIdx(null)}>
        {plotted.map((item, index) => {
          const color = VIZ_PALETTE[index % VIZ_PALETTE.length];
          const percent = Math.round((item.value / total) * 100);
          const itemDelay = prefersReducedMotion ? 0 : 0.2 + index * 0.06;
          const isHovered = hoveredIdx === index;

          return (
            <motion.li
              key={item.label}
              initial={{ opacity: prefersReducedMotion ? 1 : 0, x: prefersReducedMotion ? 0 : -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: itemDelay, duration: 0.25 }}
              onMouseEnter={() => setHoveredIdx(index)}
              style={{
                cursor: 'pointer',
                padding: '3px 6px',
                borderRadius: '5px',
                background: isHovered ? 'rgba(255, 255, 255, 0.06)' : 'transparent',
                transition: 'background 0.2s',
              }}
            >
              <span
                style={{
                  background: color,
                  boxShadow: isHovered ? `0 0 8px ${color}` : undefined,
                  transition: 'box-shadow 0.2s',
                }}
              />
              <b style={{ color: isHovered ? '#64f2ff' : undefined }}>{item.label}</b>
              <em>{percent}%</em>
            </motion.li>
          );
        })}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 5. SELF-FORMING SCATTER CHART (TRUE NUMERIC X & Y)
// ---------------------------------------------------------------------------

interface SelfFormingScatterChartProps {
  scatterPoints?: ScatterPoint[];
  bounds?: { minX: number; maxX: number; minY: number; maxY: number };
  ariaLabel: string;
  replayKey?: string | number;
}

export function SelfFormingScatterChart({
  scatterPoints = [],
  bounds,
  ariaLabel,
  replayKey,
}: SelfFormingScatterChartProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const width = 540;
  const height = 190;
  const containerRef = useRef<SVGSVGElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });

  const [activeHoverPoint, setActiveHoverPoint] = useState<{
    x: number;
    y: number;
    plotX: number;
    plotY: number;
    label: string;
    group?: string;
  } | null>(null);

  const minX = bounds?.minX ?? 0;
  const maxX = bounds?.maxX ?? 100;
  const minY = bounds?.minY ?? 0;
  const maxY = bounds?.maxY ?? 100;

  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;

  const plotted = useMemo(() => {
    return scatterPoints.map((pt) => {
      const plotX = 40 + ((pt.x - minX) / rangeX) * (width - 70);
      const plotY = height - 34 - ((pt.y - minY) / rangeY) * 128;
      return { ...pt, plotX, plotY };
    });
  }, [scatterPoints, minX, minY, rangeX, rangeY, width, height]);

  return (
    <div key={replayKey} className="viz-chart-wrapper" style={{ position: 'relative' }}>
      <svg
        ref={containerRef}
        className="viz-line-chart viz-animated-scatter"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
        onMouseLeave={() => setActiveHoverPoint(null)}
      >
        {/* Grid lines */}
        <path
          className="viz-chart-grid"
          d="M40 30H520M40 70H520M40 110H520M40 150H520M40 30V150M160 30V150M280 30V150M400 30V150M520 30V150"
        />

        {/* Y Axis ticks */}
        <g className="viz-axis-labels">
          <text x="32" y="34" textAnchor="end">{formatCompactNumber(maxY)}</text>
          <text x="32" y="94" textAnchor="end">{formatCompactNumber(minY + rangeY * 0.5)}</text>
          <text x="32" y="154" textAnchor="end">{formatCompactNumber(minY)}</text>
        </g>

        {/* X Axis ticks */}
        <g className="viz-axis-labels">
          <text x="40" y="174" textAnchor="middle">{Math.round(minX).toLocaleString()}</text>
          <text x="280" y="174" textAnchor="middle">{Math.round(minX + rangeX * 0.5).toLocaleString()}</text>
          <text x="520" y="174" textAnchor="middle">{Math.round(maxX).toLocaleString()}</text>
        </g>

        {/* Plotted Scatter Points */}
        {plotted.map((pt, idx) => {
          const delay = prefersReducedMotion ? 0 : 0.08 + idx * 0.025;
          return (
            <motion.circle
              key={`${pt.label}-${idx}`}
              cx={pt.plotX}
              cy={pt.plotY}
              r="5"
              fill="#64f2ff"
              stroke="#13233c"
              strokeWidth="2"
              initial={{ scale: prefersReducedMotion ? 1 : 0, opacity: prefersReducedMotion ? 0.95 : 0 }}
              animate={{ scale: 1, opacity: 0.95 }}
              transition={{ delay, duration: 0.35, type: 'spring', stiffness: 350 }}
              whileHover={{ scale: 1.8, fill: '#ffffff' }}
              style={{
                cursor: 'pointer',
                filter: 'drop-shadow(0 0 6px rgba(100, 242, 255, 0.75))',
              }}
              onMouseEnter={() => setActiveHoverPoint(pt)}
            />
          );
        })}
      </svg>

      {/* Hover tooltip */}
      {activeHoverPoint && (
        <div
          className="viz-floating-tooltip"
          style={{
            position: 'absolute',
            left: `${(activeHoverPoint.plotX / width) * 100}%`,
            top: `${(activeHoverPoint.plotY / height) * 100}%`,
            transform: 'translate(-50%, -125%)',
            pointerEvents: 'none',
            zIndex: 10,
          }}
        >
          <div className="viz-tooltip-card">
            <span className="viz-tooltip-label">{activeHoverPoint.label}</span>
            <strong className="viz-tooltip-val">
              Y: {formatCompactNumber(activeHoverPoint.y)}
            </strong>
            <span style={{ fontSize: '11px', color: '#64f2ff' }}>
              X: {Math.round(activeHoverPoint.x).toLocaleString()}
            </span>
            {activeHoverPoint.group && (
              <em className="viz-tooltip-group">{activeHoverPoint.group}</em>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 6. SELF-FORMING 2D MATRIX HEATMAP
// ---------------------------------------------------------------------------

interface SelfFormingHeatmapProps {
  heatmapData?: HeatmapData;
  ariaLabel: string;
  replayKey?: string | number;
}

export function SelfFormingHeatmap({
  heatmapData,
  ariaLabel,
  replayKey,
}: SelfFormingHeatmapProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });

  const [activeCell, setActiveCell] = useState<{
    row: string;
    col: string;
    value: number;
    x: number;
    y: number;
  } | null>(null);

  if (!heatmapData || heatmapData.cells.length === 0) {
    return <div className="viz-empty">No heatmap matrix available.</div>;
  }

  const { rowLabels, colLabels, cells } = heatmapData;
  const colCount = colLabels.length;

  return (
    <div
      key={replayKey}
      ref={containerRef}
      className="viz-heatmap-matrix"
      role="img"
      aria-label={ariaLabel}
      onMouseLeave={() => setActiveCell(null)}
      style={{ position: 'relative' }}
    >
      {/* Column Headers */}
      <div
        className="viz-heatmap-header-row"
        style={{
          gridTemplateColumns: `100px repeat(${colCount}, minmax(44px, 1fr))`,
        }}
      >
        <span />
        {colLabels.map((col) => (
          <span key={col} className="viz-heatmap-col-title">
            {col}
          </span>
        ))}
      </div>

      {/* Matrix Data Rows */}
      {rowLabels.map((rowName, rIdx) => {
        return (
          <div
            key={rowName}
            className="viz-heatmap-data-row"
            style={{
              gridTemplateColumns: `100px repeat(${colCount}, minmax(44px, 1fr))`,
            }}
          >
            <span className="viz-heatmap-row-title">{rowName}</span>
            {colLabels.map((colName, cIdx) => {
              const cell = cells.find((c) => c.row === rowName && c.col === colName);
              const val = cell?.value ?? 0;
              const intensity = cell?.intensity ?? 0;
              const delay = prefersReducedMotion ? 0 : 0.05 + (rIdx + cIdx) * 0.035;

              // Dark blue to vibrant cyan gradient based on real value intensity
              const bg = `rgba(53, 217, 255, ${0.12 + intensity * 0.76})`;

              return (
                <motion.div
                  key={`${rowName}-${colName}`}
                  className="viz-heatmap-cell"
                  style={{ background: bg }}
                  initial={{ opacity: prefersReducedMotion ? 1 : 0, scale: prefersReducedMotion ? 1 : 0.85 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay, duration: 0.35 }}
                  onMouseEnter={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const parentRect = containerRef.current?.getBoundingClientRect();
                    if (parentRect) {
                      setActiveCell({
                        row: rowName,
                        col: colName,
                        value: val,
                        x: rect.left - parentRect.left + rect.width / 2,
                        y: rect.top - parentRect.top,
                      });
                    }
                  }}
                >
                  {formatCompactNumber(val)}
                </motion.div>
              );
            })}
          </div>
        );
      })}

      {/* Floating Tooltip */}
      {activeCell && (
        <div
          className="viz-floating-tooltip"
          style={{
            position: 'absolute',
            left: `${activeCell.x}px`,
            top: `${activeCell.y}px`,
            transform: 'translate(-50%, -115%)',
            pointerEvents: 'none',
            zIndex: 10,
          }}
        >
          <div className="viz-tooltip-card">
            <span className="viz-tooltip-label">
              {activeCell.row} × {activeCell.col}
            </span>
            <strong className="viz-tooltip-val">
              {formatCompactNumber(activeCell.value)}
            </strong>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 7. SELF-FORMING PROPORTIONAL TREEMAP
// ---------------------------------------------------------------------------

interface SelfFormingTreemapProps {
  treemapData?: TreemapData;
  ariaLabel: string;
  replayKey?: string | number;
}

export function SelfFormingTreemap({
  treemapData,
  ariaLabel,
  replayKey,
}: SelfFormingTreemapProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });

  if (!treemapData || treemapData.items.length === 0) {
    return <div className="viz-empty">No treemap data available.</div>;
  }

  const { items } = treemapData;

  return (
    <div
      key={replayKey}
      ref={containerRef}
      className="viz-treemap-grid"
      role="img"
      aria-label={ariaLabel}
    >
      {items.map((node, idx) => {
        const delay = prefersReducedMotion ? 0 : 0.08 + idx * 0.05;
        const color = VIZ_PALETTE[node.colorIndex % VIZ_PALETTE.length];

        // Span between 3 and 6 columns out of 12 grid depending on percentage share
        const colSpan = Math.max(3, Math.min(6, Math.round((node.percent / 100) * 12) + 2));

        return (
          <motion.div
            key={node.id}
            className="viz-treemap-tile"
            style={{
              gridColumn: `span ${colSpan}`,
              background: `linear-gradient(145deg, ${color}22, ${color}55)`,
              borderColor: `${color}88`,
            }}
            initial={{ opacity: prefersReducedMotion ? 1 : 0, scale: prefersReducedMotion ? 1 : 0.88 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay, duration: 0.4 }}
          >
            <div className="viz-treemap-tile-header">
              <span className="viz-treemap-tile-label">{node.label}</span>
              <span className="viz-treemap-tile-share">{Math.round(node.percent)}%</span>
            </div>
            <strong className="viz-treemap-tile-val">
              {formatCompactNumber(node.value)}
            </strong>
          </motion.div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 8. SELF-FORMING INTERACTIVE TABLE WITH PAGINATION
// ---------------------------------------------------------------------------

interface SelfFormingTableProps {
  tableData?: TableData;
  ariaLabel: string;
  replayKey?: string | number;
}

export function SelfFormingTable({
  tableData,
  ariaLabel,
  replayKey,
}: SelfFormingTableProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 8;

  const containerRef = useRef<HTMLDivElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });

  if (!tableData || tableData.rows.length === 0) {
    return <div className="viz-empty">No table data available.</div>;
  }

  const { columns, rows } = tableData;
  const totalPages = Math.ceil(rows.length / pageSize) || 1;
  const displayedRows = rows.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <div key={replayKey} ref={containerRef} className="viz-data-table-wrap">
      <table className="viz-data-table">
        <caption>{ariaLabel}</caption>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayedRows.map((row, rIdx) => {
            const delay = prefersReducedMotion ? 0 : 0.03 * rIdx;
            return (
              <motion.tr
                key={`table-row-${rIdx}`}
                initial={{ opacity: prefersReducedMotion ? 1 : 0, y: prefersReducedMotion ? 0 : 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay, duration: 0.25 }}
              >
                {columns.map((col) => {
                  const val = row[col.key];
                  const formatted =
                    col.type === 'number'
                      ? typeof val === 'number'
                        ? col.key.toLowerCase().includes('rate') || col.key.toLowerCase().includes('discount')
                          ? `${val}%`
                          : formatCompactNumber(val, col.key.toLowerCase().includes('price') || col.key.toLowerCase().includes('revenue') || col.key.toLowerCase().includes('profit') ? '$' : '')
                        : '-'
                      : String(val ?? '-');

                  return <td key={col.key}>{formatted}</td>;
                })}
              </motion.tr>
            );
          })}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className="viz-table-pagination">
          <span>
            Page {currentPage} of {totalPages} ({rows.length} total rows)
          </span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              type="button"
              className="viz-table-page-btn"
              disabled={currentPage <= 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft size={13} style={{ verticalAlign: 'middle' }} /> Prev
            </button>
            <button
              type="button"
              className="viz-table-page-btn"
              disabled={currentPage >= totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            >
              Next <ChevronRight size={13} style={{ verticalAlign: 'middle' }} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 9. SELF-FORMING TOP 10 RANKING BARS
// ---------------------------------------------------------------------------

export function SelfFormingRankingBars({
  data,
  replayKey,
}: {
  data: ChartPoint[];
  replayKey?: string | number;
}) {
  const prefersReducedMotion = useChartReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });

  const validData = Array.isArray(data)
    ? data.filter((d) => d && typeof d.label === 'string' && Number.isFinite(d.value))
    : [];

  if (validData.length === 0) {
    return <div className="viz-empty">No ranking data available.</div>;
  }

  const topVal = validData[0]?.value || 1;

  return (
    <div key={replayKey} ref={containerRef} className="viz-ranking viz-animated-ranking">
      {validData.map((item, index) => {
        const targetPercent = Math.max(5, (item.value / topVal) * 100);
        const delay = prefersReducedMotion ? 0 : 0.08 + index * 0.05;

        return (
          <div key={item.label} className="viz-rank-row" style={{ position: 'relative' }}>
            <span>{item.label}</span>
            <b style={{ color: index === 0 ? '#64f2ff' : '#fff' }}>
              {formatCompactNumber(item.value)}
            </b>
            <motion.em
              initial={{ width: prefersReducedMotion ? `${targetPercent}%` : '0%' }}
              animate={{ width: `${targetPercent}%` }}
              transition={{
                delay,
                duration: prefersReducedMotion ? 0 : 0.6,
                ease: [0.16, 1, 0.3, 1],
              }}
              style={{
                width: `${targetPercent}%`,
                boxShadow: index === 0 ? '0 0 10px rgba(100, 242, 255, 0.45)' : undefined,
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 10. SELF-FORMING REGION WORLD CHOROPLETH MAP
// ---------------------------------------------------------------------------

export interface SelfFormingRegionMapProps {
  data: ChartPoint[];
  filteredRows?: Array<Record<string, unknown>>;
  replayKey?: string | number;
}

export function SelfFormingRegionMap({
  data,
  filteredRows,
  replayKey,
}: SelfFormingRegionMapProps) {
  const prefersReducedMotion = useChartReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });

  const [hoveredCountry, setHoveredCountry] = useState<{
    country: WorldCountryShape;
    sales: number;
  } | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });

  // Map dimensions based on equirectangular coordinate space
  const baseWidth = 2000;
  const baseHeight = 1001;

  // Aggregate Sales
  const { countrySalesMap, maxSale, minSale, hasData } = useMemo(() => {
    const cMap = new Map<string, number>();
    const rMap = new Map<string, number>();

    if (Array.isArray(data)) {
      for (const item of data) {
        if (!item || typeof item.label !== 'string') continue;
        const val = parseNumeric(item.value);
        if (val === null || val <= 0) continue;

        const match = normalizeGeoLocation(item.label);
        if (match?.type === 'country') {
          cMap.set(match.id, (cMap.get(match.id) ?? 0) + val);
        } else if (match?.type === 'region') {
          rMap.set(match.region, (rMap.get(match.region) ?? 0) + val);
        }
      }
    }

    if (Array.isArray(filteredRows) && filteredRows.length > 0 && cMap.size === 0 && rMap.size === 0) {
      const sample = filteredRows[0];
      const keys = Object.keys(sample);
      const geoCol = keys.find((k) => /^(country|region|nation|territory|geo)$/i.test(k));
      const valCol = keys.find((k) => /^(revenue|sales|spend|amount|total)$/i.test(k));

      if (geoCol && valCol) {
        for (const row of filteredRows) {
          const rawGeo = row[geoCol];
          const rawVal = parseNumeric(row[valCol]);
          if (rawVal === null || rawVal <= 0) continue;

          const match = normalizeGeoLocation(rawGeo);
          if (match?.type === 'country') {
            cMap.set(match.id, (cMap.get(match.id) ?? 0) + rawVal);
          } else if (match?.type === 'region') {
            rMap.set(match.region, (rMap.get(match.region) ?? 0) + rawVal);
          }
        }
      }
    }

    const finalCountrySales = new Map<string, number>();
    let max = 0;
    let min = Infinity;
    let nonZeroCount = 0;

    for (const c of WORLD_MAP_COUNTRIES) {
      let sales = 0;
      if (cMap.has(c.id)) {
        sales = cMap.get(c.id)!;
      } else if (rMap.has(c.region)) {
        sales = rMap.get(c.region)!;
      }

      if (sales > 0) {
        finalCountrySales.set(c.id, sales);
        if (sales > max) max = sales;
        if (sales < min) min = sales;
        nonZeroCount++;
      }
    }

    return {
      countrySalesMap: finalCountrySales,
      maxSale: max > 0 ? max : 1,
      minSale: min < Infinity ? min : 0,
      hasData: nonZeroCount > 0,
    };
  }, [data, filteredRows]);

  if (!hasData) {
    return (
      <div className="viz-empty" role="status">
        <strong>No regional data available</strong>
        <p style={{ fontSize: '11px', color: 'rgba(255, 180, 210, 0.6)', marginTop: '4px' }}>
          Unable to map regional data to geographic boundaries.
        </p>
      </div>
    );
  }

  // Calculate current viewBox based on zoom and pan
  const currentW = baseWidth / zoom;
  const currentH = baseHeight / zoom;
  const currentX = (baseWidth - currentW) / 2 - pan.x;
  const currentY = (baseHeight - currentH) / 2 - pan.y;
  const viewBoxStr = `${currentX} ${currentY} ${currentW} ${currentH}`;

  const handleZoomIn = () => setZoom((z) => Math.min(3.5, z * 1.3));
  const handleZoomOut = () => {
    setZoom((z) => {
      const next = Math.max(1, z / 1.3);
      if (next === 1) setPan({ x: 0, y: 0 });
      return next;
    });
  };
  const handleResetZoom = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (zoom <= 1) return;
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging && zoom > 1) {
      setPan({
        x: e.clientX - dragStartRef.current.x,
        y: e.clientY - dragStartRef.current.y,
      });
    }

    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setTooltipPos({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });
    }
  };

  const handleMouseUp = () => setIsDragging(false);

  return (
    <div
      key={replayKey}
      ref={containerRef}
      className="viz-region-map"
      role="region"
      aria-label="Sales by Region World Choropleth Map"
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => {
        setIsDragging(false);
        setHoveredCountry(null);
      }}
    >
      {/* Zoom / Pan Controls */}
      <div className="viz-map-controls" role="toolbar" aria-label="Map zoom controls">
        <button
          type="button"
          className="viz-map-btn"
          onClick={handleZoomIn}
          title="Zoom in"
          aria-label="Zoom in"
        >
          <ZoomIn size={13} />
        </button>
        <button
          type="button"
          className="viz-map-btn"
          onClick={handleZoomOut}
          title="Zoom out"
          aria-label="Zoom out"
          disabled={zoom <= 1}
        >
          <ZoomOut size={13} />
        </button>
        {zoom > 1 && (
          <button
            type="button"
            className="viz-map-btn"
            onClick={handleResetZoom}
            title="Reset map view"
            aria-label="Reset map view"
          >
            <RotateCcw size={12} />
          </button>
        )}
      </div>

      {/* World Map SVG Container */}
      <div
        className="viz-map-svg-wrap"
        onMouseDown={handleMouseDown}
        style={{ cursor: zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default' }}
      >
        <svg
          viewBox={viewBoxStr}
          preserveAspectRatio="xMidYMid meet"
          style={{ width: '100%', height: '100%', display: 'block' }}
        >
          {WORLD_MAP_COUNTRIES.map((country, idx) => {
            const sales = countrySalesMap.get(country.id) ?? 0;
            const fillColor = getPinkChoroplethColor(sales, maxSale);
            const isHovered = hoveredCountry?.country.id === country.id;

            return (
              <motion.path
                key={country.id}
                d={country.shape}
                fill={fillColor}
                stroke={isHovered ? '#ffffff' : 'rgba(255, 185, 215, 0.16)'}
                strokeWidth={isHovered ? 2 : 0.6}
                style={{
                  cursor: 'pointer',
                  transition: 'fill 0.25s, stroke 0.2s, stroke-width 0.2s',
                  filter: isHovered ? 'drop-shadow(0 0 10px rgba(255, 175, 215, 0.8))' : undefined,
                }}
                onMouseEnter={(e) => {
                  setHoveredCountry({ country, sales });
                  if (containerRef.current) {
                    const rect = containerRef.current.getBoundingClientRect();
                    setTooltipPos({
                      x: e.clientX - rect.left,
                      y: e.clientY - rect.top,
                    });
                  }
                }}
                onMouseMove={(e) => {
                  if (containerRef.current) {
                    const rect = containerRef.current.getBoundingClientRect();
                    setTooltipPos({
                      x: e.clientX - rect.left,
                      y: e.clientY - rect.top,
                    });
                  }
                }}
                initial={{ opacity: prefersReducedMotion ? 1 : 0 }}
                animate={{ opacity: 1 }}
                transition={{
                  duration: prefersReducedMotion ? 0 : 0.4,
                  delay: prefersReducedMotion ? 0 : Math.min(0.25, idx * 0.0015),
                }}
              />
            );
          })}
        </svg>
      </div>

      {/* Floating Hover Tooltip */}
      {hoveredCountry && tooltipPos && (
        <div
          className="viz-map-tooltip"
          style={{
            left: `${tooltipPos.x}px`,
            top: `${tooltipPos.y}px`,
          }}
        >
          <div style={{ fontWeight: 700, color: '#ffb8d9', fontSize: '12px' }}>
            {hoveredCountry.country.name}
          </div>
          <div style={{ color: '#ffffff', marginTop: '2px', fontWeight: 600 }}>
            {hoveredCountry.sales > 0
              ? `Sales: $${Math.round(hoveredCountry.sales).toLocaleString()}`
              : 'No sales data'}
          </div>
          {hoveredCountry.country.region && (
            <div style={{ color: 'rgba(255, 195, 220, 0.65)', fontSize: '10px', marginTop: '1px' }}>
              Region: {hoveredCountry.country.region}
            </div>
          )}
        </div>
      )}

      {/* Color Scale Legend */}
      <div className="viz-map-legend">
        <span>Low: {formatCompactNumber(minSale)}</span>
        <div className="viz-map-legend-bar" />
        <span>High: {formatCompactNumber(maxSale)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 11. CUSTOMER SEGMENT DISTRIBUTION CHART
// ---------------------------------------------------------------------------

export function CustomerSegmentChart({
  chartType,
  data,
  replayKey,
}: {
  chartType: 'Bar Chart' | 'Pie Chart' | 'Table';
  data: ChartPoint[];
  replayKey?: string | number;
}) {
  const prefersReducedMotion = useChartReducedMotion();
  const validData = Array.isArray(data)
    ? data.filter((d) => d && typeof d.label === 'string' && Number.isFinite(d.value) && d.value >= 0)
    : [];

  const containerRef = useRef<HTMLDivElement>(null);
  useInView(containerRef, { once: true, amount: 0.05 });
  const [hoveredSegment, setHoveredSegment] = useState<string | null>(null);

  if (validData.length === 0) {
    return <div className="viz-empty">No valid customer segment data available.</div>;
  }

  const total = validData.reduce((acc, curr) => acc + curr.value, 0) || 1;

  if (chartType === 'Pie Chart') {
    return (
      <SelfFormingDonutChart
        data={validData}
        ariaLabel="Customer segment distribution pie chart"
        isPie
        replayKey={replayKey}
      />
    );
  }

  if (chartType === 'Table') {
    const tableColumns = [
      { key: 'segment', label: 'Customer Segment', type: 'category' as const },
      { key: 'value', label: 'Value', type: 'number' as const },
      { key: 'share', label: 'Share', type: 'category' as const },
    ];
    const tableRows = validData.map((item) => ({
      segment: item.label,
      value: item.value,
      share: `${Math.round((item.value / total) * 100)}%`,
    }));

    return (
      <SelfFormingTable
        tableData={{ columns: tableColumns, rows: tableRows, totalCount: validData.length }}
        ariaLabel="Customer segment distribution table"
        replayKey={replayKey}
      />
    );
  }

  // Default: Bar Chart
  const max = Math.max(...validData.map((d) => d.value), 1);

  return (
    <div
      key={replayKey}
      ref={containerRef}
      className="viz-bar-chart viz-animated-bars"
      role="img"
      aria-label="Customer segment distribution bar chart"
      onMouseLeave={() => setHoveredSegment(null)}
    >
      {validData.map((item, idx) => {
        const heightPercent = Math.max(10, (item.value / max) * 100);
        const percent = Math.round((item.value / total) * 100);
        const delay = prefersReducedMotion ? 0 : 0.12 + idx * 0.08;
        const color = VIZ_PALETTE[idx % VIZ_PALETTE.length];
        const isHovered = hoveredSegment === item.label;

        return (
          <div
            key={item.label}
            onMouseEnter={() => setHoveredSegment(item.label)}
            style={{ cursor: 'pointer', position: 'relative' }}
            title={`${item.label}: ${formatCompactNumber(item.value)} (${percent}%)`}
          >
            {isHovered && (
              <div
                style={{
                  position: 'absolute',
                  bottom: '100%',
                  left: '50%',
                  transform: 'translateX(-50%) translateY(-8px)',
                  background: 'rgba(11, 19, 36, 0.95)',
                  border: '1px solid rgba(100, 242, 255, 0.4)',
                  boxShadow: '0 8px 24px rgba(0, 0, 0, 0.6), 0 0 12px rgba(100, 242, 255, 0.25)',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  whiteSpace: 'nowrap',
                  zIndex: 30,
                  pointerEvents: 'none',
                  fontSize: '11px',
                  color: '#fff',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontWeight: 600, color: '#64f2ff' }}>{item.label}</div>
                <div>{formatCompactNumber(item.value)} ({percent}%)</div>
              </div>
            )}
            {/* Value Label + Share badge */}
            <motion.div
              initial={{ opacity: prefersReducedMotion ? 1 : 0, y: prefersReducedMotion ? 0 : 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: delay + 0.2, duration: 0.25 }}
              style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}
            >
              <b style={{ color: isHovered ? '#64f2ff' : '#ffffff', fontSize: '11px' }}>
                {formatCompactNumber(item.value)}
              </b>
              <span style={{ fontSize: '9.5px', color: '#64f2ff', fontWeight: 700 }}>
                {percent}%
              </span>
            </motion.div>

            {/* Rising Bar */}
            <div className="viz-bar-track" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'flex-end' }}>
              <motion.span
                className="viz-bar-fill"
                initial={{ height: prefersReducedMotion ? `${heightPercent}%` : '0%' }}
                animate={{ height: `${heightPercent}%` }}
                transition={{
                  delay,
                  duration: prefersReducedMotion ? 0 : 0.65,
                  ease: [0.22, 1, 0.36, 1],
                }}
                style={{
                  width: '100%',
                  height: `${heightPercent}%`,
                  background: isHovered
                    ? `linear-gradient(180deg, #64f2ff, ${color})`
                    : `linear-gradient(180deg, ${color}, #1f4bbd)`,
                  borderRadius: '5px 5px 0 0',
                  boxShadow: isHovered
                    ? `0 0 16px ${color}, 0 -2px 8px rgba(100, 242, 255, 0.5)`
                    : `0 0 10px rgba(66, 148, 255, 0.15)`,
                  transition: 'box-shadow 0.25s, background 0.25s',
                  position: 'relative',
                }}
              >
                <span
                  className="viz-bar-highlight-cap"
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: '2px',
                    background: 'rgba(255, 255, 255, 0.65)',
                    borderRadius: '5px 5px 0 0',
                    boxShadow: '0 0 8px rgba(255, 255, 255, 0.8)',
                  }}
                />
              </motion.span>
            </div>

            {/* Segment Name */}
            <motion.em
              initial={{ opacity: prefersReducedMotion ? 1 : 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: delay + 0.25, duration: 0.25 }}
              style={{
                color: isHovered ? '#ffffff' : 'rgba(220, 231, 246, 0.6)',
                fontWeight: isHovered ? 600 : 400,
                fontSize: '10.5px',
              }}
            >
              {item.label}
            </motion.em>
          </div>
        );
      })}
    </div>
  );
}
