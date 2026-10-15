import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Database, FileUp, Server, CheckCircle2, AlertCircle, Loader2, X, Trash2, RefreshCw } from 'lucide-react';
import { connectionService, type DatabaseConnection, type ConnectionTestResult } from '../../services/connectionService';

export default function ConnectionsPage() {
  const [activeModal, setActiveModal] = useState<'postgresql' | 'mysql' | null>(null);
  const [connName, setConnName] = useState('');
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState(5432);
  const [database, setDatabase] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [schemaName, setSchemaName] = useState('public');

  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [savedConnections, setSavedConnections] = useState<DatabaseConnection[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  // Default workspace ID
  const workspaceId = '00000000-0000-0000-0000-000000000000';

  useEffect(() => {
    loadConnections();
  }, []);

  async function loadConnections() {
    setLoadingList(true);
    try {
      const list = await connectionService.listConnections(workspaceId);
      setSavedConnections(Array.isArray(list) ? list : []);
    } catch {
      // If workspace does not exist yet or unauthenticated in dev, keep empty list
      setSavedConnections([]);
    } finally {
      setLoadingList(false);
    }
  }

  function openModal(type: 'postgresql' | 'mysql') {
    setActiveModal(type);
    setConnName(type === 'postgresql' ? 'Production Postgres' : 'Main MySQL');
    setHost('localhost');
    setPort(type === 'postgresql' ? 5432 : 3306);
    setDatabase('');
    setUsername(type === 'postgresql' ? 'postgres' : 'root');
    setPassword('');
    setSchemaName('public');
    setTestResult(null);
    setFormError(null);
  }

  function closeModal() {
    setActiveModal(null);
    setTestResult(null);
    setFormError(null);
  }

  async function handleTest() {
    if (!activeModal) return;
    if (!host || !database || !username) {
      setFormError('Please enter Host, Database name, and Username.');
      return;
    }
    setTesting(true);
    setFormError(null);
    setTestResult(null);

    try {
      const res = await connectionService.testConnection({
        connector_type: activeModal,
        host,
        port: Number(port),
        database,
        username,
        password,
        schema_name: activeModal === 'postgresql' ? schemaName : undefined,
      });
      setTestResult(res);
    } catch (err: any) {
      const msg = err.response?.data?.detail?.message || err.response?.data?.detail || err.message || 'Connection test failed';
      setFormError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    if (!activeModal) return;
    if (!connName.trim()) {
      setFormError('Please enter a connection name.');
      return;
    }
    setSaving(true);
    setFormError(null);

    try {
      await connectionService.saveConnection({
        workspace_id: workspaceId,
        connector_name: connName.trim(),
        connector_type: activeModal,
        host,
        port: Number(port),
        database,
        username,
        password,
        schema_name: activeModal === 'postgresql' ? schemaName : undefined,
      });
      closeModal();
      void loadConnections();
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Failed to save connection';
      setFormError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(connId: string) {
    try {
      await connectionService.deleteConnection(connId, workspaceId);
      setSavedConnections(prev => prev.filter(c => c.id !== connId));
    } catch (err) {
      console.error('Delete connection error:', err);
    }
  }

  return (
    <div className="ws-page">
      <header className="editorial-heading">
        <p className="eyebrow">DATA MANAGEMENT / CONNECTIONS</p>
        <h1 className="ws-page-heading">Bring your data together.</h1>
        <p className="ws-page-sub">Connect directly to your relational databases or upload structured datasets.</p>
      </header>

      <div className="connector-grid">
        <section className="surface-panel">
          <FileUp size={30} />
          <h2>File upload</h2>
          <p>Import CSV, XLSX, TSV, JSON, JSONL, Parquet, or documents and inspect schema and quality.</p>
          <span className="capability-badge">Available</span>
          <br /><br />
          <Link className="reports-btn-secondary" to="/datasets/upload">Upload dataset →</Link>
        </section>

        <section className="surface-panel">
          <Database size={30} />
          <h2>PostgreSQL</h2>
          <p>Connect to an external PostgreSQL database with table discovery and read-only schema inspection.</p>
          <span className="capability-badge" style={{ background: '#22c55e', color: '#fff' }}>Supported</span>
          <br /><br />
          <button className="reports-btn-secondary" onClick={() => openModal('postgresql')}>
            Configure connection →
          </button>
        </section>

        <section className="surface-panel">
          <Server size={30} />
          <h2>MySQL</h2>
          <p>Connect to an external MySQL instance to synchronize schemas and query permitted tables.</p>
          <span className="capability-badge" style={{ background: '#22c55e', color: '#fff' }}>Supported</span>
          <br /><br />
          <button className="reports-btn-secondary" onClick={() => openModal('mysql')}>
            Configure connection →
          </button>
        </section>
      </div>

      {/* Configured Connections List */}
      <section className="surface-panel" style={{ marginTop: 24, padding: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <p className="eyebrow">ACTIVE DATA SOURCES</p>
            <h2 style={{ fontSize: 20, margin: '4px 0' }}>Configured Database Connections</h2>
          </div>
          <button className="reports-btn-secondary" onClick={loadConnections} disabled={loadingList}>
            <RefreshCw size={14} className={loadingList ? 'spin' : ''} /> Refresh
          </button>
        </div>

        {savedConnections.length === 0 ? (
          <p className="source-note" style={{ margin: 0 }}>
            No external database connections configured yet. Click "Configure connection" above to link a PostgreSQL or MySQL database.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {savedConnections.map(c => (
              <div
                key={c.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '14px 18px',
                  background: 'var(--surface-raised, #172015)',
                  borderRadius: 10,
                  border: '1px solid var(--border)',
                }}
              >
                <div>
                  <strong style={{ fontSize: 16, color: 'var(--text-h)' }}>{c.connector_name}</strong>
                  <span style={{ marginLeft: 10, fontSize: 12, padding: '2px 8px', borderRadius: 4, background: '#22c55e22', color: '#22c55e' }}>
                    {c.connector_subtype.toUpperCase()} · {c.status}
                  </span>
                  <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
                    Host: {c.config.host}:{c.config.port} | Database: {c.config.database} | User: {c.config.username}
                  </p>
                </div>
                <button
                  className="reports-btn-secondary"
                  style={{ color: '#ef4444', borderColor: '#ef444444' }}
                  onClick={() => handleDelete(c.id)}
                >
                  <Trash2 size={14} /> Disconnect
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Connection Modal */}
      {activeModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 20,
          }}
        >
          <div
            style={{
              background: '#151b17',
              border: '1px solid #2d3e30',
              borderRadius: 16,
              maxWidth: 540,
              width: '100%',
              padding: 28,
              boxShadow: '0 20px 40px rgba(0,0,0,0.5)',
              color: '#cbd5c7',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <p className="eyebrow" style={{ color: '#c8fd39' }}>EXTERNAL DATA CONNECTOR</p>
                <h2 style={{ color: '#fff', margin: 0, fontSize: 22 }}>
                  Configure {activeModal === 'postgresql' ? 'PostgreSQL' : 'MySQL'} Source
                </h2>
              </div>
              <button
                onClick={closeModal}
                style={{ background: 'transparent', border: 'none', color: '#888', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div style={{ gridColumn: 'span 2' }}>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Connection Name</label>
                <input
                  type="text"
                  value={connName}
                  onChange={e => setConnName(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', background: '#1c241e', border: '1px solid #334435', borderRadius: 8, color: '#fff' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Host / IP</label>
                <input
                  type="text"
                  value={host}
                  onChange={e => setHost(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', background: '#1c241e', border: '1px solid #334435', borderRadius: 8, color: '#fff' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Port</label>
                <input
                  type="number"
                  value={port}
                  onChange={e => setPort(Number(e.target.value))}
                  style={{ width: '100%', padding: '10px 12px', background: '#1c241e', border: '1px solid #334435', borderRadius: 8, color: '#fff' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Database Name</label>
                <input
                  type="text"
                  value={database}
                  onChange={e => setDatabase(e.target.value)}
                  placeholder="e.g. analytics_db"
                  style={{ width: '100%', padding: '10px 12px', background: '#1c241e', border: '1px solid #334435', borderRadius: 8, color: '#fff' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', background: '#1c241e', border: '1px solid #334435', borderRadius: 8, color: '#fff' }}
                />
              </div>

              <div style={{ gridColumn: activeModal === 'postgresql' ? 'span 1' : 'span 2' }}>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{ width: '100%', padding: '10px 12px', background: '#1c241e', border: '1px solid #334435', borderRadius: 8, color: '#fff' }}
                />
              </div>

              {activeModal === 'postgresql' && (
                <div>
                  <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Schema Name</label>
                  <input
                    type="text"
                    value={schemaName}
                    onChange={e => setSchemaName(e.target.value)}
                    placeholder="public"
                    style={{ width: '100%', padding: '10px 12px', background: '#1c241e', border: '1px solid #334435', borderRadius: 8, color: '#fff' }}
                  />
                </div>
              )}
            </div>

            {formError && (
              <div style={{ marginTop: 16, padding: '10px 14px', background: '#451a1a', border: '1px solid #ef4444', borderRadius: 8, color: '#fca5a5', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertCircle size={16} />
                <span>{formError}</span>
              </div>
            )}

            {testResult && (
              <div style={{ marginTop: 16, padding: '12px 14px', background: '#14331e', border: '1px solid #22c55e', borderRadius: 8, color: '#86efac', fontSize: 13 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                  <CheckCircle2 size={16} />
                  <span>{testResult.message} ({testResult.latency_ms}ms)</span>
                </div>
                {testResult.tables.length > 0 && (
                  <p style={{ margin: '6px 0 0', fontSize: 12, color: '#cbd5c7' }}>
                    Tables: {testResult.tables.slice(0, 8).join(', ')}{testResult.tables.length > 8 ? ` +${testResult.tables.length - 8} more` : ''}
                  </p>
                )}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24 }}>
              <button
                type="button"
                className="reports-btn-secondary"
                onClick={handleTest}
                disabled={testing || saving}
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              >
                {testing && <Loader2 size={14} className="spin" />}
                {testing ? 'Testing...' : 'Test Connection'}
              </button>
              <button
                type="button"
                className="reports-btn-primary"
                onClick={handleSave}
                disabled={saving || testing}
                style={{ background: '#c8fd39', color: '#101312', border: 'none', padding: '10px 20px', borderRadius: 8, fontWeight: 600, cursor: 'pointer' }}
              >
                {saving ? 'Saving...' : 'Save Connection'}
              </button>
            </div>
          </div>
        </div>
      )}

      <section className="analysis-hero">
        <div>
          <p className="eyebrow">EXPLORE WHAT IS CONNECTED</p>
          <h2>Understand your schema.</h2>
          <p>Browse tables, column types and relationships returned by the configured database.</p>
        </div>
        <Link className="editorial-link" to="/data-warehouse">Open data warehouse ↗</Link>
      </section>
    </div>
  );
}
