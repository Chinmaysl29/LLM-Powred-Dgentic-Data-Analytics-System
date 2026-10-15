import { type FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { Eye, EyeOff, ArrowRight, Lock, Mail, User as UserIcon, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

// ---------------------------------------------------------------------------
// Validation helpers
// ---------------------------------------------------------------------------

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD_LENGTH = 8;

function validateEmail(email: string): string | null {
  if (!email.trim()) return 'Work email is required.';
  if (!EMAIL_REGEX.test(email)) return 'Enter a valid corporate email address.';
  return null;
}

function validateFullName(name: string): string | null {
  if (!name.trim()) return 'Full name is required.';
  if (name.trim().length < 2) return 'Full name must be at least 2 characters.';
  return null;
}

function validatePassword(password: string): string | null {
  if (!password) return 'Password is required.';
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  return null;
}

function validateConfirmPassword(password: string, confirm: string): string | null {
  if (!confirm) return 'Please confirm your password.';
  if (confirm !== password) return 'Passwords do not match.';
  return null;
}

// ---------------------------------------------------------------------------
// SignupPage Component — Approved Modern Split-Screen Auth Card
// ---------------------------------------------------------------------------

export default function SignupPage() {
  const navigate = useNavigate();
  const { signup, login } = useAuth();

  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [errors, setErrors] = useState<{
    email?: string;
    fullName?: string;
    password?: string;
    confirmPassword?: string;
  }>({});
  const [touched, setTouched] = useState<{
    email?: boolean;
    fullName?: boolean;
    password?: boolean;
    confirmPassword?: boolean;
  }>({});

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [signupSuccess, setSignupSuccess] = useState(false);

  const handleBlur = (field: 'email' | 'fullName' | 'password' | 'confirmPassword') => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    setErrors((prev) => {
      const updated = { ...prev };
      if (field === 'email') updated.email = validateEmail(email) ?? undefined;
      if (field === 'fullName') updated.fullName = validateFullName(fullName) ?? undefined;
      if (field === 'password') updated.password = validatePassword(password) ?? undefined;
      if (field === 'confirmPassword')
        updated.confirmPassword = validateConfirmPassword(password, confirmPassword) ?? undefined;
      return updated;
    });
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    const emailErr = validateEmail(email);
    const nameErr = validateFullName(fullName);
    const pwErr = validatePassword(password);
    const confirmErr = validateConfirmPassword(password, confirmPassword);

    setTouched({
      email: true,
      fullName: true,
      password: true,
      confirmPassword: true,
    });
    setErrors({
      email: emailErr ?? undefined,
      fullName: nameErr ?? undefined,
      password: pwErr ?? undefined,
      confirmPassword: confirmErr ?? undefined,
    });

    if (emailErr || nameErr || pwErr || confirmErr) return;
    if (isSubmitting) return;

    setIsSubmitting(true);
    try {
      await signup({
        email: email.trim(),
        full_name: fullName.trim(),
        password,
      });

      // Try automatic login
      try {
        await login({ email: email.trim(), password });
        navigate('/dashboard', { replace: true });
      } catch (loginErr: unknown) {
        // If login failed because Supabase requires email verification
        const msg = loginErr instanceof Error ? loginErr.message : '';
        if (msg.includes('confirm') || msg.includes('verification')) {
          setSignupSuccess(true);
        } else {
          // If login failed for another reason, show success state so user can proceed
          setSignupSuccess(true);
        }
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Unable to create account. Please try again.';
      setSubmitError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (signupSuccess) {
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
          <h2 className="cinematic-card-title">Check your email</h2>
          <p className="cinematic-card-subtitle" style={{ marginBottom: '1.75rem' }}>
            We sent a verification link to <strong>{email}</strong>. Please confirm your email address to activate your analytical workspace.
          </p>
          <Link
            to="/login"
            className="cinematic-submit-btn"
            style={{ justifyContent: 'center', textDecoration: 'none' }}
          >
            <span>Proceed to Sign In</span>
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
      <h2 className="cinematic-card-title">Create your account</h2>
      <p className="cinematic-card-subtitle">
        Deploy an intelligent data analytics workspace for your enterprise.
      </p>

      {/* Error banner */}
      {submitError && (
        <div className="cinematic-error-banner" role="alert">
          {submitError}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="cinematic-form">
        {/* Full Name */}
        <div className="cinematic-input-group">
          <label htmlFor="signup-name" className="cinematic-label">
            Full Name
          </label>
          <div className="cinematic-input-wrapper">
            <input
              id="signup-name"
              type="text"
              autoComplete="name"
              placeholder="Jane Doe"
              value={fullName}
              onChange={(e) => {
                setFullName(e.target.value);
                if (touched.fullName) {
                  setErrors((prev) => ({
                    ...prev,
                    fullName: validateFullName(e.target.value) ?? undefined,
                  }));
                }
              }}
              onBlur={() => handleBlur('fullName')}
              className={`cinematic-input ${
                touched.fullName && errors.fullName ? 'cinematic-input--error' : ''
              }`}
              aria-invalid={Boolean(touched.fullName && errors.fullName)}
              aria-describedby={touched.fullName && errors.fullName ? 'name-error' : undefined}
              disabled={isSubmitting}
            />
            <UserIcon className="cinematic-input-icon" />
          </div>
          {touched.fullName && errors.fullName && (
            <p id="name-error" className="cinematic-field-error" role="alert">
              {errors.fullName}
            </p>
          )}
        </div>

        {/* Email */}
        <div className="cinematic-input-group">
          <label htmlFor="signup-email" className="cinematic-label">
            Work Email
          </label>
          <div className="cinematic-input-wrapper">
            <input
              id="signup-email"
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
              onBlur={() => handleBlur('email')}
              className={`cinematic-input ${
                touched.email && errors.email ? 'cinematic-input--error' : ''
              }`}
              aria-invalid={Boolean(touched.email && errors.email)}
              aria-describedby={touched.email && errors.email ? 'signup-email-error' : undefined}
              disabled={isSubmitting}
            />
            <Mail className="cinematic-input-icon" />
          </div>
          {touched.email && errors.email && (
            <p id="signup-email-error" className="cinematic-field-error" role="alert">
              {errors.email}
            </p>
          )}
        </div>

        {/* Password */}
        <div className="cinematic-input-group">
          <label htmlFor="signup-password" className="cinematic-label">
            Password (min. 8 characters)
          </label>
          <div className="cinematic-input-wrapper">
            <input
              id="signup-password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
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
              onBlur={() => handleBlur('password')}
              className={`cinematic-input ${
                touched.password && errors.password ? 'cinematic-input--error' : ''
              }`}
              aria-invalid={Boolean(touched.password && errors.password)}
              aria-describedby={touched.password && errors.password ? 'signup-password-error' : undefined}
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
            <p id="signup-password-error" className="cinematic-field-error" role="alert">
              {errors.password}
            </p>
          )}
        </div>

        {/* Confirm Password */}
        <div className="cinematic-input-group">
          <label htmlFor="signup-confirm" className="cinematic-label">
            Confirm Password
          </label>
          <div className="cinematic-input-wrapper">
            <input
              id="signup-confirm"
              type={showConfirm ? 'text' : 'password'}
              autoComplete="new-password"
              placeholder="••••••••••••"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                if (touched.confirmPassword) {
                  setErrors((prev) => ({
                    ...prev,
                    confirmPassword:
                      validateConfirmPassword(password, e.target.value) ?? undefined,
                  }));
                }
              }}
              onBlur={() => handleBlur('confirmPassword')}
              className={`cinematic-input ${
                touched.confirmPassword && errors.confirmPassword ? 'cinematic-input--error' : ''
              }`}
              aria-invalid={Boolean(touched.confirmPassword && errors.confirmPassword)}
              aria-describedby={
                touched.confirmPassword && errors.confirmPassword ? 'confirm-error' : undefined
              }
              disabled={isSubmitting}
            />
            <Lock className="cinematic-input-icon" />
            <button
              type="button"
              onClick={() => setShowConfirm((prev) => !prev)}
              className="cinematic-pw-toggle"
              aria-label={showConfirm ? 'Hide confirm password' : 'Show confirm password'}
            >
              {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {touched.confirmPassword && errors.confirmPassword && (
            <p id="confirm-error" className="cinematic-field-error" role="alert">
              {errors.confirmPassword}
            </p>
          )}
        </div>

        {/* Submit Action */}
        <button
          type="submit"
          disabled={isSubmitting}
          className="cinematic-submit-btn"
          aria-label="Create your account"
        >
          {isSubmitting ? (
            <>
              <span className="cinematic-spinner" aria-hidden="true" />
              <span>Creating account…</span>
            </>
          ) : (
            <>
              <span>Create account</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>

      {/* Login link */}
      <div className="cinematic-auth-footer">
        <span>Already have an enterprise account?</span>
        <Link to="/login">Sign in</Link>
      </div>
    </motion.div>
  );
}
