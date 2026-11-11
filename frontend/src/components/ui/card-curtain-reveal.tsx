/**
 * CardCurtainReveal — Center-origin curtain reveal compound component.
 *
 * Animation reference:
 *   CLOSED  → clipPath: polygon(50% 0, 50% 0, 50% 100%, 50% 100%)
 *   OPEN    → clipPath: polygon(0 0, 100% 0, 100% 100%, 0 100%)
 *
 * The curtain layer expands horizontally from the center, revealing the
 * alternate card state beneath — producing a "physical curtain opening"
 * interaction identical to the supplied reference video.
 */

import {
  createContext,
  useContext,
  useState,
  useRef,
  useCallback,
  type ReactNode,
  type CSSProperties,
} from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { cn } from '../../lib/utils';

// ---------------------------------------------------------------------------
// Context — shared hover state for compound component
// ---------------------------------------------------------------------------

interface CurtainContextValue {
  isOpen: boolean;
  shouldReduceMotion: boolean;
}

const CurtainContext = createContext<CurtainContextValue>({
  isOpen: false,
  shouldReduceMotion: false,
});

function useCurtain() {
  return useContext(CurtainContext);
}

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const curtainVariants = {
  hidden: {
    clipPath: 'polygon(50% 0%, 50% 0%, 50% 100%, 50% 100%)',
  },
  visible: {
    clipPath: 'polygon(0% 0%, 100% 0%, 100% 100%, 0% 100%)',
  },
} as const;

// ---------------------------------------------------------------------------
// CardCurtainReveal — root wrapper
// ---------------------------------------------------------------------------

interface CardCurtainRevealProps {
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
  /** Accessible label for the card */
  'aria-label'?: string;
}

export function CardCurtainReveal({
  className,
  style,
  children,
  'aria-label': ariaLabel,
}: CardCurtainRevealProps) {
  const [isOpen, setIsOpen] = useState(false);
  const shouldReduceMotion = useReducedMotion() ?? false;

  // Support keyboard focus as an interaction trigger
  const handleFocus = useCallback(() => setIsOpen(true), []);
  const handleBlur = useCallback(() => setIsOpen(false), []);
  const handleMouseEnter = useCallback(() => setIsOpen(true), []);
  const handleMouseLeave = useCallback(() => setIsOpen(false), []);

  // Touch: tap toggles the card (fallback for touch devices)
  const touchRef = useRef(false);
  const handleTouchStart = useCallback(() => {
    touchRef.current = true;
  }, []);
  const handleClick = useCallback(() => {
    if (touchRef.current) {
      setIsOpen((v) => !v);
      touchRef.current = false;
    }
  }, []);

  return (
    <CurtainContext.Provider value={{ isOpen, shouldReduceMotion }}>
      <article
        className={cn('feat-card', className)}
        style={style}
        tabIndex={0}
        aria-label={ariaLabel}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onTouchStart={handleTouchStart}
        onClick={handleClick}
      >
        {children}
      </article>
    </CurtainContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// CardCurtain — the animated overlay that reveals from center
// ---------------------------------------------------------------------------

interface CardCurtainProps {
  className?: string;
  children?: ReactNode;
}

export function CardCurtain({ className, children }: CardCurtainProps) {
  const { isOpen, shouldReduceMotion } = useCurtain();

  return (
    <motion.div
      className={cn('feat-curtain', className)}
      aria-hidden="true"
      initial="hidden"
      animate={isOpen ? 'visible' : 'hidden'}
      variants={
        shouldReduceMotion ? { hidden: { opacity: 0 }, visible: { opacity: 1 } } : curtainVariants
      }
      transition={
        shouldReduceMotion
          ? { duration: 0.15 }
          : {
              duration: 0.45,
              ease: [0.76, 0, 0.24, 1],
            }
      }
    >
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// CardCurtainRevealBody — static content wrapper (always visible)
// ---------------------------------------------------------------------------

interface CardCurtainRevealBodyProps {
  className?: string;
  children: ReactNode;
}

export function CardCurtainRevealBody({ className, children }: CardCurtainRevealBodyProps) {
  return <div className={cn('feat-body', className)}>{children}</div>;
}

// ---------------------------------------------------------------------------
// CardCurtainRevealTitle — animated title (moves up on reveal)
// ---------------------------------------------------------------------------

interface CardCurtainRevealTitleProps {
  className?: string;
  children: ReactNode;
  /** Whether this title lives inside the curtain (revealed) or outside (resting) */
  inCurtain?: boolean;
}

export function CardCurtainRevealTitle({
  className,
  children,
  inCurtain = false,
}: CardCurtainRevealTitleProps) {
  const { isOpen, shouldReduceMotion } = useCurtain();

  if (!inCurtain) {
    // Resting title — always present, fades out when curtain opens
    return (
      <motion.h3
        className={cn('feat-title feat-title--resting', className)}
        animate={shouldReduceMotion ? {} : { opacity: isOpen ? 0 : 1, y: isOpen ? -8 : 0 }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
      >
        {children}
      </motion.h3>
    );
  }

  // Revealed title — animates upward into position when curtain opens
  return (
    <motion.h3
      className={cn('feat-title feat-title--revealed', className)}
      initial={{ y: 170 }}
      animate={shouldReduceMotion ? {} : { y: isOpen ? 0 : 170 }}
      transition={{
        duration: 0.45,
        ease: [0.76, 0, 0.24, 1],
      }}
    >
      {children}
    </motion.h3>
  );
}

// ---------------------------------------------------------------------------
// CardCurtainRevealDescription — description visible in revealed state
// ---------------------------------------------------------------------------

interface CardCurtainRevealDescriptionProps {
  className?: string;
  children: ReactNode;
}

export function CardCurtainRevealDescription({
  className,
  children,
}: CardCurtainRevealDescriptionProps) {
  const { isOpen, shouldReduceMotion } = useCurtain();

  return (
    <motion.p
      className={cn('feat-desc', className)}
      animate={
        shouldReduceMotion
          ? {}
          : {
              opacity: isOpen ? 1 : 0,
              y: isOpen ? 0 : 12,
            }
      }
      transition={{
        duration: 0.3,
        delay: isOpen ? 0.18 : 0,
        ease: 'easeOut',
      }}
    >
      {children}
    </motion.p>
  );
}

// ---------------------------------------------------------------------------
// CardCurtainRevealFooter — footer row with action button
// ---------------------------------------------------------------------------

interface CardCurtainRevealFooterProps {
  className?: string;
  children: ReactNode;
}

export function CardCurtainRevealFooter({ className, children }: CardCurtainRevealFooterProps) {
  const { isOpen, shouldReduceMotion } = useCurtain();

  return (
    <motion.div
      className={cn('feat-footer', className)}
      animate={
        shouldReduceMotion
          ? {}
          : {
              opacity: isOpen ? 1 : 0,
              y: isOpen ? 0 : 10,
            }
      }
      transition={{
        duration: 0.3,
        delay: isOpen ? 0.22 : 0,
        ease: 'easeOut',
      }}
    >
      {children}
    </motion.div>
  );
}
