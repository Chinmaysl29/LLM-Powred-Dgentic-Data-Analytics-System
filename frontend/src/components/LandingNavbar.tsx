import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NavItem {
  id: string;
  label: string;
  href: string;
  isHash?: boolean;
}

// ---------------------------------------------------------------------------
// Center nav items (Features / Work)
// ---------------------------------------------------------------------------

const CENTER_ITEMS: NavItem[] = [
  { id: 'features', label: 'Features', href: '#hero', isHash: true },
  { id: 'work', label: 'Work', href: '/datasets' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function LandingNavbar() {
  const location = useLocation();
  const navigate = useNavigate();

  // Refs for measuring nav items
  const navRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Map<string, HTMLButtonElement | HTMLAnchorElement>>(new Map());

  // Indicator position state
  const [indicator, setIndicator] = useState<{
    left: number;
    width: number;
    opacity: number;
  }>({ left: 0, width: 0, opacity: 0 });

  const [hovered, setHovered] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Track scroll for enhanced shadow
  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Entrance animation trigger
  useEffect(() => {
    const id = setTimeout(() => setMounted(true), 10);
    return () => clearTimeout(id);
  }, []);

  // Compute indicator position based on hovered item.
  // We keep the indicator vertically centered via the combined transform string
  // to avoid the CSS translateY(-50%) being overwritten by the inline style.
  const updateIndicator = useCallback((itemId: string | null) => {
    if (!itemId || !navRef.current) {
      setIndicator((prev) => ({ ...prev, opacity: 0 }));
      return;
    }
    const el = itemRefs.current.get(itemId);
    const navCenter = navRef.current;
    if (!el || !navCenter) return;

    // Measure relative to the center container, not the whole nav pill
    const centerEl = navCenter.querySelector<HTMLDivElement>('.landing-nav-center');
    if (!centerEl) return;

    const containerRect = centerEl.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const left = elRect.left - containerRect.left;
    const width = elRect.width;

    setIndicator({ left, width, opacity: 1 });
  }, []);

  useLayoutEffect(() => {
    updateIndicator(hovered);
  }, [hovered, updateIndicator]);

  // Close mobile on outside click
  useEffect(() => {
    if (!mobileOpen) return;
    const handleClick = (e: MouseEvent) => {
      const drawer = document.getElementById('landing-mobile-drawer');
      const toggle = document.getElementById('landing-mobile-toggle');
      if (
        drawer &&
        !drawer.contains(e.target as Node) &&
        toggle &&
        !toggle.contains(e.target as Node)
      ) {
        setMobileOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [mobileOpen]);

  // Keyboard: Escape closes mobile menu
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileOpen) setMobileOpen(false);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [mobileOpen]);

  const handleHashLink = (href: string) => {
    if (location.pathname !== '/') {
      navigate('/');
      setTimeout(() => {
        const el = document.querySelector(href);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      }, 120);
    } else {
      const el = document.querySelector(href);
      if (el) el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const reducedMotion = prefersReducedMotion();

  return (
    <>
      {/* ----------------------------------------------------------------- */}
      {/* Desktop / Tablet pill navbar                                        */}
      {/* ----------------------------------------------------------------- */}
      <header
        className={`landing-nav-wrapper${mounted ? ' landing-nav-wrapper--visible' : ''}`}
        aria-label="Site navigation"
      >
        <nav
          className={`landing-nav${scrolled ? ' landing-nav--scrolled' : ''}`}
          ref={navRef}
          aria-label="Main navigation"
        >
          {/* ----- Brand ----- */}
          <Link to="/" className="landing-nav-brand" aria-label="AI Data Analyst – home">
            <span className="landing-nav-brand-dot" aria-hidden="true" />
            <span className="landing-nav-brand-text">AI Data Analyst</span>
          </Link>

          {/* ----- Center links ----- */}
          <div className="landing-nav-center" role="list">
            {/* Sliding indicator */}
            <div
              className="landing-nav-indicator"
              aria-hidden="true"
              style={{
                /* Include translateY(-50%) to preserve vertical centering */
                transform: `translateX(${indicator.left}px) translateY(-50%)`,
                width: `${indicator.width}px`,
                opacity: indicator.opacity,
                transition: reducedMotion
                  ? 'none'
                  : 'transform 220ms cubic-bezier(0.34,1.15,0.64,1), width 220ms cubic-bezier(0.34,1.15,0.64,1), opacity 150ms ease',
              }}
            />

            {CENTER_ITEMS.map((item) => {
              if (item.isHash) {
                return (
                  <button
                    key={item.id}
                    role="listitem"
                    ref={(el) => {
                      if (el) itemRefs.current.set(item.id, el);
                    }}
                    className="landing-nav-link landing-nav-link--btn"
                    onMouseEnter={() => setHovered(item.id)}
                    onMouseLeave={() => setHovered(null)}
                    onFocus={() => setHovered(item.id)}
                    onBlur={() => setHovered(null)}
                    onClick={() => handleHashLink(item.href)}
                    aria-label={item.label}
                  >
                    {item.label}
                  </button>
                );
              }
              return (
                <Link
                  key={item.id}
                  to={item.href}
                  role="listitem"
                  ref={(el) => {
                    if (el) itemRefs.current.set(item.id, el);
                  }}
                  className="landing-nav-link"
                  onMouseEnter={() => setHovered(item.id)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(item.id)}
                  onBlur={() => setHovered(null)}
                  aria-label={item.label}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>

          {/* ----- Right actions ----- */}
          <div className="landing-nav-actions">
            <Link to="/login" className="landing-nav-login">
              Login
            </Link>
            <Link to="/signup" className="landing-nav-signup">
              Sign Up
            </Link>
          </div>

          {/* ----- Mobile hamburger ----- */}
          <button
            id="landing-mobile-toggle"
            className="landing-nav-hamburger"
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileOpen}
            aria-controls="landing-mobile-drawer"
            onClick={() => setMobileOpen((v) => !v)}
          >
            <span
              className={`landing-hamburger-icon${mobileOpen ? ' landing-hamburger-icon--open' : ''}`}
              aria-hidden="true"
            >
              <span />
              <span />
              <span />
            </span>
          </button>
        </nav>
      </header>

      {/* ----------------------------------------------------------------- */}
      {/* Mobile drawer overlay                                               */}
      {/* ----------------------------------------------------------------- */}
      {mobileOpen && (
        <div
          className="landing-mobile-overlay"
          aria-hidden="true"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <div
        id="landing-mobile-drawer"
        className={`landing-mobile-drawer${mobileOpen ? ' landing-mobile-drawer--open' : ''}`}
        role="dialog"
        aria-label="Mobile navigation"
        aria-modal="true"
      >
        <nav aria-label="Mobile main navigation">
          <ul className="landing-mobile-nav" role="list">
            {CENTER_ITEMS.map((item) => (
              <li key={item.id} role="listitem">
                {item.isHash ? (
                  <button
                    className="landing-mobile-link"
                    onClick={() => {
                      setMobileOpen(false);
                      handleHashLink(item.href);
                    }}
                  >
                    {item.label}
                  </button>
                ) : (
                  <Link
                    to={item.href}
                    className="landing-mobile-link"
                    onClick={() => setMobileOpen(false)}
                  >
                    {item.label}
                  </Link>
                )}
              </li>
            ))}
            <li role="separator" className="landing-mobile-divider" />
            <li role="listitem">
              <Link
                to="/login"
                className="landing-mobile-link"
                onClick={() => setMobileOpen(false)}
              >
                Login
              </Link>
            </li>
            <li role="listitem">
              <Link
                to="/signup"
                className="landing-mobile-link landing-mobile-link--signup"
                onClick={() => setMobileOpen(false)}
              >
                Sign Up
              </Link>
            </li>
          </ul>
        </nav>
      </div>
    </>
  );
}
