import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Play, TrendingUp } from 'lucide-react';
import { apiClient } from '../../api/client';
import { downloadWorkbenchJson, forecastSeries, workbenchService } from '../../services/workbenchService';
import type { ForecastResult, SourceDataset, SourcePreview } from '../../services/workbenchService';

export default function ForecastingWorkbenchPage() {
  const [datasets, setDatasets] = useState<SourceDataset[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [preview, setPreview] = useState<SourcePreview | null>(null);
  const [dateColumn, setDateColumn] = useState('');
  const [valueColumn, setValueColumn] = useState('');
  const [model, setModel] = useState('prophet');
  const [frequency, setFrequency] = useState('monthly');
  const [horizon, setHorizon] = useState(12);
  const [confidence, setConfidence] = useState(95);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [history, setHistory] = useState<{ date: string; value: number }[]>([]);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    workbenchService.datasets().then(data => { if (active) setDatasets(data); })
      .catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [revision]);
  async function selectDataset(id: string) {
    setDatasetId(id); setPreview(null); setResult(null); setError(''); setBusy(true);
    try {
      const data = await workbenchService.preview(id);
      setPreview(data); setDateColumn(data.columns.find(c => /date|time/i.test(c)) ?? '');
      setValueColumn(data.columns.find(c => data.rows.some(row => typeof row[c] === 'number')) ?? '');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load dataset.'); }
    finally { setBusy(false); }
  }
  async function run() {
    if (!preview) return;
    setBusy(true); setError(''); setResult(null);
    try {
      const series = forecastSeries(preview.rows, dateColumn, valueColumn);
      const output = await apiClient.post<ForecastResult>(`/api/v1/forecasting/${model}`, {
        series, frequency, horizon, confidence_level: confidence / 100, target: valueColumn,
      }, { timeout: 120000 });
      if (!output.forecast?.length || output.dates.length !== output.forecast.length ||
        output.lower_bound.length !== output.forecast.length || output.upper_bound.length !== output.forecast.length ||
        output.dates.some(date => !Number.isFinite(Date.parse(date))) ||
        [...output.forecast, ...output.lower_bound, ...output.upper_bound].some(v => !Number.isFinite(v))) throw new Error('The forecasting service returned incomplete or invalid results.');
      setHistory(series);
      setResult(output);
    } catch (e) { setError(e instanceof Error ? e.message : 'Forecast failed.'); }
    finally { setBusy(false); }
  }
  return <div className="page-container">
    <div className="page-header editorial-heading"><div><p className="eyebrow">ANALYTICS / FORECASTING</p><div>
      <h1 className="page-title">Forecasting workbench</h1><p className="page-subtitle">Explore predictions from your dataset’s preview records.</p>
    </div></div></div>
    {error && <div role="alert" className="mem-panel"><p>{error}</p><button className="btn btn--ghost" onClick={() => { setBusy(true); setError(''); setRevision(v => v + 1); }}>Retry dataset connection</button></div>}
    <div className="fw-layout"><fieldset className="fw-config" disabled={busy} style={{ margin: 0, minWidth: 0 }}>
      <legend>Forecast configuration</legend>
      <label className="fw-param">Dataset<select className="fw-select" value={datasetId} onChange={e => void selectDataset(e.target.value)}>
        <option value="" disabled>Select an uploaded dataset</option>{datasets.map(d => <option value={d.dataset_id} key={d.dataset_id}>{d.dataset_name}</option>)}
      </select></label>
      {!busy && !datasets.length && !error && <p>No datasets uploaded yet. <Link to="/datasets">Upload a dataset</Link></p>}
      {preview && <p className="page-subtitle">Using {preview.rows.length.toLocaleString()} preview rows of {(preview.total_rows == null ? 'unknown total' : preview.total_rows.toLocaleString())}. Results apply only to this sample.</p>}
      <label className="fw-param">Date column<select className="fw-select" value={dateColumn} onChange={e => setDateColumn(e.target.value)}><option value="">Select date column</option>{preview?.columns.map(c => <option key={c}>{c}</option>)}</select></label>
      <label className="fw-param">Numeric target<select className="fw-select" value={valueColumn} onChange={e => setValueColumn(e.target.value)}><option value="">Select target</option>{preview?.columns.map(c => <option key={c}>{c}</option>)}</select></label>
      <label className="fw-param">Model<select className="fw-select" value={model} onChange={e => setModel(e.target.value)}><option value="prophet">Prophet</option><option value="arima">ARIMA</option><option value="xgboost">XGBoost</option></select></label>
      <label className="fw-param">Observation frequency<select className="fw-select" value={frequency} onChange={e => setFrequency(e.target.value)}>{['daily', 'weekly', 'monthly'].map(f => <option key={f}>{f}</option>)}</select></label>
      <label className="fw-param">Forecast periods<input className="fw-select" type="number" min={1} max={365} value={horizon} onChange={e => setHorizon(Number(e.target.value))} /></label>
      <label className="fw-param">Prediction interval (%)<input className="fw-select" type="number" min={50} max={99} value={confidence} onChange={e => setConfidence(Number(e.target.value))} /></label>
      <button className="btn btn--primary" disabled={!preview?.rows.length || !dateColumn || !valueColumn || horizon < 1 || horizon > 365 || confidence < 50 || confidence > 99} onClick={() => void run()}><Play size={15} /> Run forecast</button>
    </fieldset><div className="fw-main" aria-busy={busy}>
      {busy && <p role="status">Waiting for the dataset or forecasting service…</p>}
      {!busy && !result && <div className="fw-empty"><TrendingUp size={32} /><h2>Build a forecast from real observations</h2><p>Select date and numeric columns, confirm the observation frequency, then run a model. Accuracy scores are unavailable without a separate held-out backtest.</p></div>}
      {result && <section className="fw-chart-card"><h2>{result.target} forecast</h2><p>{result.model_type} · {result.horizon} {result.frequency} periods · {result.confidence_level * 100}% prediction interval</p><p className="page-subtitle">Generated {new Date(result.generated_at).toLocaleString()} from preview data. Predictions are estimates, not guarantees.</p>
        <ForecastChart result={result} history={history} />
        <p className="chart-scope">Solid line: observed preview values. Dashed line: model forecast. Shading: returned prediction interval.</p>
        <details><summary>Historical observations used by this forecast</summary><div className="studio-values"><table><caption>Preview observations in source units</caption><thead><tr><th scope="col">Date</th><th scope="col">Observed value</th></tr></thead><tbody>{history.map(point => <tr key={point.date}><td>{point.date}</td><td>{point.value.toLocaleString()}</td></tr>)}</tbody></table></div></details>
        <button className="btn btn--ghost" onClick={() => downloadWorkbenchJson({ dataset_id: datasetId, sample_rows: preview?.rows.length, result }, 'forecast.json')}><Download size={15} /> Download results</button>
        <div className="fw-metrics-table-wrap"><table className="fw-metrics-table"><caption>Forecast values and prediction bounds</caption><thead><tr><th>Date</th><th>Forecast</th><th>Lower bound</th><th>Upper bound</th></tr></thead><tbody>{result.dates.map((date, i) => <tr key={`${date}-${i}`}><td>{date}</td><td>{result.forecast[i].toLocaleString()}</td><td>{result.lower_bound[i].toLocaleString()}</td><td>{result.upper_bound[i].toLocaleString()}</td></tr>)}</tbody></table></div>
      </section>}
    </div></div>
  </div>;
}
function ForecastChart({ result, history }: { result: ForecastResult; history: { date: string; value: number }[] }) {
  const min = Math.min(...result.lower_bound, ...result.forecast, ...history.map(point => point.value));
  const max = Math.max(...result.upper_bound, ...result.forecast, ...history.map(point => point.value));
  const range = max - min || Math.max(Math.abs(max) * .1, 1);
  const timestamps = [...history.map(point => Date.parse(point.date)), ...result.dates.map(date => Date.parse(date))];
  const first = Math.min(...timestamps); const last = Math.max(...timestamps);
  const atDate = (date: string) => 70 + (Date.parse(date) - first) / (last - first || 1) * 620;
  const x = (i: number) => atDate(result.dates[i]);
  const y = (v: number) => 220 - (v - min) / range * 180;
  const path = result.forecast.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join(' ');
  const observed = history.map((point, i) => `${i ? 'L' : 'M'}${atDate(point.date)},${y(point.value)}`).join(' ');
  const interval = [...result.upper_bound.map((v, i) => `${x(i)},${y(v)}`), ...result.lower_bound.map((v, i) => `${x(i)},${y(v)}`).reverse()].join(' ');
  return <svg viewBox="0 0 740 280" role="img" aria-label={`${result.target} forecast. Exact values and prediction bounds follow in the table.`} style={{ width: '100%' }}>
    {[0, .5, 1].map(f => <g key={f}><line x1={70} x2={690} y1={220 - f * 180} y2={220 - f * 180} stroke="currentColor" opacity={.15} /><text x={62} y={224 - f * 180} textAnchor="end" fill="currentColor" fontSize={10}>{(min + f * range).toLocaleString(undefined, { maximumFractionDigits: 1, notation: 'compact' })}</text></g>)}
    <polygon points={interval} fill="var(--chart-1)" opacity={.2}><title>{result.confidence_level * 100}% prediction interval</title></polygon>
    <path d={observed} stroke="var(--text-h)" strokeWidth={2} fill="none" />
    <path d={path} stroke="var(--accent)" strokeWidth={2} strokeDasharray="5 4" fill="none" />{result.forecast.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={3} fill="var(--accent)"><title>{result.dates[i]}: {v}</title></circle>)}
    <text x={70} y={250} fill="currentColor" fontSize={11}>{new Date(first).toISOString().slice(0, 10)}</text><text x={690} y={250} textAnchor="end" fill="currentColor" fontSize={11}>{new Date(last).toISOString().slice(0, 10)}</text>
  </svg>;
}
