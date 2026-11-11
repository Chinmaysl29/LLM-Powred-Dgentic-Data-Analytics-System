import React, { useState } from 'react';
import { X, RotateCcw, AlertCircle, Loader2 } from 'lucide-react';

interface ResetSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmReset: () => Promise<void>;
}

export const ResetSettingsModal: React.FC<ResetSettingsModalProps> = ({
  isOpen,
  onClose,
  onConfirmReset,
}) => {
  const [isResetting, setIsResetting] = useState(false);

  if (!isOpen) return null;

  const handleReset = async () => {
    setIsResetting(true);
    try {
      await onConfirmReset();
      onClose();
    } catch (err) {
      console.error('Failed to reset settings:', err);
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div
      className="settings-modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="reset-settings-title"
    >
      <div className="settings-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="settings-modal-header">
          <div className="settings-modal-header-title">
            <div className="settings-modal-icon-badge settings-modal-icon-badge--warning">
              <RotateCcw size={18} />
            </div>
            <div>
              <h3 id="reset-settings-title">Reset all settings?</h3>
              <p>Restore default application behavior</p>
            </div>
          </div>
          <button
            type="button"
            className="settings-modal-close"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={18} />
          </button>
        </div>

        <div className="settings-modal-body">
          <div className="settings-callout-warning">
            <AlertCircle size={18} className="settings-warning-icon" />
            <div>
              <p>Your application preferences will be restored to their factory default values.</p>
              <p className="settings-callout-subtext">
                <strong>Your datasets, reports, analyses and account will not be deleted.</strong>
              </p>
            </div>
          </div>

          <div className="settings-modal-actions">
            <button
              type="button"
              className="settings-btn-secondary"
              onClick={onClose}
              disabled={isResetting}
            >
              Cancel
            </button>
            <button
              type="button"
              className="settings-btn-warning"
              onClick={handleReset}
              disabled={isResetting}
            >
              {isResetting ? (
                <>
                  <Loader2 size={15} className="settings-spinner" />
                  Resetting...
                </>
              ) : (
                'Reset Settings'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
