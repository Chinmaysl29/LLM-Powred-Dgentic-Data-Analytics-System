import { type FormEvent, useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'motion/react';
import { Eye, EyeOff, ArrowRight, Lock, Mail } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

// ---------------------------------------------------------------------------
// Form Validation Helpers
// ---------------------------------------------------------------------------

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD_LENGTH = 8;

function validateEmail(email: string): string | null {
  if (!email.trim()) return 'Email address is required.';
  if (!EMAIL_REGEX.test(email)) return 'Enter a valid email address.';
  return null;
}

function validatePassword(password: string): string | null {
  if (!password) return 'Password is required.';
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// LoginPage Component — Modern Auth Card for Approved Split-Screen UI
// ---------------------------------------------------------------------------

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  // Retrieve post-login redirect path (default to /dashboard)
  const from = (location.state as { from?: string })?.from || '/dashboard';

  // Form Fields State
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // Validation & Submission State
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Field Blur Handlers
  const handleEmailBlur = () => {
    setTouched((prev) => ({ ...prev, email: true }));
    setErrors((prev) => ({ ...prev, email: validateEmail(email) ?? undefined }));
  };

  const handlePasswordBlur = () => {
    setTouched((prev) => ({ ...prev, password: true }));
    setErrors((prev) => ({ ...prev, password: validatePassword(password) ?? undefined }));
  };

  // Form Submit Handler
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    const emailErr = validateEmail(email);
    const passwordErr = validatePassword(password);

    setTouched({ email: true, password: true });
    setErrors({
      email: emailErr ?? undefined,
      password: passwordErr ?? undefined,
    });

    if (emailErr || passwordErr) return;
    if (isSubmitting) return;

    setIsSubmitting(true);
    try {
      await login({ email, password });
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Invalid credentials. Please verify and try again.';
      setSubmitError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, delay: 0.08, ease: 'easeOut' }}
      className="cinematic-auth-card"
    >
      <h2 className="cinematic-card-title">Welcome back</h2>
      <p className="cinematic-card-subtitle">
        Sign in to your analytical workspace to access your models, datasets, and reports.
      </p>

      {/* Error Banner */}
      {submitError && (
        <div className="cinematic-error-banner" role="alert">
          {submitError}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="cinematic-form">
        {/* Email Address */}
        <div className="cinematic-input-group">
          <label htmlFor="login-email" className="cinematic-label">
            Work Email
          </label>
          <div className="cinematic-input-wrapper">
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              placeholder="analyst@enterprise.com"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (touched.email) {
                  setErrors((prev) => ({
                    ...prev,
                    email: validateEmail(e.target.value) ?? undefined,
                  }));
                }
              }}
              onBlur={handleEmailBlur}
              className={`cinematic-input ${
                touched.email && errors.email ? 'cinematic-input--error' : ''
              }`}
              aria-invalid={Boolean(touched.email && errors.email)}
              aria-describedby={touched.email && errors.email ? 'email-error' : undefined}
              disabled={isSubmitting}
            />
            <Mail className="cinematic-input-icon" />
          </div>
          {touched.email && errors.email && (
            <p id="email-error" className="cinematic-field-error" role="alert">
              {errors.email}
            </p>
          )}
        </div>

        {/* Password */}
        <div className="cinematic-input-group">
          <div className="cinematic-label-row">
            <label htmlFor="login-password" className="cinematic-label">
              Password
            </label>
            <Link to="/forgot-password" className="cinematic-forgot-link">
              Forgot password?
            </Link>
          </div>
          <div className="cinematic-input-wrapper">
            <input
              id="login-password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (touched.password) {
                  setErrors((prev) => ({
                    ...prev,
                    password: validatePassword(e.target.value) ?? undefined,
                  }));
                }
              }}
              onBlur={handlePasswordBlur}
              className={`cinematic-input ${
                touched.password && errors.password ? 'cinematic-input--error' : ''
              }`}
              aria-invalid={Boolean(touched.password && errors.password)}
              aria-describedby={touched.password && errors.password ? 'password-error' : undefined}
              disabled={isSubmitting}
            />
            <Lock className="cinematic-input-icon" />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              className="cinematic-pw-toggle"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {touched.password && errors.password && (
            <p id="password-error" className="cinematic-field-error" role="alert">
              {errors.password}
            </p>
          )}
        </div>

        {/* Submit Action */}
        <button
          type="submit"
          disabled={isSubmitting}
          className="cinematic-submit-btn"
          aria-label="Sign in to your account"
        >
          {isSubmitting ? (
            <>
              <span className="cinematic-spinner" aria-hidden="true" />
              <span>Signing in…</span>
            </>
          ) : (
            <>
              <span>Sign in</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>

      {/* Signup prompt */}
      <div className="cinematic-auth-footer">
        <span>Don't have an enterprise account?</span>
        <Link to="/signup">Request access</Link>
      </div>
    </motion.div>
  );
}
