import { Link } from 'react-router-dom';
import { Palette, Shield, SlidersHorizontal } from 'lucide-react';
import { DEFAULT_APPEARANCE, useAppearance } from '../../hooks/useAppearance';
export default function SettingsPage() {
  const { appearance, update, storageError } = useAppearance();
  return <div className="ws-page"><header className="editorial-heading"><p className="eyebrow">YOUR WORKSPACE</p><h1 className="ws-page-heading">Make space for your work.</h1><p className="ws-page-sub">Appearance preferences are saved in this browser.</p></header>
    <div className="settings-editorial"><section className="surface-panel"><Palette size={24} /><h2>Appearance</h2>
      <label className="control-field">Theme<select value={appearance.theme} onChange={e => update({ ...appearance, theme: e.target.value as typeof appearance.theme })}><option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option></select></label>
      <label className="control-field">Accent palette<select value={appearance.accent} onChange={e => update({ ...appearance, accent: e.target.value as typeof appearance.accent })}><option value="lime">Lime</option><option value="sage">Sage</option></select></label>
      <label className="control-field">Sidebar density<select value={appearance.density} onChange={e => update({ ...appearance, density: e.target.value as typeof appearance.density })}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>
      <label className="preference-check"><input type="checkbox" checked={appearance.reducedMotion} onChange={e => update({ ...appearance, reducedMotion: e.target.checked })} /> Reduce motion</label>
      <p className="ws-page-sub">Your system's reduced-motion preference is always respected.</p><button className="reports-btn-secondary" onClick={() => update(DEFAULT_APPEARANCE)}>Reset appearance</button>
      {storageError && <p role="alert">{storageError}</p>}
    </section><div className="panel-stack"><section className="surface-panel"><Shield size={24} /><h2>Security & privacy</h2><p>Account access is managed by your authentication provider. Contact your administrator for retention, session and account changes.</p><Link to="/profile">Account details →</Link><Link to="/privacy">Privacy information →</Link></section>
      <section className="surface-panel"><SlidersHorizontal size={24} /><h2>Workspace configuration</h2><p>Notifications, API preferences and model configuration are administrator-managed. This deployment does not expose preference update APIs.</p><span className="capability-badge">Administrator managed</span></section></div></div></div>;
}
