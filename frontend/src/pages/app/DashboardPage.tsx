import { useCallback, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Database, MessageSquare, BarChart3 } from 'lucide-react';
import { datasetService } from '../../services/datasetService';
import { getStoredReports } from '../../services/reportsService';
import { useAsyncResource } from '../../hooks/useAsyncResource';
export default function DashboardPage() {
  const navigate = useNavigate();
  const [revision, setRevision] = useState(0);
  const [question, setQuestion] = useState('');
  const fetchOverview = useCallback(
    () => Promise.allSettled([datasetService.list(0, 100), getStoredReports()]),
    [],
  );
  const overview = useAsyncResource(fetchOverview, revision);
  const datasetsResult = overview.data?.[0];
  const reportsResult = overview.data?.[1];
  const datasets = datasetsResult?.status === 'fulfilled' ? datasetsResult.value : [];
  const reports = reportsResult?.status === 'fulfilled' ? reportsResult.value : [];
  const error =
    datasetsResult?.status === 'rejected'
      ? datasetsResult.reason instanceof Error
        ? datasetsResult.reason.message
        : 'Unable to load datasets.'
      : overview.error;
  const reportError =
    reportsResult?.status === 'rejected'
      ? reportsResult.reason instanceof Error
        ? reportsResult.reason.message
        : 'Unable to load reports.'
      : overview.error;
  const loading = overview.loading;
  const load = () => setRevision((value) => value + 1);
  const profiled = datasets.filter((d) => d.quality_score != null);
  return (
    <div className="ws-page dashboard-overview">
      <header className="editorial-heading">
        <p className="eyebrow">WORKSPACE / OVERVIEW</p>
        <h1 className="ws-page-heading">Your data. A clearer view.</h1>
        <p className="ws-page-sub">Move from raw information to questions worth exploring.</p>
      </header>
      <div className="metric-strip">
        <Link className="metric-tile" to="/datasets">
          <span>Available datasets</span>
          <strong>
            {loading || error ? '—' : `${datasets.length}${datasets.length === 100 ? '+' : ''}`}
          </strong>
          <small>
            {datasets.length === 100 ? 'First 100 registry records loaded' : 'Dataset registry'}
          </small>
        </Link>
        <Link className="metric-tile" to="/reports">
          <span>Saved reports</span>
          <strong>{loading || reportError ? '—' : reports.length}</strong>
          <small>Returned report history</small>
        </Link>
        <Link className="metric-tile" to="/datasets">
          <span>Quality profiles</span>
          <strong>{loading || error ? '—' : profiled.length}</strong>
          <small>Loaded datasets with a quality score</small>
        </Link>
      </div>
      <form
        className="ws-composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) navigate('/analysis', { state: { question: question.trim() } });
        }}
      >
        <p className="eyebrow" style={{ color: '#c8fd39' }}>
          YOUR AI ANALYST
        </p>
        <h2 style={{ color: '#fff' }}>What would you like to understand?</h2>
        <label className="sr-only" htmlFor="dashboard-question">
          Analytical question
        </label>
        <textarea
          id="dashboard-question"
          className="ws-composer-textarea"
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about your dataset"
        />
        <div className="ws-composer-footer">
          <button className="ws-composer-send" disabled={!question.trim()}>
            Open analysis ↗
          </button>
        </div>
      </form>
      <div className="ws-quick-grid">
        {[
          {
            to: '/datasets/upload',
            icon: Database,
            title: 'Bring your data',
            description: 'Upload and profile a supported file.',
          },
          {
            to: '/analysis',
            icon: MessageSquare,
            title: 'Ask a question',
            description: 'Inspect answers and their evidence.',
          },
          {
            to: '/visualizations',
            icon: BarChart3,
            title: 'Find a perspective',
            description: 'Build charts from actual records.',
          },
        ].map((action) => (
          <Link key={action.to} to={action.to} className="ws-quick-card">
            <action.icon size={20} />
            <h2 className="ws-quick-card-title">{action.title}</h2>
            <p className="ws-quick-card-desc">{action.description}</p>
          </Link>
        ))}
      </div>
      <section className="ws-section-card">
        <div className="ws-section-card-header">
          <h2 className="ws-section-card-title">Dataset registry</h2>
          <Link to="/datasets" className="ws-section-card-link">
            View all datasets →
          </Link>
        </div>
        {loading ? (
          <p className="ws-empty" role="status">
            Loading datasets…
          </p>
        ) : error ? (
          <div className="ws-empty" role="alert">
            <p>{error}</p>
            <button className="reports-btn-secondary" onClick={() => void load()}>
              Try again
            </button>
          </div>
        ) : datasets.length ? (
          <div className="ws-dataset-list">
            {datasets.slice(0, 5).map((ds) => (
              <Link
                key={ds.dataset_id}
                className="ws-dataset-item"
                to={'/datasets/' + encodeURIComponent(ds.dataset_id)}
              >
                <Database size={18} />
                <div className="ws-dataset-info">
                  <p className="ws-dataset-name">{ds.name}</p>
                  <p className="ws-dataset-meta">
                    {(ds.row_count ?? 0).toLocaleString()} rows · {ds.column_count} columns
                  </p>
                </div>
                <span className="ws-badge">{ds.status}</span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="ws-empty">
            <Database size={28} />
            <h3>No datasets uploaded yet.</h3>
            <p>Upload a supported data file to begin.</p>
            <Link className="reports-create-btn" to="/datasets/upload">
              Upload dataset
            </Link>
          </div>
        )}
      </section>
      <section className="ws-section-card">
        <div className="ws-section-card-header">
          <h2 className="ws-section-card-title">Recent reports</h2>
          <Link className="ws-section-card-link" to="/reports">
            Open report library →
          </Link>
        </div>
        {loading ? (
          <p className="ws-empty" role="status">
            Loading reports…
          </p>
        ) : reportError ? (
          <div className="ws-empty" role="alert">
            <p>{reportError}</p>
            <button className="reports-btn-secondary" onClick={() => void load()}>
              Retry reports
            </button>
          </div>
        ) : reports.length ? (
          <div className="ws-dataset-list">
            {reports.slice(0, 4).map((r) => (
              <Link
                key={r.id}
                className="ws-dataset-item"
                to={'/reports/' + encodeURIComponent(r.id)}
              >
                <div>
                  <p className="ws-dataset-name">{r.title}</p>
                  <p className="ws-dataset-meta">
                    {r.report_type} · {new Date(r.created_at).toLocaleDateString()}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <p className="ws-empty">No reports returned by the report library.</p>
        )}
      </section>
      <p className="source-note">
        Activity totals and analysis counts are unavailable from the connected workspace APIs.
        Explore recent questions within your current analysis session.
      </p>
    </div>
  );
}
