import React, { useState } from 'react';
import { X, AlertTriangle, Loader2, CheckCircle2 } from 'lucide-react';
import { profileService } from '../../services/profileService';

interface DeleteAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAccountDeleted?: () => void;
}

export const DeleteAccountModal: React.FC<DeleteAccountModalProps> = ({
  isOpen,
  onClose,
  onAccountDeleted,
}) => {
  const [confirmationInput, setConfirmationInput] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [scheduled, setScheduled] = useState(false);

  if (!isOpen) return null;

  const handleReset = () => {
    setConfirmationInput('');
    setIsDeleting(false);
    setScheduled(false);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleDelete = async () => {
    if (confirmationInput !== 'DELETE') return;

    setIsDeleting(true);
    try {
      await profileService.deleteAccount();
      setScheduled(true);
      setTimeout(() => {
        handleClose();
        if (onAccountDeleted) {
          onAccountDeleted();
        }
      }, 1800);
    } catch (err) {
      console.error('Account deletion request failed:', err);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div
      className="profile-modal-backdrop"
      onClick={handleClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-account-title"
    >
      <div
        className="profile-modal-card profile-modal-card--danger"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="profile-modal-header">
          <div className="profile-modal-header-title">
            <div className="profile-modal-icon-badge profile-modal-icon-badge--danger">
              <AlertTriangle size={18} />
            </div>
            <div>
              <h3 id="delete-account-title">Delete your account?</h3>
              <p>Permanent, irreversible action</p>
            </div>
          </div>
          <button
            type="button"
            className="profile-modal-close"
            onClick={handleClose}
            aria-label="Close dialog"
          >
            <X size={18} />
          </button>
        </div>

        {scheduled ? (
          <div className="profile-modal-success-state">
            <CheckCircle2 size={36} className="profile-danger-text" />
            <h4>Account Deletion Scheduled</h4>
            <p>Your account deletion request has been submitted.</p>
          </div>
        ) : (
          <div className="profile-modal-body">
            <div className="profile-danger-callout">
              <p>
                This action permanently removes your account, personal details, uploaded datasets,
                reports, and generated AI intelligence. <strong>This cannot be undone.</strong>
              </p>
            </div>

            <div className="profile-form-group" style={{ marginTop: 16 }}>
              <label htmlFor="confirm-delete-input">
                To confirm, type <span className="profile-code-pill">DELETE</span> below:
              </label>
              <input
                id="confirm-delete-input"
                type="text"
                className="profile-input"
                placeholder="DELETE"
                value={confirmationInput}
                onChange={(e) => setConfirmationInput(e.target.value)}
                disabled={isDeleting}
                autoComplete="off"
              />
            </div>

            <div className="profile-modal-actions">
              <button
                type="button"
                className="profile-btn-secondary"
                onClick={handleClose}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="profile-btn-danger"
                disabled={confirmationInput !== 'DELETE' || isDeleting}
                onClick={handleDelete}
              >
                {isDeleting ? (
                  <>
                    <Loader2 size={15} className="profile-spinner" />
                    Processing...
                  </>
                ) : (
                  'Delete Account'
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
