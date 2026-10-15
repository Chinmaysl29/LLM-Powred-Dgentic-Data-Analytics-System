import React from 'react';
import { motion } from 'motion/react';
import type { PipelinePhase } from '../../hooks/useDataPipelineMotion';

interface AnimatedDonutChartProps {
  phase: PipelinePhase;
  elapsedMs: number;
  isReducedMotion?: boolean;
}

export const AnimatedDonutChart: React.FC<AnimatedDonutChartProps> = ({
  phase,
  isReducedMotion = false,
}) => {
  const isVisualizing =
    phase === 'bar-to-donut' ||
    phase === 'donut-complete' ||
    isReducedMotion;

  // Circle geometry
  const size = 96;
  const strokeWidth = 11;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius; // approx 267.03

  // Segments distribution: 70%, 20%, 10%
  const seg1Len = circumference * 0.70;
  const seg2Len = circumference * 0.20;
  const seg3Len = circumference * 0.10;

  // Offsets around the circle starting from top (-90deg)
  const seg1Offset = 0;
  const seg2Offset = -seg1Len;
  const seg3Offset = -(seg1Len + seg2Len);

  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', width: 96, height: 96 }} aria-label="Data Distribution Donut Chart">
      <motion.svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ transform: 'rotate(-90deg)' }}
        initial={{ rotate: isReducedMotion ? -90 : -130, opacity: 0 }}
        animate={{
          rotate: isVisualizing ? -90 : -130,
          opacity: isVisualizing ? 1 : 0.2,
        }}
        transition={{ duration: isReducedMotion ? 0 : 0.8, ease: 'easeOut' }}
      >
        {/* Background track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#F5F9ED"
          strokeWidth={strokeWidth}
        />

        {/* Segment 1: 70% (Primary Lime #B8F641) */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#B8F641"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${seg1Len} ${circumference}`}
          initial={{ strokeDashoffset: seg1Len }}
          animate={{ strokeDashoffset: isVisualizing ? seg1Offset : seg1Len }}
          transition={{
            duration: isReducedMotion ? 0 : 0.9,
            delay: isReducedMotion ? 0 : 0.2,
            ease: [0.16, 1, 0.3, 1],
          }}
        />

        {/* Segment 2: 20% (Primary Dark #151915) */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#151915"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${seg2Len} ${circumference}`}
          initial={{ strokeDashoffset: seg2Len }}
          animate={{ strokeDashoffset: isVisualizing ? seg2Offset : seg2Len }}
          transition={{
            duration: isReducedMotion ? 0 : 0.8,
            delay: isReducedMotion ? 0 : 0.45,
            ease: [0.16, 1, 0.3, 1],
          }}
        />

        {/* Segment 3: 10% (Muted Sage #DCE5D4) */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#DCE5D4"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${seg3Len} ${circumference}`}
          initial={{ strokeDashoffset: seg3Len }}
          animate={{ strokeDashoffset: isVisualizing ? seg3Offset : seg3Len }}
          transition={{
            duration: isReducedMotion ? 0 : 0.7,
            delay: isReducedMotion ? 0 : 0.65,
            ease: [0.16, 1, 0.3, 1],
          }}
        />
      </motion.svg>

      {/* Center Label */}
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{
          opacity: isVisualizing ? 1 : 0,
          scale: isVisualizing ? 1 : 0.8,
        }}
        transition={{ duration: 0.4, delay: isReducedMotion ? 0 : 0.6 }}
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none',
        }}
      >
        <span style={{ fontSize: '0.8125rem', fontWeight: 800, color: '#151915', lineHeight: 1.1 }}>99.8%</span>
        <span style={{ fontSize: '0.5625rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#737D6E', fontWeight: 600 }}>Valid</span>
      </motion.div>
    </div>
  );
};
