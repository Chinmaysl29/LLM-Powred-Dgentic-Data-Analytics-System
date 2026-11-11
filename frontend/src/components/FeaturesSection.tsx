/**
 * FeaturesSection — Four curtain-reveal feature cards.
 *
 * Palette (from design reference):
 *   CHARCOAL  #4D4D4D
 *   TAUPE     #A89D92
 *   IVORY     #F8F4EE
 *   WHITE     #FFFFFF
 *
 * Each card has:
 *   - A resting state (base background, title visible)
 *   - A revealed state (curtain expands from center, alternate content shown)
 *
 * Section enters viewport with a subtle fade-up via IntersectionObserver.
 */

import { useEffect, useRef, useState } from 'react';
import {
  CardCurtainReveal,
  CardCurtain,
  CardCurtainRevealBody,
  CardCurtainRevealTitle,
  CardCurtainRevealDescription,
  CardCurtainRevealFooter,
} from './ui/card-curtain-reveal';

// ---------------------------------------------------------------------------
// Feature data
// ---------------------------------------------------------------------------

interface FeatureCard {
  id: string;
  title: string;
  headline: string;
  description: string;
  /** Resting card background */
  bg: string;
  /** Text colour on the resting card */
  textColor: string;
  /** Curtain (revealed) background */
  curtainBg: string;
  /** Text colour on the curtain */
  curtainTextColor: string;
  /** Subtle border colour */
  borderColor: string;
}

const FEATURE_CARDS: FeatureCard[] = [
  {
    id: 'natural-language',
    title: 'Natural Language\nData Analysis',
    headline: 'Ask questions. Get answers.',
    description:
      'Interact with your data using plain natural language instead of writing complex SQL or manually performing analysis. The AI understands your business question and takes it through the appropriate analytics workflow.',
    bg: '#4D4D4D',
    textColor: '#F5F5F5',
    curtainBg: '#F8F4EE',
    curtainTextColor: '#1a1a1a',
    borderColor: 'rgba(255,255,255,0.10)',
  },
  {
    id: 'visualizations',
    title: 'Intelligent\nVisualizations',
    headline: 'Turn complex data into clear visuals.',
    description:
      'Automatically generates relevant interactive charts and visualizations based on the data and the question being asked — helping users quickly understand trends, patterns, relationships, and anomalies.',
    bg: '#A89D92',
    textColor: '#1a1a1a',
    curtainBg: '#4D4D4D',
    curtainTextColor: '#F5F5F5',
    borderColor: 'rgba(0,0,0,0.08)',
  },
  {
    id: 'decision-intelligence',
    title: 'Decision\nIntelligence',
    headline: 'Go beyond insights. Get actionable decisions.',
    description:
      "The system doesn't stop at showing what happened. It identifies important patterns, potential risks and opportunities, and provides data-driven recommendations to support better business decisions.",
    bg: '#F8F4EE',
    textColor: '#1a1a1a',
    curtainBg: '#4D4D4D',
    curtainTextColor: '#F5F5F5',
    borderColor: 'rgba(0,0,0,0.08)',
  },
  {
    id: 'autonomous-analytics',
    title: 'Autonomous\nAI Analytics',
    headline: 'From raw data to business insights.',
    description:
      'Multiple specialized AI agents work together across data preparation, analysis, visualization, and reporting. The system follows a structured analytics workflow instead of relying on a single AI response.',
    bg: '#FFFFFF',
    textColor: '#1a1a1a',
    curtainBg: '#A89D92',
    curtainTextColor: '#1a1a1a',
    borderColor: 'rgba(0,0,0,0.08)',
  },
];

// ---------------------------------------------------------------------------
// Arrow icon — inline SVG, no external dep required
// ---------------------------------------------------------------------------

function ArrowUpRight({ color }: { color: string }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M2.5 11.5L11.5 2.5M11.5 2.5H5M11.5 2.5V9"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// FeaturesSection
// ---------------------------------------------------------------------------

export default function FeaturesSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const [inView, setInView] = useState(false);

  // Section entrance animation via IntersectionObserver
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;

    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          obs.disconnect();
        }
      },
      { threshold: 0.08 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <section
      id="features"
      ref={sectionRef}
      className={`features-section${inView ? ' features-section--visible' : ''}`}
      aria-labelledby="features-heading"
    >
      {/* Section header */}
      <div className="features-header">
        <p className="features-eyebrow">Features</p>
        <h2 id="features-heading" className="features-heading">
          Built for intelligent analytics
        </h2>
      </div>

      {/* Card grid */}
      <div className="features-grid" role="list">
        {FEATURE_CARDS.map((card, i) => (
          <CardCurtainReveal
            key={card.id}
            aria-label={card.title.replace('\n', ' ')}
            style={
              {
                '--feat-bg': card.bg,
                '--feat-text': card.textColor,
                '--feat-curtain-bg': card.curtainBg,
                '--feat-curtain-text': card.curtainTextColor,
                '--feat-border': card.borderColor,
                '--feat-delay': `${i * 60}ms`,
              } as React.CSSProperties
            }
          >
            {/* ---------- Resting state content ---------- */}
            <CardCurtainRevealBody>
              {/* Resting title */}
              <CardCurtainRevealTitle inCurtain={false}>
                {card.title.split('\n').map((line, li) => (
                  <span key={li} className="feat-title-line">
                    {line}
                  </span>
                ))}
              </CardCurtainRevealTitle>

              {/* Resting headline — small muted text */}
              <p className="feat-headline">{card.headline}</p>
            </CardCurtainRevealBody>

            {/* ---------- Curtain (revealed) layer ---------- */}
            <CardCurtain>
              {/* Revealed title */}
              <CardCurtainRevealTitle inCurtain>
                {card.title.split('\n').map((line, li) => (
                  <span key={li} className="feat-title-line">
                    {line}
                  </span>
                ))}
              </CardCurtainRevealTitle>

              {/* Description */}
              <CardCurtainRevealDescription>{card.description}</CardCurtainRevealDescription>

              {/* Footer */}
              <CardCurtainRevealFooter>
                <span className="feat-footer-label">Learn more</span>
                <button
                  className="feat-btn"
                  aria-label={`Learn more about ${card.title.replace('\n', ' ')}`}
                  tabIndex={-1}
                >
                  <ArrowUpRight color={card.curtainTextColor} />
                </button>
              </CardCurtainRevealFooter>
            </CardCurtain>
          </CardCurtainReveal>
        ))}
      </div>
    </section>
  );
}
