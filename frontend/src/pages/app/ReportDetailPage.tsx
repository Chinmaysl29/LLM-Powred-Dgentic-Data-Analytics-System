import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getStoredReports, downloadStoredReport } from '../../services/reportsService';
import type { StoredReport } from '../../services/reportsService';
export default function ReportDetailPage() {
 const params = useParams(); const id = params.reportId || params.id; const [report, setReport] = useState<StoredReport | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [retry, setRetry] = useState(0);
 useEffect(() => { let active = true; setLoading(true); setError(''); getStoredReports().then(rows => { if (active) setReport(rows.find(r => r.id === id) ?? null); }).catch(err => { if (active) setError(err instanceof Error ? err.message : 'Unable to load report.'); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [id, retry]);
 return <div className="ws-page"><Link to="/reports">Back to reports</Link><h1 className="ws-page-heading">{report?.title || 'Report record'}</h1>{loading ? <p role="status">Loading report…</p> : error ? <div role="alert"><p>{error}</p><button onClick={() => setRetry(n => n + 1)}>Try again</button></div> : !report ? <p>Report not found.</p> : <><p className="ws-page-sub">Legacy report content. Source dataset identifiers are not included in this API; business statements and template text are not verified findings.</p><button className="reports-btn-secondary" onClick={() => downloadStoredReport(report)}>Download stored JSON</button><pre className="ws-section-card" style={{ padding: 24, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{report.markdown || report.summary || 'No report content was returned.'}</pre></>}</div>;
}
