import React from 'react';
import { motion } from 'motion/react';
import { ArrowDown } from 'lucide-react';

interface DataFlowTransitionProps {
  fromStage: 1 | 2;
  toStage: 2 | 3;
  isActive: boolean;
  label?: string;
  isReducedMotion?: boolean;
}

export const DataFlowTransition: React.FC<DataFlowTransitionProps> = ({
  fromStage,
  toStage,
  isActive,
  label,
  isReducedMotion = false,
}) => {
  return (
    <div className="pipeline-connector">
      {/* Central Connector Line */}
      <div className="pipeline-connector-pill">
        {/* Animated pulse dot */}
        <motion.div
          animate={{
            scale: isActive && !isReducedMotion ? [1, 1.4, 1] : 1,
            backgroundColor: isActive ? '#B8F641' : '#DCE5D4',
          }}
          transition={{ duration: 1, repeat: Infinity }}
          className="connector-pulse-dot"
        />

        <span className="connector-label">
          {label ?? `Stage ${fromStage} → Stage ${toStage}`}
        </span>

        {/* Arrow indicator */}
        <motion.div
          animate={{
            y: isActive && !isReducedMotion ? [0, 2, 0] : 0,
            color: isActive ? '#151915' : '#737D6E',
          }}
          transition={{ duration: 0.8, repeat: Infinity }}
          style={{ display: 'flex', alignItems: 'center' }}
        >
          <ArrowDown style={{ width: 11, height: 11 }} />
        </motion.div>
      </div>
    </div>
  );
};
