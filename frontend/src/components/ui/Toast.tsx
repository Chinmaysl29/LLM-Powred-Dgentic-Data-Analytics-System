/**
 * Toast Notification System � Phase 23.12
 *
 * Provides a global toast notification center with:
 *  - success, error, warning, info variants
 *  - auto-dismiss with progress bar
 *  - manual dismiss
 *  - stacked notifications (up to 5)
 *  - useToast hook for easy integration
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ToastContext, type Toast, type ToastVariant } from '../../hooks/useToast';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Individual Toast item
// ---------------------------------------------------------------------------

const ICONS: Record<ToastVariant, typeof CheckCircle> = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

interface ToastItemProps {
  toast: Toast;
  onRemove: (id: string) => void;
}

function ToastItem({ toast, onRemove }: ToastItemProps) {
  const [visible, setVisible] = useState(false);
  const [progress, setProgress] = useState(100);
  const duration = toast.duration ?? 4500;
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dismissRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleDismiss = useCallback(() => {
    if (dismissRef.current !== null) return;
    if (intervalRef.current) clearInterval(intervalRef.current);
    setVisible(false);
    dismissRef.current = setTimeout(() => onRemove(toast.id), 300);
  }, [onRemove, toast.id]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true));
    const startedAt = Date.now();
    if (duration > 0) {
      intervalRef.current = setInterval(() => {
        const remaining = Math.max(0, 100 - ((Date.now() - startedAt) / duration) * 100);
        setProgress(remaining);
        if (remaining <= 0) handleDismiss();
      }, 50);
    }
    return () => {
      cancelAnimationFrame(frame);
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (dismissRef.current) clearTimeout(dismissRef.current);
      dismissRef.current = null;
    };
  }, [duration, handleDismiss]);

  const Icon = ICONS[toast.variant];

  return (
    <div
      className={`toast toast--${toast.variant}${visible ? ' toast--visible' : ''}`}
      role="alert"
      aria-live="polite"
    >
      <span className="toast-icon" aria-hidden="true">
        <Icon size={16} />
      </span>
      <div className="toast-body">
        <span className="toast-message">{toast.message}</span>
        {toast.description && <span className="toast-description">{toast.description}</span>}
      </div>
      <button
        type="button"
        className="toast-dismiss"
        onClick={handleDismiss}
        aria-label="Dismiss notification"
      >
        <X size={14} />
      </button>
      {duration > 0 && (
        <div className="toast-progress" style={{ width: `${progress}%` }} aria-hidden="true" />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((opts: Omit<Toast, 'id'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts((prev) => [...prev.slice(-4), { ...opts, id }]); // max 5
  }, []);

  const success = useCallback(
    (message: string, description?: string) =>
      addToast({ message, description, variant: 'success' }),
    [addToast],
  );
  const error = useCallback(
    (message: string, description?: string) =>
      addToast({ message, description, variant: 'error', duration: 6000 }),
    [addToast],
  );
  const warning = useCallback(
    (message: string, description?: string) =>
      addToast({ message, description, variant: 'warning' }),
    [addToast],
  );
  const info = useCallback(
    (message: string, description?: string) => addToast({ message, description, variant: 'info' }),
    [addToast],
  );

  return (
    <ToastContext.Provider value={{ addToast, removeToast, success, error, warning, info }}>
      {children}
      <div className="toast-container" aria-label="Notifications" role="region">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onRemove={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
