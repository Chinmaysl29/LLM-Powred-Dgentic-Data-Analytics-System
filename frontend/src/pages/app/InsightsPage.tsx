import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { datasetService } from '../../services/datasetService';
import { useAsyncResource } from '../../hooks/useAsyncResource';
interface Finding {
  recommendation_id: string;
  description: string;
  suggested_action: string;
  severity: string;
  column_name?: string;
}
export default function InsightsPage(_props: { subView?: string }) {
  const [selectedId, setSelected] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const fetchDatasets = useCallback(() => datasetService.list(), []);
  const registry = useAsyncResource(fetchDatasets, retry);
  const datasets = registry.data ?? [];
  const selected = selectedId ?? datasets[0]?.dataset_id ?? '';
  const fetchFindings = useCallback(
    (signal: AbortSignal) =>
      apiClient.get<{ recommendations: Finding[] }>(
        '/api/v1/datasets/' + encodeURIComponent(selected) + '/recommendations',
        { signal },
      ),
    [selected],
  );
  const recommendations = useAsyncResource(selected ? fetchFindings : null, retry);
  const findings = recommendations.data?.recommendations ?? [];
  const loading = registry.loading || recommendations.loading;
  const error = registry.error || recommendations.error;
  return (
    <div className="ws-page">
      <header className="editorial-heading">
        <p className="eyebrow">INTELLIGENCE / INSIGHTS</p>
        <h1 className="ws-page-heading">Turn findings into next steps.</h1>
        <p className="ws-page-sub">
          Explore data-quality recommendations for your selected dataset.
        </p>
      </header>
      <label htmlFor="insights-dataset">Dataset</label>
      <select
        id="insights-dataset"
        className="reports-select"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
      >
        <option value="">Select a dataset</option>
        {datasets.map((ds) => (
          <option key={ds.dataset_id} value={ds.dataset_id}>
            {ds.name}
          </option>
        ))}
      </select>
      {!loading && !error && selected && (
        <div className="metric-strip">
          <div className="metric-tile metric-tile--lime">
            <span>Returned recommendations</span>
            <strong>{findings.length}</strong>
            <small>Selected dataset only</small>
          </div>
          <div className="metric-tile">
            <span>Fields mentioned</span>
            <strong>
              {new Set(findings.flatMap((f) => (f.column_name ? [f.column_name] : []))).size}
            </strong>
            <small>Distinct fields in these findings</small>
          </div>
          <div className="metric-tile">
            <span>Explore the evidence</span>
            <p>Review each suggested action alongside the source data.</p>
            <Link to={'/datasets/' + encodeURIComponent(selected)}>Inspect dataset →</Link>
          </div>
        </div>
      )}
      {error ? (
        <div role="alert" className="ws-empty">
          <p>{error}</p>
          <button className="reports-btn-secondary" onClick={() => setRetry((n) => n + 1)}>
            Try again
          </button>
        </div>
      ) : loading ? (
        <p role="status" className="ws-empty">
          Loading dataset insights…
        </p>
      ) : !datasets.length ? (
        <div className="ws-empty">
          <h2>No datasets uploaded yet.</h2>
          <Link to="/datasets/upload">Upload dataset</Link>
        </div>
      ) : !findings.length ? (
        <div className="ws-empty">
          <h2>No recommendations returned</h2>
          <p>Ask a question in Analytics to explore this dataset further.</p>
        </div>
      ) : (
        <div className="insights-cards-grid">
          {findings.map((f) => (
            <article className="ws-section-card" key={f.recommendation_id} style={{ padding: 20 }}>
              <p className="ws-page-sub">
                {f.severity}
                {f.column_name ? ' · ' + f.column_name : ''}
              </p>
              <h2 className="ws-section-card-title">{f.description}</h2>
              <p>{f.suggested_action}</p>
            </article>
          ))}
        </div>
      )}
      {selected && (
        <Link
          className="reports-create-btn"
          to={'/analysis?datasetId=' + encodeURIComponent(selected)}
        >
          Analyze selected dataset
        </Link>
      )}
      <p className="ws-page-sub">
        Business conclusions and forecasts require a completed analysis.
      </p>
    </div>
  );
}
