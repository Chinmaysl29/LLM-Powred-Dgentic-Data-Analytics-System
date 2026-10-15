import { type FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { Mail, ArrowRight, CheckCircle2 } from 'lucide-react';
import { authService } from '../../services/authService';

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validateEmail(email: string): string | null {
  if (!email.trim()) return 'Email is required.';
  if (!EMAIL_REGEX.test(email)) return 'Enter a valid email address.';
  return null;
}

// ---------------------------------------------------------------------------
// ForgotPasswordPage Component — Approved Modern Split-Screen Auth Card
// ---------------------------------------------------------------------------

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleBlur = () => {
    setTouched(true);
    setEmailError(validateEmail(email));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    setTouched(true);

    const err = validateEmail(email);
    setEmailError(err);
    if (err || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await authService.forgotPassword({ email: email.trim() });
      setIsSent(true);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Unable to send reset email. Please try again.';
      setSubmitError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isSent) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="cinematic-auth-card"
      >
        <div style={{ textAlign: 'center', padding: '1rem 0' }}>
          <CheckCircle2
            className="w-12 h-12"
            style={{ color: '#151915', margin: '0 auto 1.25rem' }}
          />
          <h2 className="cinematic-card-title">Instructions sent</h2>
          <p className="cinematic-card-subtitle" style={{ marginBottom: '1.75rem' }}>
            If an account exists for <strong>{email}</strong>, password reset instructions have been sent. Check your inbox and spam folder.
          </p>
          <Link
            to="/login"
            className="cinematic-submit-btn"
            style={{ justifyContent: 'center', textDecoration: 'none' }}
          >
            <span>Return to Sign In</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, delay: 0.08, ease: 'easeOut' }}
      className="cinematic-auth-card"
    >
      <h2 className="cinematic-card-title">Reset password</h2>
      <p className="cinematic-card-subtitle">
        Enter your registered work email to receive secure password recovery instructions.
      </p>

      {/* Error banner */}
      {submitError && (
        <div className="cinematic-error-banner" role="alert">
          {submitError}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="cinematic-form">
        {/* Email */}
        <div className="cinematic-input-group">
          <label htmlFor="forgot-email" className="cinematic-label">
            Work Email
          </label>
          <div className="cinematic-input-wrapper">
            <input
              id="forgot-email"
              type="email"
              autoComplete="email"
              placeholder="analyst@enterprise.com"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (touched) setEmailError(validateEmail(e.target.value));
              }}
              onBlur={handleBlur}
              className={`cinematic-input ${
                touched && emailError ? 'cinematic-input--error' : ''
              }`}
              aria-invalid={Boolean(touched && emailError)}
              aria-describedby={touched && emailError ? 'forgot-email-error' : undefined}
              disabled={isSubmitting}
            />
            <Mail className="cinematic-input-icon" />
          </div>
          {touched && emailError && (
            <p id="forgot-email-error" className="cinematic-field-error" role="alert">
              {emailError}
            </p>
          )}
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={isSubmitting}
          className="cinematic-submit-btn"
          aria-label="Send reset link"
        >
          {isSubmitting ? (
            <>
              <span className="cinematic-spinner" aria-hidden="true" />
              <span>Sending instructions…</span>
            </>
          ) : (
            <>
              <span>Send reset link</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>

      {/* Login link */}
      <div className="cinematic-auth-footer">
        <span>Remember your password?</span>
        <Link to="/login">Sign in</Link>
      </div>
    </motion.div>
  );
}
