import React from 'react';
import { motion } from 'motion/react';
import type { PipelinePhase } from '../../hooks/useDataPipelineMotion';

interface AnimatedBarChartProps {
  phase: PipelinePhase;
  elapsedMs: number;
  isReducedMotion?: boolean;
}

const BARS_DATA = [
  { label: 'Jan', value: 42, isHighlight: false },
  { label: 'Feb', value: 68, isHighlight: false },
  { label: 'Mar', value: 54, isHighlight: false },
  { label: 'Apr', value: 83, isHighlight: true },  // Peak highlight
  { label: 'May', value: 61, isHighlight: false },
  { label: 'Jun', value: 96, isHighlight: true },  // Highest peak highlight
];

export const AnimatedBarChart: React.FC<AnimatedBarChartProps> = ({
  phase,
  isReducedMotion = false,
}) => {
  const isVisualizing =
    phase === 'bar-chart' ||
    phase === 'bar-to-donut' ||
    phase === 'donut-complete' ||
    isReducedMotion;

  return (
    <div className="bar-chart-container" aria-label="Monthly Performance Chart">
      {/* Bars container */}
      <div className="bar-chart-tracks">
        {BARS_DATA.map((bar, i) => {
          // Height percentage
          const targetHeight = `${bar.value}%`;

          // Color palette: Muted sage #DCE5D4, primary lime #B8F641 for peaks, or dark accent
          let barBg = '#DCE5D4';
          if (bar.isHighlight) {
            barBg = i === 5 ? '#B8F641' : '#A8EB2C';
          }

          return (
            <div key={bar.label} className="bar-col-item">
              {/* Value pill tooltip on active/hover */}
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{
                  opacity: isVisualizing ? 1 : 0,
                  y: isVisualizing ? 0 : 4,
                }}
                transition={{ duration: 0.3, delay: isReducedMotion ? 0 : 0.4 + i * 0.08 }}
                className="bar-value-tooltip"
              >
                {bar.value}%
              </motion.div>

              {/* Animated Bar element */}
              <motion.div
                initial={{ height: 0, scaleY: 0 }}
                animate={{
                  height: isVisualizing ? targetHeight : '0%',
                  scaleY: isVisualizing ? 1 : 0,
                }}
                transition={{
                  duration: isReducedMotion ? 0 : 0.7,
                  delay: isReducedMotion ? 0 : 0.15 + i * 0.09,
                  ease: [0.34, 1.3, 0.64, 1], // subtle spring bounce
                }}
                style={{
                  backgroundColor: barBg,
                  transformOrigin: 'bottom',
                }}
                className="bar-animated-bar"
              />
            </div>
          );
        })}
      </div>

      {/* Axis Labels */}
      <div className="bar-axis-row">
        {BARS_DATA.map((bar) => (
          <span key={bar.label} style={{ flex: 1, textAlign: 'center', fontFamily: 'monospace', fontSize: '0.625rem' }}>
            {bar.label}
          </span>
        ))}
      </div>
    </div>
  );
};
