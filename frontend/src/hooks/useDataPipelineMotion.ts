import { useEffect, useState, useRef, useCallback } from 'react';

export const PIPELINE_MOTION = {
  durationMs: 7000,
  playbackRate: 1,
  loop: true,
} as const;

export const PIPELINE_DURATION_MS = PIPELINE_MOTION.durationMs;

export type PipelinePhase =
  | 'raw'
  | 'raw-to-clean'
  | 'cleaning'
  | 'clean-to-chart'
  | 'bar-chart'
  | 'bar-to-donut'
  | 'donut-complete'
  | 'loop-reset';

export interface DataPipelineMotionState {
  phase: PipelinePhase;
  progress: number; // 0 to 1
  elapsedMs: number;
  activeStage: 1 | 2 | 3;
  statusText: string;
  stageName: string;
  stageTag: string;
  stageTitle: string;
  statusBadge: string;
  footerLeft: string;
  footerRight: string;
  isReducedMotion: boolean;
  isVerifiedRunning: boolean;
  systemReduced: boolean;
  toggleMotion: () => void;
  setStageOverride?: (stage: 1 | 2 | 3 | null) => void;
  subscribeToFrames: (callback: (elapsedMs: number) => void) => () => void;
  getElapsedMs: () => number;
}

export const PIPELINE_TIMING = {
  raw: [0, 1500] as const,
  rawToClean: [1500, 2250] as const,
  cleaning: [2250, 3350] as const,
  cleanToChart: [3350, 4000] as const,
  barChart: [4000, 4950] as const,
  barToDonut: [4950, 5950] as const,
  donutComplete: [5950, 6550] as const,
  loopReset: [6550, 7000] as const,
};

function getPhaseForElapsed(elapsedMs: number): PipelinePhase {
  if (elapsedMs < PIPELINE_TIMING.raw[1]) return 'raw';
  if (elapsedMs < PIPELINE_TIMING.rawToClean[1]) return 'raw-to-clean';
  if (elapsedMs < PIPELINE_TIMING.cleaning[1]) return 'cleaning';
  if (elapsedMs < PIPELINE_TIMING.cleanToChart[1]) return 'clean-to-chart';
  if (elapsedMs < PIPELINE_TIMING.barChart[1]) return 'bar-chart';
  if (elapsedMs < PIPELINE_TIMING.barToDonut[1]) return 'bar-to-donut';
  if (elapsedMs < PIPELINE_TIMING.donutComplete[1]) return 'donut-complete';
  return 'loop-reset';
}

function getPhaseMetadata(phase: PipelinePhase): {
  activeStage: 1 | 2 | 3;
  statusText: string;
  stageName: string;
  stageTag: string;
  stageTitle: string;
  statusBadge: string;
  footerLeft: string;
  footerRight: string;
} {
  switch (phase) {
    case 'raw':
      return {
        activeStage: 1,
        statusText: 'Ingesting disorganized records...',
        stageName: '01 Raw Data',
        stageTag: 'Stage 01',
        stageTitle: 'Unstructured Raw Inflow',
        statusBadge: 'Turbulent Ingestion',
        footerLeft: '8 scattered records · anomalies detected',
        footerRight: 'JSON · CSV · SQL',
      };
    case 'raw-to-clean':
      return {
        activeStage: 1,
        statusText: 'Filtering anomalies & aligning schema...',
        stageName: '01 → 02 Transition',
        stageTag: 'Stage 01 → 02',
        stageTitle: 'Schema Normalization',
        statusBadge: 'Filtering Anomalies',
        footerLeft: 'Anomalies routed to cleaning pipeline',
        footerRight: 'Type Coercion',
      };
    case 'cleaning':
      return {
        activeStage: 2,
        statusText: 'Types coerced · 4/4 schemas verified',
        stageName: '02 Clean Data',
        stageTag: 'Stage 02',
        stageTitle: 'Structured & Verified Schema',
        statusBadge: 'Data Validated',
        footerLeft: '4/4 schemas verified · 0 nulls · types coerced',
        footerRight: '100% Quality Score',
      };
    case 'clean-to-chart':
      return {
        activeStage: 2,
        statusText: 'Synthesizing verified dataset into analytics...',
        stageName: '02 → 03 Transition',
        stageTag: 'Stage 02 → 03',
        stageTitle: 'Synthesis into Intelligence',
        statusBadge: 'Synthesizing...',
        footerLeft: 'Generating analytical models & charts',
        footerRight: 'Zero Hallucination',
      };
    case 'bar-chart':
      return {
        activeStage: 3,
        statusText: 'Bars growing: Forecast +28.4% YoY',
        stageName: '03 Bar Chart',
        stageTag: 'Stage 03',
        stageTitle: 'Forecast Trajectory',
        statusBadge: '+28.4% YoY',
        footerLeft: 'Linear trajectory · Continuous transformation',
        footerRight: '96.2% Confidence',
      };
    case 'bar-to-donut':
      return {
        activeStage: 3,
        statusText: 'Radial transformation: Bars → Donut',
        stageName: '03 Continuous Morph',
        stageTag: 'Stage 03',
        stageTitle: 'Continuous Shape Morph',
        statusBadge: 'Bars → Donut',
        footerLeft: 'Radial geometric transformation',
        footerRight: 'Analytical Synthesis',
      };
    case 'donut-complete':
      return {
        activeStage: 3,
        statusText: 'Precision verified: 99.8% valid',
        stageName: '03 Donut Complete',
        stageTag: 'Stage 03',
        stageTitle: 'Synthesized Distribution',
        statusBadge: 'Donut Settled',
        footerLeft: 'Clean Precision · Zero schema drift',
        footerRight: '99.8% Valid',
      };
    case 'loop-reset':
    default:
      return {
        activeStage: 3,
        statusText: 'Loop complete · Seamlessly resetting',
        stageName: '03 → 01 Reset',
        stageTag: 'Cycle Reset',
        stageTitle: 'Pipeline Refresh',
        statusBadge: 'Resetting...',
        footerLeft: 'Seamless transition to next cycle',
        footerRight: 'Live Pipeline',
      };
  }
}

