import React from 'react';
import { X, Terminal, Copy, Check } from 'lucide-react';

interface DebugInfoModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DebugInfoModal: React.FC<DebugInfoModalProps> = ({ isOpen, onClose }) => {
  const [copied, setCopied] = React.useState(false);

  if (!isOpen) return null;

  const debugData = {
    appVersion: 'v1.0.0-phase9',
    environment: 'development',
    framework: 'React 18.3.1 · Vite 8.2.1',
    viewport: `${window.innerWidth} × ${window.innerHeight}`,
    screenResolution: `${window.screen.width} × ${window.screen.height}`,
    devicePixelRatio: `${window.devicePixelRatio || 1}x`,
    colorScheme: 'Dark (Strict)',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    userAgent: navigator.userAgent,
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(debugData, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className="settings-modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="debug-info-title"
    >
      <div className="settings-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="settings-modal-header">
          <div className="settings-modal-header-title">
            <div className="settings-modal-icon-badge">
              <Terminal size={18} />
            </div>
            <div>
              <h3 id="debug-info-title">System & Diagnostic Info</h3>
              <p>Client runtime parameters for troubleshooting</p>
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
          <div className="settings-debug-grid">
            <div className="settings-debug-row">
              <span className="settings-debug-label">Application Version</span>
              <span className="settings-debug-val">{debugData.appVersion}</span>
            </div>
            <div className="settings-debug-row">
              <span className="settings-debug-label">Client Runtime</span>
              <span className="settings-debug-val">{debugData.framework}</span>
            </div>
            <div className="settings-debug-row">
              <span className="settings-debug-label">Viewport Geometry</span>
              <span className="settings-debug-val">{debugData.viewport}</span>
            </div>
            <div className="settings-debug-row">
              <span className="settings-debug-label">Display Resolution</span>
              <span className="settings-debug-val">
                {debugData.screenResolution} ({debugData.devicePixelRatio})
              </span>
            </div>
            <div className="settings-debug-row">
              <span className="settings-debug-label">Active Timezone</span>
              <span className="settings-debug-val">{debugData.timezone}</span>
            </div>
            <div className="settings-debug-row">
              <span className="settings-debug-label">Theme Engine</span>
              <span className="settings-debug-val">{debugData.colorScheme}</span>
            </div>
          </div>

          <div className="settings-modal-actions">
            <button type="button" className="settings-btn-secondary" onClick={handleCopy}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy Diagnostics'}
            </button>
            <button type="button" className="settings-btn-primary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
