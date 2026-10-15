import React from 'react';
import type { PipelinePhase } from '../../hooks/useDataPipelineMotion';
import { AnimatedChartMorph } from './AnimatedChartMorph';

interface VisualizationStageProps {
  phase: PipelinePhase;
  elapsedMs: number;
  isActive: boolean;
  isReducedMotion?: boolean;
  subscribeToFrames?: (cb: (elapsedMs: number) => void) => () => void;
}

export const VisualizationStage: React.FC<VisualizationStageProps> = ({
  phase,
  elapsedMs,
  isReducedMotion = false,
  subscribeToFrames,
}) => {
  return (
    <AnimatedChartMorph
      phase={phase}
      elapsedMs={elapsedMs}
      isReducedMotion={isReducedMotion}
      subscribeToFrames={subscribeToFrames}
    />
  );
};