// Storage can be unavailable in privacy-restricted embeds. Motion still works.
function readMotionPreference(): boolean {
  try { return window.localStorage.getItem('ai_analyst_motion_mode') === 'reduced'; }
  catch { return false; }
}

export function useDataPipelineMotion(): DataPipelineMotionState {
  const [userPaused, setUserPaused] = useState(readMotionPreference);
  const [systemReduced, setSystemReduced] = useState(() =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const isReducedMotion = userPaused || systemReduced;
  const [isVerifiedRunning, setIsVerifiedRunning] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<PipelinePhase>(isReducedMotion ? 'donut-complete' : 'raw');
  const [sampledMs, setSampledMs] = useState(isReducedMotion ? 6200 : 0);
  const elapsedMsRef = useRef(isReducedMotion ? 6200 : 0);
  const subscribersRef = useRef(new Set<(elapsedMs: number) => void>());

  const subscribeToFrames = useCallback((callback: (elapsedMs: number) => void) => {
    subscribersRef.current.add(callback);
    callback(elapsedMsRef.current);
    return () => { subscribersRef.current.delete(callback); };
  }, []);
  const getElapsedMs = useCallback(() => elapsedMsRef.current, []);
  const toggleMotion = useCallback(() => {
    if (systemReduced) return;
    const next = !userPaused;
    try { window.localStorage.setItem('ai_analyst_motion_mode', next ? 'reduced' : 'live'); } catch { /* Session-only preference. */ }
    setUserPaused(next);
  }, [userPaused, systemReduced]);

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onMedia = () => setSystemReduced(media.matches);
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'ai_analyst_motion_mode' || event.key === null) setUserPaused(readMotionPreference());
    };
    media.addEventListener('change', onMedia);
    window.addEventListener('storage', onStorage);
    return () => {
      media.removeEventListener('change', onMedia);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useEffect(() => {
    let request: number | null = null;
    let lastTimestamp: number | null = null;
    let frames = 0;
    let disposed = false;
    let lastPhase: PipelinePhase = isReducedMotion ? 'donut-complete' : 'raw';
    elapsedMsRef.current = isReducedMotion ? 6200 : 0;
    // Synchronize the React captions once when the imperative playback mode changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrentPhase(lastPhase);
    setSampledMs(elapsedMsRef.current);
    setIsVerifiedRunning(false);
    const publish = () => subscribersRef.current.forEach(callback => callback(elapsedMsRef.current));
    publish();
    if (isReducedMotion) return;

    const animate = (timestamp: number) => {
      request = null;
      if (disposed || document.hidden) return;
      // One active-time clock. Modulo has no terminal state or repeat counter.
      // Do not clamp long frames: elapsed active time must remain at 1x.
      const delta = lastTimestamp === null ? 0 : Math.max(0, timestamp - lastTimestamp);
      lastTimestamp = timestamp;
      elapsedMsRef.current = (elapsedMsRef.current + delta) % PIPELINE_DURATION_MS;
      publish();
      if (delta > 0 && ++frames === 3) setIsVerifiedRunning(true);
      const phase = getPhaseForElapsed(elapsedMsRef.current);
      if (phase !== lastPhase) {
        lastPhase = phase;
        setCurrentPhase(phase);
        setSampledMs(elapsedMsRef.current);
      }
      request = requestAnimationFrame(animate);
    };
    const onVisibility = () => {
      if (request !== null) cancelAnimationFrame(request);
      request = null;
      lastTimestamp = null;
      frames = 0;
      setIsVerifiedRunning(false);
      if (!document.hidden) request = requestAnimationFrame(animate);
    };
    document.addEventListener('visibilitychange', onVisibility);
    onVisibility();
    return () => {
      disposed = true;
      if (request !== null) cancelAnimationFrame(request);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [isReducedMotion]);

  const metadata = getPhaseMetadata(isReducedMotion ? 'donut-complete' : currentPhase);
  return {
    ...metadata,
    phase: isReducedMotion ? 'donut-complete' : currentPhase,
    progress: isReducedMotion ? 1 : sampledMs / PIPELINE_DURATION_MS,
    elapsedMs: sampledMs,
    isReducedMotion,
    isVerifiedRunning,
    systemReduced,
    toggleMotion,
    subscribeToFrames,
    getElapsedMs,
  };
}
