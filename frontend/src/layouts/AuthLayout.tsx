import { Link, Outlet, useLocation, Navigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { Sparkles } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { DataTransformationAnimation } from '../components/auth/DataTransformationAnimation';
import '../styles/login-motion.css';

/**
 * Approved Cinematic Auth & Landing Layout
 *
 * Implements the approved design direction across all public authentication routes:
 * - Off-white landing page background (#FAFBF7)
 * - Lime-green visual accents (#B8F641)
 * - "Your data. Finally makes sense." product showcase
 * - Animated analytics transformation pipeline
 * - Consistent typography and restrained styling
 * - Auto-redirects authenticated users to /dashboard
 */
export default function AuthLayout() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div
        className="cinematic-login-page"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div
            className="cinematic-spinner"
            style={{
              width: 28,
              height: 28,
              borderWidth: 3,
              borderColor: 'rgba(21, 25, 21, 0.15)',
              borderTopColor: '#151915',
              margin: '0 auto 1rem',
            }}
            aria-hidden="true"
          />
          <p className="cinematic-subhead" role="status">
            Checking session…
          </p>
        </div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const isSignup = location.pathname.startsWith('/signup');

  return (
    <div className="cinematic-login-page">
      {/* Top Brand Bar */}
      <header className="cinematic-login-topbar">
        <Link to="/" className="cinematic-brand-link">
          <div className="cinematic-brand-icon">
            <Sparkles className="w-4 h-4 text-[#B8F641]" />
          </div>
          <span>AI Data Analyst OS</span>
        </Link>

        <nav aria-label="Auxiliary navigation" className="cinematic-topbar-nav">
          <Link to="/" className="cinematic-tour-link">
            Product Tour
          </Link>
          {isSignup ? (
            <Link to="/login" className="cinematic-create-btn">
              Sign In
            </Link>
          ) : (
            <Link to="/signup" className="cinematic-create-btn">
              Create Account
            </Link>
          )}
        </nav>
      </header>

      {/* Main Split-Screen Layout */}
      <main className="cinematic-login-main">
        {/* Left Section — Cinematic Motion & Product Story */}
        <section className="cinematic-showcase-section" aria-label="Product Capabilities">
          <div className="cinematic-headline-group">
            <div>
              <span className="cinematic-tag-badge">
                Data Intelligence Redefined
              </span>
            </div>
            <h1 className="cinematic-headline">
              Your data. <br />
              <span className="cinematic-wavy-text">
                Finally makes sense.
              </span>
            </h1>
            <p className="cinematic-subhead">
              Transform scattered information into reliable, actionable intelligence. From turbulent
              raw files to verified metrics and predictive models in seconds.
            </p>
          </div>

          {/* Core Feature Badges */}
          <div className="cinematic-feature-pills">
            <span className="cinematic-feature-pill">
              <span className="cinematic-pill-dot cinematic-pill-dot--lime" />
              Automated Cleaning
            </span>
            <span className="cinematic-feature-pill">
              <span className="cinematic-pill-dot cinematic-pill-dot--dark" />
              Schema Enforcement
            </span>
            <span className="cinematic-feature-pill">
              <span className="cinematic-pill-dot cinematic-pill-dot--lime" />
              Predictive Models
            </span>
            <span className="cinematic-feature-pill">
              <span className="cinematic-pill-dot cinematic-pill-dot--muted" />
              Zero Hallucinations
            </span>
          </div>

          {/* Central Animated Data-Transformation Component */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <DataTransformationAnimation />
          </motion.div>
        </section>

        {/* Right Section — Authentication Card Slot */}
        <section className="cinematic-auth-section" aria-label="Authentication Form">
          <Outlet />
        </section>
      </main>

      {/* Page Footer */}
      <footer className="cinematic-login-footer">
        <span>© 2026 AI Data Analyst OS. Enterprise Analytical Intelligence.</span>
        <div className="cinematic-legal-links">
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/terms">Terms of Service</Link>
          <Link to="/dashboard">System Status</Link>
        </div>
      </footer>
    </div>
  );
}
