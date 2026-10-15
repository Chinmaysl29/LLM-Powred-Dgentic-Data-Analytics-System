/**
 * EDAStudioPage.tsx
 *
 * Phase 23 — EDA Visualization Studio
 * Premium Power BI-inspired analytics canvas built on real backend data.
 *
 * Architecture:
 * - Fetches EDA results from GET /api/v1/eda/{dataset_id}
 * - Renders 15 analytical cards (including the KPI banner), subject to data availability
 * - Asymmetric 12-column CSS bento grid, alternating dark/light surfaces
 * - Lime accent (#D6FA43) highlights key metrics only
 * - No fake statistics, no placeholder charts
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  CheckCircle2,
  ArrowUpRight,
  RefreshCw,
  Download,
  Activity,
  Target,
  Layers,
  XCircle,
} from 'lucide-react';
import { datasetService } from '../../services/datasetService';
import { edaService } from '../../services/edaService';
import type { Dataset } from '../../types/datasets';
import type {
  EDAResults,
  NumericColumnStatistics,
  CategoryDetail,
  TrendPattern,
  ColumnOutliers,
  BusinessInsight,
} from '../../types/eda';
import '../../styles/eda-studio.css';
import { EDAChartCoordinates } from './EDAChartCoordinates';

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  });
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return n.toFixed(1) + '%';
}

function shortLabel(s: string, max = 14): string {
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}

// Correlation color: diverging red (–1) → white (0) → green (+1)
function corrColor(r: number): string {
  const v = Math.max(-1, Math.min(1, r));
  if (v >= 0) {
    const g = Math.round(40 + v * 140);
    const a = (0.15 + v * 0.75).toFixed(2);
    return `rgba(110,${g + 60},130,${a})`;
  }
  const rr = Math.round(180 + Math.abs(v) * 75);
  const a = (0.15 + Math.abs(v) * 0.75).toFixed(2);
  return `rgba(${rr},80,80,${a})`;
}

function trendIcon(t: TrendPattern['trend_type']) {
  if (t === 'growth') return <TrendingUp size={14} />;
  if (t === 'decline') return <TrendingDown size={14} />;
  return <Minus size={14} />;
}

// ---------------------------------------------------------------------------
// Skeleton loader card
// ---------------------------------------------------------------------------
function SkeletonCard({ span = 'eda-span-4' }: { span?: string }) {
  return (
    <div className={`eda-card ${span}`} aria-hidden="true">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <div className="eda-skeleton eda-skeleton-h12 eda-skeleton-w60" style={{ marginBottom: 6 }} />
          <div className="eda-skeleton eda-skeleton-h20 eda-skeleton-w80" />
        </div>
      </div>
      <div className="eda-card-body">
        <div className="eda-skeleton eda-skeleton-h80 eda-skeleton-w100" style={{ borderRadius: 6 }} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 01 — Dataset Overview
// ---------------------------------------------------------------------------
function Card01Overview({
  results,
  datasetName,
}: {
  results: EDAResults;
  datasetName: string;
}) {
  const s = results.dataset_summary;
  return (
    <div className="eda-card eda-span-4">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">01 / DATASET OVERVIEW</p>
          <h2 className="eda-card-title">Your data, at a glance.</h2>
          <p className="eda-card-desc" title={datasetName}>{shortLabel(datasetName, 28)}</p>
        </div>
        <span className="eda-card-badge">{s.dataset_type.toUpperCase()}</span>
      </div>
      <div className="eda-stat-grid">
        <div className="eda-stat-cell">
          <span className="eda-stat-value">{s.row_count.toLocaleString()}</span>
          <span className="eda-stat-label">Rows</span>
        </div>
        <div className="eda-stat-cell">
          <span className="eda-stat-value">{s.column_count}</span>
          <span className="eda-stat-label">Columns</span>
        </div>
        <div className="eda-stat-cell">
          <span className="eda-stat-value">{fmt(s.memory_usage_mb, 1)}</span>
          <span className="eda-stat-label">MB Memory</span>
        </div>
      </div>
      <div className="eda-section-divider" />
      <div className="eda-card-body">
        <div className="eda-pill-list">
          {s.numeric_columns.slice(0, 4).map(c => (
            <span key={c} className="eda-pill">{c}</span>
          ))}
          {s.categorical_columns.slice(0, 3).map(c => (
            <span key={c} className="eda-pill eda-pill-lime">{c}</span>
          ))}
          {s.numeric_columns.length + s.categorical_columns.length > 7 && (
            <span className="eda-pill">+{s.numeric_columns.length + s.categorical_columns.length - 7} more</span>
          )}
        </div>
        {s.is_sampled && (
          <p style={{ fontSize: 10, color: '#f59e0b', marginTop: 8 }}>
            EDA performed on an adaptive sample; statistics describe the sampled rows.
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 02 — Data Quality
// ---------------------------------------------------------------------------
function Card02Quality({ results }: { results: EDAResults }) {
  const mv = results.missing_values;
  const totalCols = results.dataset_summary.column_count;
  const completeness = results.dataset_summary.row_count > 0 && totalCols > 0
    ? 100 - mv.missing_percentage : null;
  const completeColumns = totalCols > 0 && results.dataset_summary.row_count > 0
    ? ((totalCols - mv.affected_columns_count) / totalCols) * 100 : null;
  const metrics = [
    { name: 'Non-missing cells', value: completeness },
    { name: 'Columns without missing values', value: completeColumns },
  ];

  return (
    <div className="eda-card-light eda-span-4">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">02 / DATA QUALITY</p>
          <h2 className="eda-card-title">Check the foundations.</h2>
        </div>
        <CheckCircle2 size={16} color={completeness != null && completeness >= 90 ? '#6ee7b7' : '#f59e0b'} />
      </div>
      <div className="eda-card-body">
        <div className="eda-quality-row">
          {metrics.map(m => {
            const cls = m.value != null && m.value >= 90 ? '' : m.value != null && m.value >= 70 ? 'eda-quality-fill-warn' : 'eda-quality-fill-err';
            return (
              <div key={m.name} className="eda-quality-item">
                <div className="eda-quality-label-row">
                  <span className="eda-quality-name">{m.name}</span>
                  <span className="eda-quality-score">{fmtPct(m.value)}</span>
                </div>
                <div className="eda-quality-track">
                  <div
                    className={`eda-quality-fill ${cls}`}
                    style={{ width: `${Math.max(0, Math.min(100, m.value ?? 0))}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <p style={{ fontSize: 10, color: '#5A6A6A', marginTop: 12, lineHeight: 1.5 }}>
          {mv.affected_columns_count} of {totalCols} columns have missing values.
          {mv.total_missing_cells > 0 && ` Total: ${mv.total_missing_cells.toLocaleString()} empty cells.`}
          Uniqueness and validity are not measured by this analysis.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 03 — Distribution summary and quartile range widths
// ---------------------------------------------------------------------------
function Card03Distribution({ results }: { results: EDAResults }) {
  const numCols = Object.keys(results.statistics);
  const [col, setCol] = useState(numCols[0] ?? '');
  const stat = col ? results.statistics[col] : null;
  const dist = col ? results.distributions[col] : null;

  // Show value-range widths; quartiles do not provide histogram frequencies.
  const bars = useMemo(() => {
    if (!stat) return [];
    const { min, max, q25, median, q75 } = stat;
    const range = max - min || 1;
    // Each bar is a percentage of the observed numeric range.
    const bins = [
      { label: 'Min→Q25', value: ((q25 - min) / range) * 100, fill: '#2A3838' },
      { label: 'Q25→Med', value: ((median - q25) / range) * 100, fill: '#3A4848' },
      { label: 'Med→Q75', value: ((q75 - median) / range) * 100, fill: '#D6FA43' },
      { label: 'Q75→Max', value: ((max - q75) / range) * 100, fill: '#2A3838' },
    ];
    return bins;
  }, [stat]);

  if (!numCols.length) return null;

  return (
    <div className="eda-card eda-span-4">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">03 / DISTRIBUTION</p>
          <h2 className="eda-card-title">Know the shape.</h2>
        </div>
      </div>
      <div className="eda-card-body">
        <select
          className="eda-dist-select"
          value={col}
          onChange={e => setCol(e.target.value)}
          aria-label="Select column for distribution"
        >
          {numCols.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        {stat && (
          <>
            <p className="eda-card-desc">Quartile interval widths (% of value range), not observation frequencies.</p>
            {/* Quartile range widths */}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 80, marginBottom: 8 }}>
              {bars.map((b, i) => (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, height: '100%', justifyContent: 'flex-end' }}>
                  <div
                    style={{
                      width: '100%',
                      height: `${b.value}%`,
                      background: b.fill,
                      borderRadius: '3px 3px 0 0',
                      transition: 'height 0.4s ease',
                    }}
                    title={`${b.label}: ${b.value.toFixed(1)}% of range`}
                  />
                  <span style={{ fontSize: 8, color: '#4A5A5A', textAlign: 'center', lineHeight: 1.2 }}>{b.label}</span>
                </div>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px', fontSize: 10 }}>
              {[
                ['Mean', fmt(stat.mean)],
                ['Median', fmt(stat.median)],
                ['Std Dev', fmt(stat.std)],
                ['Skewness', dist ? fmt(dist.skewness, 3) : '—'],
                ['Min', fmt(stat.min)],
                ['Max', fmt(stat.max)],
              ].map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #1A2020', paddingBottom: 3 }}>
                  <span style={{ color: '#5A6A6A' }}>{k}</span>
                  <span style={{ color: '#AEB5AF', fontVariantNumeric: 'tabular-nums', fontFamily: 'ui-monospace, monospace' }}>{v}</span>
                </div>
              ))}
            </div>
            {dist && (
              <p style={{ fontSize: 9, color: '#5A6A6A', marginTop: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                {dist.distribution_type} · {dist.is_symmetric ? 'symmetric' : 'asymmetric'}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 04 — Box Plot (IQR visualization)
// ---------------------------------------------------------------------------
function Card04BoxPlot({ results }: { results: EDAResults }) {
  const numCols = Object.keys(results.statistics);
  const [col, setCol] = useState(numCols[0] ?? '');
  const stat = col ? results.statistics[col] : null;

  if (!numCols.length) return null;

  return (
    <div className="eda-card eda-span-3">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">04 / BOX PLOT</p>
          <h2 className="eda-card-title">Spread & quartiles.</h2>
        </div>
      </div>
      <div className="eda-card-body">
        <select
          className="eda-dist-select"
          value={col}
          onChange={e => setCol(e.target.value)}
          aria-label="Select column for box plot"
        >
          {numCols.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        {stat && (() => {
          const { min, max, q25, median, q75 } = stat;
          const range = max - min || 1;
          const pct = (v: number) => ((v - min) / range) * 100;

          return (
            <div>
              <svg viewBox="0 0 240 80" className="eda-chart-svg" role="img" aria-label={`Box plot for ${col}`}>
                <title>{`${col} box plot: min=${fmt(min)}, Q25=${fmt(q25)}, median=${fmt(median)}, Q75=${fmt(q75)}, max=${fmt(max)}`}</title>
                {/* Whisker line */}
                <line x1={10 + pct(min) / 100 * 220} x2={10 + pct(max) / 100 * 220}
                  y1="40" y2="40" stroke="#3A4848" strokeWidth="1.5" />
                {/* IQR box */}
                <rect
                  x={10 + pct(q25) / 100 * 220}
                  y="26"
                  width={(pct(q75) - pct(q25)) / 100 * 220}
                  height="28"
                  fill="#2A3838"
                  stroke="#3A5050"
                  strokeWidth="1"
                  rx="2"
                />
                {/* Median line */}
                <line
                  x1={10 + pct(median) / 100 * 220}
                  x2={10 + pct(median) / 100 * 220}
                  y1="26" y2="54"
                  stroke="#D6FA43"
                  strokeWidth="2"
                />
                {/* Min whisker */}
                <line x1={10 + pct(min) / 100 * 220} x2={10 + pct(min) / 100 * 220}
                  y1="33" y2="47" stroke="#3A4848" strokeWidth="1.5" />
                {/* Max whisker */}
                <line x1={10 + pct(max) / 100 * 220} x2={10 + pct(max) / 100 * 220}
                  y1="33" y2="47" stroke="#3A4848" strokeWidth="1.5" />
                {/* Labels */}
                <text x={10 + pct(min) / 100 * 220} y="72" textAnchor="middle" fontSize="8" fill="#5A6A6A">{fmt(min, 0)}</text>
                <text x={10 + pct(median) / 100 * 220} y="16" textAnchor="middle" fontSize="8" fill="#D6FA43">{fmt(median)}</text>
                <text x={10 + pct(max) / 100 * 220} y="72" textAnchor="middle" fontSize="8" fill="#5A6A6A">{fmt(max, 0)}</text>
              </svg>
              <p style={{ fontSize: 9, color: '#3A4A4A', textAlign: 'center', marginTop: 4 }}>
                IQR: {fmt(q75 - q25)} · Median highlighted in lime
              </p>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 05 — Correlation Heatmap
// ---------------------------------------------------------------------------
function Card05Correlation({ results }: { results: EDAResults }) {
  const matrix = results.correlations.correlation_matrix;
  const cols = Object.keys(matrix).slice(0, 7);

  if (!cols.length) return null;

  return (
    <div className="eda-card eda-span-5">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">05 / CORRELATION ANALYSIS</p>
          <h2 className="eda-card-title">How variables relate.</h2>
        </div>
        <span className="eda-card-badge">PEARSON</span>
      </div>
      <div className="eda-heatmap-wrap">
        <table className="eda-heatmap-table" role="grid" aria-label="Correlation matrix">
          <thead>
            <tr>
              <th />
              {cols.map(c => (
                <th key={c} title={c}>{shortLabel(c, 8)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cols.map(row => (
              <tr key={row}>
                <th style={{ textAlign: 'right', paddingRight: 6 }}>{shortLabel(row, 8)}</th>
                {cols.map(colKey => {
                  const r = matrix[row]?.[colKey] ?? 0;
                  return (
                    <td
                      key={colKey}
                      style={{ background: corrColor(r), color: Math.abs(r) > 0.4 ? '#F4F5F0' : '#5A6A6A' }}
                      title={`${row} × ${colKey}: ${r.toFixed(3)}`}
                    >
                      {r.toFixed(2)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {results.correlations.strongest_correlations.length > 0 && (
        <div className="eda-card-body" style={{ paddingTop: 4 }}>
          <p style={{ fontSize: 9, color: '#5A6A6A', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
            Strongest pairs
          </p>
          {results.correlations.strongest_correlations.slice(0, 3).map((p, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, padding: '3px 0', borderBottom: '1px solid #1A2020' }}>
              <span style={{ color: '#7A8A8A' }}>{shortLabel(p.column_a, 10)} × {shortLabel(p.column_b, 10)}</span>
              <span style={{
                color: p.correlation > 0 ? '#6ee7b7' : '#f87171',
                fontWeight: 700,
                fontFamily: 'ui-monospace, monospace',
              }}>
                {p.correlation.toFixed(3)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 06 — Time-Series Trend
// ---------------------------------------------------------------------------
function Card06Trend({ results }: { results: EDAResults }) {
  const trends = results.trends;
  if (!trends.has_time_series || !trends.trends.length) return null;

  return (
    <div className="eda-card eda-span-6">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">06 / TREND ANALYSIS</p>
          <h2 className="eda-card-title">See what changed.</h2>
          <p className="eda-card-desc">Date columns: {trends.date_columns.join(', ')}</p>
        </div>
      </div>
      <div className="eda-card-body">
        <div className="eda-trend-row">
          {trends.trends.slice(0, 4).map((t, i) => (
            <div key={i} className="eda-trend-item">
              <div className={`eda-trend-dir ${t.trend_type}`}>
                {trendIcon(t.trend_type)}
              </div>
              <div className="eda-trend-meta">
                <p className="eda-trend-col">{t.metric_column}</p>
                <p className="eda-trend-desc">{t.description}</p>
                {t.seasonality_detected && (
                  <span style={{ fontSize: 9, color: '#D6FA43', fontWeight: 600, letterSpacing: '0.08em' }}>SEASONALITY DETECTED</span>
                )}
              </div>
              <span className="eda-trend-rate">{t.growth_rate_pct >= 0 ? '+' : ''}{fmtPct(t.growth_rate_pct)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 07 — Category Comparison
// ---------------------------------------------------------------------------
function Card07Categories({ results }: { results: EDAResults }) {
  const cats = results.categorical_analysis;
  const catKeys = Object.keys(cats);
  const [col, setCol] = useState(catKeys[0] ?? '');
  const detail: CategoryDetail | undefined = col ? cats[col] : undefined;

  if (!catKeys.length) return null;

  const topEntries = detail
    ? Object.entries(detail.top_categories)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
    : [];
  const maxVal = topEntries[0]?.[1] ?? 1;

  return (
    <div className="eda-card-light eda-span-6">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">07 / CATEGORY COMPARISON</p>
          <h2 className="eda-card-title">Top categories.</h2>
        </div>
      </div>
      <div className="eda-card-body">
        <select
          className="eda-dist-select"
          value={col}
          onChange={e => setCol(e.target.value)}
          aria-label="Select categorical column"
          style={{ background: '#E8E8E0', borderColor: '#D0D0C8', color: '#374151' }}
        >
          {catKeys.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        {detail && (
          <>
            <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10, color: '#9CA3AF' }}>{detail.unique_count} unique values</span>
              <span style={{ fontSize: 10, color: '#9CA3AF', textTransform: 'capitalize' }}>
                {detail.cardinality_level} cardinality
              </span>
            </div>
            <div className="eda-bar-rows">
              {topEntries.map(([label, count]) => (
                <div key={label} className="eda-bar-row">
                  <span className="eda-bar-label" title={label}>{shortLabel(label)}</span>
                  <div className="eda-bar-track">
                    <div
                      className="eda-bar-fill"
                      style={{ width: `${(count / maxVal) * 100}%`, background: '#374151' }}
                    />
                  </div>
                  <span className="eda-bar-value">{count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 08 — Pairwise summary (no observation coordinates)
// ---------------------------------------------------------------------------
function Card08Scatter({ results }: { results: EDAResults }) {
  const numCols = Object.keys(results.statistics);
  const [xCol, setXCol] = useState(numCols[0] ?? '');
  const [yCol, setYCol] = useState(numCols[1] ?? numCols[0] ?? '');

  const xStat = results.statistics[xCol];
  const yStat = results.statistics[yCol];

  if (numCols.length < 2) return null;

  // We don't have raw row data here — show statistical summary as proxy
  const corrVal = xCol !== yCol
    ? (results.correlations.correlation_matrix[xCol]?.[yCol] ?? null)
    : null;

  return (
    <div className="eda-card eda-span-4">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">08 / PAIR SUMMARY</p>
          <h2 className="eda-card-title">Two-variable relationship.</h2>
          <p className="eda-card-desc">Correlation and ranges; paired observations are not available in this summary.</p>
        </div>
      </div>
      <div className="eda-card-body">
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          <select
            className="eda-dist-select"
            value={xCol}
            onChange={e => setXCol(e.target.value)}
            aria-label="X axis column"
            style={{ flex: 1, minWidth: 0 }}
          >
            {numCols.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            className="eda-dist-select"
            value={yCol}
            onChange={e => setYCol(e.target.value)}
            aria-label="Y axis column"
            style={{ flex: 1, minWidth: 0 }}
          >
            {numCols.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {corrVal != null && (
          <div style={{ padding: '12px', background: '#0e1111', borderRadius: 6, marginBottom: 10, textAlign: 'center' }}>
            <span style={{ fontSize: 28, fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: corrVal > 0 ? '#6ee7b7' : corrVal < -0.3 ? '#f87171' : '#D6FA43' }}>
              {corrVal.toFixed(3)}
            </span>
            <p style={{ fontSize: 10, color: '#5A6A6A', marginTop: 4 }}>Pearson correlation</p>
          </div>
        )}

        {xStat && yStat && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { label: xCol, stat: xStat },
              { label: yCol, stat: yStat },
            ].map(({ label, stat }, index) => (
              <div key={`${index}-${label}`} style={{ background: '#0e1111', borderRadius: 6, padding: 10 }}>
                <p style={{ fontSize: 9, color: '#5A6A6A', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>{shortLabel(label, 10)}</p>
                <p style={{ fontSize: 11, color: '#AEB5AF', fontFamily: 'ui-monospace, monospace' }}>
                  {fmt(stat.min, 0)} → {fmt(stat.max, 0)}
                </p>
                <p style={{ fontSize: 10, color: '#6A7A7A' }}>μ={fmt(stat.mean)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 09 — Missing Values Matrix
// ---------------------------------------------------------------------------
function Card09Missing({ results }: { results: EDAResults }) {
  const mv = results.missing_values;
  const affectedCols = mv.affected_columns.slice(0, 12);

  return (
    <div className="eda-card eda-span-4">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">09 / MISSING VALUES</p>
          <h2 className="eda-card-title">Missingness patterns.</h2>
        </div>
        <span className="eda-card-badge" style={{ color: mv.affected_columns_count > 0 ? '#f59e0b' : '#D6FA43', background: mv.affected_columns_count > 0 ? 'rgba(245,158,11,0.1)' : 'rgba(214,250,67,0.1)' }}>
          {mv.affected_columns_count} COLS
        </span>
      </div>
      <div className="eda-card-body">
        {affectedCols.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#6ee7b7', fontSize: 12 }}>
            <CheckCircle2 size={14} />
            <span>No missing values detected.</span>
          </div>
        ) : (
          <div className="eda-missing-list">
            {affectedCols.map(colName => {
              const detail = mv.column_details[colName];
              const pct = detail?.missing_percentage ?? 0;
              return (
                <div key={colName} className="eda-missing-row">
                  <span className="eda-missing-col-name" title={colName}>{shortLabel(colName, 16)}</span>
                  <div className="eda-missing-bar-track">
                    <div className="eda-missing-bar-fill" style={{ width: `${Math.min(100, pct)}%` }} />
                  </div>
                  <span className="eda-missing-pct">{fmtPct(pct)}</span>
                </div>
              );
            })}
          </div>
        )}
        <p style={{ fontSize: 10, color: '#3A4A4A', marginTop: 10 }}>
          Overall: {fmtPct(mv.missing_percentage)} cells missing across dataset.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 10 — Statistical Summary Table
// ---------------------------------------------------------------------------
function Card10Stats({ results }: { results: EDAResults }) {
  const statEntries = Object.entries(results.statistics).slice(0, 8);
  if (!statEntries.length) return null;

  return (
    <div className="eda-card eda-span-8">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">10 / STATISTICAL SUMMARY</p>
          <h2 className="eda-card-title">Mean, median, variance and percentiles.</h2>
        </div>
      </div>
      <div className="eda-table-wrap">
        <table className="eda-table" aria-label="Statistical summary">
          <thead>
            <tr>
              <th>Column</th>
              <th>Count</th>
              <th>Mean</th>
              <th>Median</th>
              <th>Std Dev</th>
              <th>Min</th>
              <th>Q25</th>
              <th>Q75</th>
              <th>Max</th>
            </tr>
          </thead>
          <tbody>
            {statEntries.map(([col, s]: [string, NumericColumnStatistics]) => (
              <tr key={col}>
                <td style={{ fontWeight: 600, color: '#F4F5F0', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }} title={col}>{col}</td>
                <td>{s.count.toLocaleString()}</td>
                <td className="lime">{fmt(s.mean)}</td>
                <td>{fmt(s.median)}</td>
                <td>±{fmt(s.std)}</td>
                <td>{fmt(s.min)}</td>
                <td>{fmt(s.q25)}</td>
                <td>{fmt(s.q75)}</td>
                <td>{fmt(s.max)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="eda-chart-caption">
        Showing {statEntries.length} of {Object.keys(results.statistics).length} numeric columns. Values computed by backend analytics pipeline.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 11 — Anomaly Detection
// ---------------------------------------------------------------------------
function Card11Anomaly({ results }: { results: EDAResults }) {
  const outlierEntries = Object.entries(results.outliers).slice(0, 6);
  const defaultCol = outlierEntries[0]?.[0] ?? '';
  const [col, setCol] = useState(defaultCol);

  if (!outlierEntries.length) return null;

  const activeCol = results.outliers[col] ? col : defaultCol;
  const detail: ColumnOutliers | undefined = results.outliers[activeCol];

  return (
    <div className="eda-card eda-span-4">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">11 / ANOMALY DETECTION</p>
          <h2 className="eda-card-title">Spot the exceptions.</h2>
        </div>
        <AlertTriangle size={14} color="#f59e0b" />
      </div>
      <div className="eda-card-body">
        <select
          className="eda-outlier-col-select"
          value={col}
          onChange={e => setCol(e.target.value)}
          aria-label="Select column for outlier detection"
        >
          {outlierEntries.map(([c]) => <option key={c} value={c}>{c}</option>)}
        </select>

        {detail && (
          <>
            <div className="eda-outlier-methods">
              {[detail.iqr, detail.z_score].map(m => (
                <div key={m.method} className="eda-outlier-method">
                  <p className="eda-outlier-method-name">{m.method}</p>
                  <p className="eda-outlier-count">{m.outlier_count.toLocaleString()}</p>
                  <p className="eda-outlier-pct">{fmtPct(m.outlier_percentage)} outliers</p>
                  {m.lower_bound != null && (
                    <p style={{ fontSize: 9, color: '#5A6A6A', marginTop: 4 }}>
                      [{fmt(m.lower_bound, 1)}, {fmt(m.upper_bound, 1)}]
                    </p>
                  )}
                </div>
              ))}
            </div>
            {detail.iqr.sample_outliers.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <p style={{ fontSize: 9, color: '#5A6A6A', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>Sample outlier values</p>
                <div className="eda-pill-list">
                  {detail.iqr.sample_outliers.slice(0, 6).map((v, i) => (
                    <span key={i} className="eda-pill" style={{ color: '#f59e0b', borderColor: 'rgba(245,158,11,0.2)', background: 'rgba(245,158,11,0.06)' }}>
                      {fmt(v)}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 12 — Composition (category distribution pie-ish)
// ---------------------------------------------------------------------------
function Card12Composition({ results }: { results: EDAResults }) {
  const cats = results.categorical_analysis;
  const catKeys = Object.keys(cats);
  const [col, setCol] = useState(catKeys[0] ?? '');
  const detail = col ? cats[col] : undefined;

  if (!catKeys.length) return null;

  const entries = detail
    ? Object.entries(detail.frequency_distribution)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
    : [];

  const COLORS = ['#D6FA43', '#14b8a6', '#3b82f6', '#f59e0b', '#a855f7', '#ec4899', '#6ee7b7', '#f87171'];

  return (
    <div className="eda-card eda-span-4">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">12 / COMPOSITION</p>
          <h2 className="eda-card-title">Category contributions.</h2>
        </div>
      </div>
      <div className="eda-card-body">
        <select
          className="eda-dist-select"
          value={col}
          onChange={e => setCol(e.target.value)}
          aria-label="Select category column"
        >
          {catKeys.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        {entries.length > 0 && (
          <div className="eda-bar-rows">
            {entries.map(([label, pct], i) => (
              <div key={label} className="eda-bar-row">
                <span className="eda-bar-label" title={label}>{shortLabel(label)}</span>
                <div className="eda-bar-track">
                  <div className="eda-bar-fill" style={{ width: `${pct}%`, background: COLORS[i % COLORS.length] }} />
                </div>
                <span className="eda-bar-value">{fmtPct(pct)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 13 — Pareto Analysis
// ---------------------------------------------------------------------------
function Card13Pareto({ results }: { results: EDAResults }) {
  const cats = results.categorical_analysis;
  const catKeys = Object.keys(cats).filter(k => cats[k].cardinality_level !== 'high');
  if (!catKeys.length) return null;

  const col = catKeys[0];
  const detail = cats[col];
  const entries = Object.entries(detail.top_categories).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const total = entries.reduce((s, [, v]) => s + v, 0);

  const withCumulative = entries.map(([label, count], idx) => {
    const cum = entries.slice(0, idx + 1).reduce((s, [, c]) => s + c, 0);
    return { label, count, cumPct: total > 0 ? (cum / total) * 100 : 0 };
  });

  return (
    <div className="eda-card-light eda-span-4">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">13 / PARETO ANALYSIS</p>
          <h2 className="eda-card-title">Cumulative contribution.</h2>
          <p className="eda-card-desc">{col}</p>
        </div>
      </div>
      <div className="eda-card-body">
        <div className="eda-bar-rows">
          {withCumulative.map(({ label, count, cumPct }) => (
            <div key={label} className="eda-bar-row">
              <span className="eda-bar-label" title={label}>{shortLabel(label)}</span>
              <div className="eda-bar-track">
                <div className="eda-bar-fill" style={{ width: `${(count / (total || 1)) * 100}%`, background: '#374151' }} />
              </div>
              <span className="eda-bar-value" style={{ color: '#101313', fontSize: 9 }}>{fmtPct(cumPct)}</span>
            </div>
          ))}
        </div>
        <p style={{ fontSize: 10, color: '#9CA3AF', marginTop: 10 }}>
          Percentages refer only to the displayed categories. Top {Math.ceil(entries.length * 0.2)} categories account for {fmtPct(withCumulative[Math.ceil(entries.length * 0.2) - 1]?.cumPct ?? 0)}.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 18 — EDA Findings (Business Insights)
// ---------------------------------------------------------------------------
function Card18Findings({ results }: { results: EDAResults }) {
  const insights: BusinessInsight[] = results.business_insights;
  if (!insights.length) return null;

  return (
    <div className="eda-card eda-span-12">
      <div className="eda-card-header">
        <div className="eda-card-header-left">
          <p className="eda-card-eyebrow">18 / EDA FINDINGS</p>
          <h2 className="eda-card-title">Statistical observations grounded in data.</h2>
        </div>
        <span className="eda-card-badge">{insights.length} INSIGHTS</span>
      </div>
      <div className="eda-card-body">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 8 }}>
          {insights.map((ins, i) => (
            <div key={i} className="eda-insight-item">
              <span className="eda-insight-category">{ins.category}</span>
              <p className="eda-insight-title">{ins.title}</p>
              <p className="eda-insight-text">{ins.insight}</p>
              <span className={`eda-insight-impact ${ins.impact}`}>
                {ins.impact === 'high' ? '▲' : ins.impact === 'medium' ? '◆' : '▼'} {ins.impact.toUpperCase()} IMPACT
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KPI Banner (lime card — overview metrics)
// ---------------------------------------------------------------------------
function KPIBanner({ results }: { results: EDAResults }) {
  const s = results.dataset_summary;
  const mv = results.missing_values;
  const hasTrend = results.trends.has_time_series;

  return (
    <div className="eda-card-lime eda-span-12">
      <div className="eda-stat-grid eda-stat-grid-4">
        <div className="eda-stat-cell">
          <span className="eda-stat-value" style={{ color: '#101313' }}>{s.numeric_columns.length}</span>
          <span className="eda-stat-label" style={{ color: '#4a5a00' }}>Numeric Columns</span>
        </div>
        <div className="eda-stat-cell">
          <span className="eda-stat-value" style={{ color: '#101313' }}>{s.categorical_columns.length}</span>
          <span className="eda-stat-label" style={{ color: '#4a5a00' }}>Categorical Columns</span>
        </div>
        <div className="eda-stat-cell">
          <span className="eda-stat-value" style={{ color: mv.affected_columns_count > 0 ? '#c05800' : '#101313' }}>
            {mv.affected_columns_count}
          </span>
          <span className="eda-stat-label" style={{ color: '#4a5a00' }}>Cols With Missing</span>
        </div>
        <div className="eda-stat-cell">
          <span className="eda-stat-value" style={{ color: '#101313' }}>
            {hasTrend ? results.trends.trends.length : 0}
          </span>
          <span className="eda-stat-label" style={{ color: '#4a5a00' }}>Trend Signals</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main EDA Studio Page
// ---------------------------------------------------------------------------
export default function EDAStudioPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const searchParams = new URLSearchParams(location.search);
  const initialDatasetId = searchParams.get('dataset') ?? searchParams.get('datasetId') ?? '';

  const [datasets, setDatasets]           = useState<Dataset[]>([]);
  const [selectedId, setSelectedId]       = useState(initialDatasetId);
  const [chartFilters, setChartFilters] = useState<Record<string, unknown>>({});
  const [filterColumn, setFilterColumn] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [filterOperator, setFilterOperator] = useState('eq');
  const [results, setResults]             = useState<EDAResults | null>(null);
  const [loadingDatasets, setLoadingDatasets] = useState(true);
  const [loadingEDA, setLoadingEDA]       = useState(false);
  const [error, setError]                 = useState('');
  const [execMs, setExecMs]               = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load dataset list
  useEffect(() => {
    let active = true;
    datasetService.list().then(items => {
      if (!active) return;
      setDatasets(items);
      if (!selectedId && items.length) setSelectedId(items[0].dataset_id);
    }).catch(e => {
      if (active) setError(e instanceof Error ? e.message : 'Unable to load datasets.');
    }).finally(() => {
      if (active) setLoadingDatasets(false);
    });
    return () => { active = false; };
  }, []);

  // Run EDA
  const runEDA = useCallback(async (datasetId: string) => {
    if (!datasetId) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoadingEDA(true);
    setError('');
    setResults(null);
    setExecMs(null);

    const t0 = performance.now();
    try {
      const res = await edaService.analyze(datasetId, { signal: ctrl.signal, filters: chartFilters });
      if (ctrl.signal.aborted) return;
      setResults(res);
      setExecMs(Math.round(performance.now() - t0));
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setError(e instanceof Error ? e.message : 'EDA analysis failed.');
    } finally {
      if (!ctrl.signal.aborted) setLoadingEDA(false);
    }
  }, [chartFilters]);

  // Auto-run when dataset changes
  useEffect(() => {
    if (selectedId) void runEDA(selectedId);
    return () => { abortRef.current?.abort(); };
  }, [selectedId, runEDA]);

  const selectedDataset = useMemo(
    () => datasets.find(d => d.dataset_id === selectedId),
    [datasets, selectedId],
  );

  const hasTrend = results?.trends.has_time_series && (results.trends.trends.length > 0);

  // Export results as JSON
  function handleExport() {
    if (!results) return;
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `eda-${selectedId}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="eda-studio" role="main">
      {/* ======= HEADER ======= */}
      <header className="eda-header">
        <div>
          <p className="eda-header-eyebrow">AI Data Analyst OS / Exploration</p>
          <h1 className="eda-header-title">Exploratory Analysis</h1>
          <p className="eda-header-sub">Dataset-driven statistical and visual exploration.</p>
        </div>
        <div className="eda-toolbar">
          {loadingDatasets ? (
            <div className="eda-spinner" style={{ width: 20, height: 20 }} />
          ) : (
            <select
              className="eda-dataset-select"
              value={selectedId}
              onChange={e => {
                setSelectedId(e.target.value);
                navigate(`/eda?dataset=${e.target.value}`, { replace: true });
              }}
              aria-label="Select dataset for EDA"
            >
              <option value="" disabled>Select a dataset</option>
              {datasets.map(d => (
                <option key={d.dataset_id} value={d.dataset_id}>{d.name || d.filename}</option>
              ))}
            </select>
          )}
          <button
            className="eda-run-btn"
            disabled={!selectedId || loadingEDA}
            onClick={() => void runEDA(selectedId)}
            aria-label="Re-run EDA analysis"
          >
            <RefreshCw size={13} />
            {loadingEDA ? 'Analyzing…' : 'Run EDA'}
          </button>
          {results && (
            <button
              className="eda-secondary-btn"
              onClick={handleExport}
              aria-label="Export EDA results as JSON"
            >
              <Download size={13} />
              Export
            </button>
          )}
          <Link to="/datasets/upload" className="eda-secondary-btn">
            <ArrowUpRight size={13} />
            Upload
          </Link>
        </div>
      </header>

      {/* ======= META BAR ======= */}
      {results && !loadingEDA && (
        <div className="eda-meta-bar" role="status" aria-live="polite">
          <div className="eda-meta-item">
            <span className="eda-meta-dot" />
            <span>{selectedDataset?.name ?? selectedId}</span>
          </div>
          <div className="eda-meta-item">
            <span className="eda-meta-dot" style={{ background: '#5A6A6A' }} />
            <span>{results.dataset_summary.row_count.toLocaleString()} rows</span>
          </div>
          <div className="eda-meta-item">
            <span className="eda-meta-dot" style={{ background: '#5A6A6A' }} />
            <span>{results.dataset_summary.column_count} columns</span>
          </div>
          {execMs != null && (
            <div className="eda-meta-item">
              <span className="eda-meta-dot" style={{ background: '#5A6A6A' }} />
              <span>Response received in {(execMs / 1000).toFixed(2)}s</span>
            </div>
          )}
          {results.dataset_summary.is_sampled && (
            <div className="eda-meta-item">
              <span className="eda-meta-dot warn" />
              <span>Adaptive sample</span>
            </div>
          )}
          <div className="eda-meta-item">
            <span className="eda-meta-dot" style={{ background: '#5A6A6A' }} />
            <span>{results.dataset_summary.business_domain}</span>
          </div>
        </div>
      )}

      {/* ======= ERROR ======= */}
      {error && (
        <div className="eda-error-banner" role="alert">
          <XCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <div>
            <strong>Analysis Error</strong>
            <p style={{ marginTop: 2, opacity: 0.8 }}>{error}</p>
            <button
              style={{ marginTop: 8, fontSize: 11, color: '#fca5a5', cursor: 'pointer', background: 'none', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 4, padding: '3px 10px', fontFamily: 'inherit' }}
              onClick={() => void runEDA(selectedId)}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* ======= EMPTY STATE ======= */}
      {!loadingEDA && !results && !error && !loadingDatasets && !datasets.length && (
        <div className="eda-empty-state">
          <div className="eda-empty-icon"><BarChart3 size={24} /></div>
          <h2 className="eda-empty-title">No datasets available.</h2>
          <p className="eda-empty-sub">Upload a dataset to begin exploratory analysis. The system will automatically compute statistics, distributions, correlations, and insights.</p>
          <Link to="/datasets/upload" className="eda-run-btn" style={{ textDecoration: 'none' }}>
            Upload a dataset
          </Link>
        </div>
      )}

      {!loadingEDA && !results && !error && !loadingDatasets && datasets.length > 0 && !selectedId && (
        <div className="eda-empty-state">
          <div className="eda-empty-icon"><Activity size={24} /></div>
          <h2 className="eda-empty-title">Select a dataset to analyze.</h2>
          <p className="eda-empty-sub">Choose a dataset from the selector above to begin automated EDA.</p>
        </div>
      )}

      {/* ======= LOADING ======= */}
      {loadingEDA && (
        <div className="eda-loading-overlay" role="status" aria-live="polite">
          <div className="eda-spinner" />
          <p className="eda-loading-text">Running EDA pipeline…</p>
          <p className="eda-loading-text" style={{ color: '#2A3838' }}>Profiling · Statistics · Correlations · Trends · Insights</p>
          <div className="eda-canvas" style={{ width: '100%', maxWidth: 1200, margin: '24px auto 0' }}>
            <SkeletonCard span="eda-span-4" />
            <SkeletonCard span="eda-span-4" />
            <SkeletonCard span="eda-span-4" />
            <SkeletonCard span="eda-span-8" />
            <SkeletonCard span="eda-span-4" />
          </div>
        </div>
      )}

      {/* ======= BENTO CANVAS ======= */}
      {results && !loadingEDA && (
        <div className="eda-canvas" role="region" aria-label="EDA visualization canvas">

          {/* Row 1: KPI Banner */}
          <KPIBanner results={results} />
          <div className="eda-card eda-span-12"><div className="eda-card-body">
            <label>Full dataset filter <select aria-label="Filter column" value={filterColumn} onChange={e=>setFilterColumn(e.target.value)}><option value="">Choose column</option>{results.dataset_summary.column_names.map(c=><option key={c}>{c}</option>)}</select></label>
            <select aria-label="Filter comparison" value={filterOperator} onChange={e=>setFilterOperator(e.target.value)}><option value="eq">Equals</option><option value="gte">At least / from date</option><option value="lte">At most / to date</option></select>
            <input aria-label="Filter value" value={filterValue} onChange={e=>setFilterValue(e.target.value)}/>
            <button onClick={()=>{if(!filterColumn)return; const value=results.dataset_summary.numeric_columns.includes(filterColumn)?Number(filterValue):filterValue; setChartFilters({conditions:[...((chartFilters.conditions as unknown[])??[]),{column:filterColumn,operator:filterOperator,value}]});}}>Apply</button>
            <button onClick={()=>setChartFilters({})}>Reset filters</button>
            <p>All charts recompute from the same filtered source. Click a category bar to drill into that category. {JSON.stringify(chartFilters)}</p>
          </div></div>
          <EDAChartCoordinates charts={results.chart_manifest??[]} onCategory={(column,value)=>setChartFilters({conditions:[...((chartFilters.conditions as unknown[])??[]),{column,operator:'eq',value}]})}/>


          {/* Row 2: Overview + Quality + Distribution */}
          <Card01Overview results={results} datasetName={selectedDataset?.name ?? selectedDataset?.filename ?? selectedId} />
          <Card02Quality results={results} />
          {!results.chart_manifest?.length && <Card03Distribution results={results} />}

          {/* Row 3: Correlation (large) + Box Plot */}
          <Card05Correlation results={results} />
          <Card04BoxPlot results={results} />
          <Card11Anomaly results={results} />

          {/* Row 4: Stats table (wide) */}
          <Card10Stats results={results} />

          {/* Row 5: Missing Values + Composition + Pareto */}
          <Card09Missing results={results} />
          <Card12Composition results={results} />
          <Card13Pareto results={results} />

          {/* Row 6: Categories + Scatter + Trend (conditional) */}
          <Card07Categories results={results} />
          {!results.chart_manifest?.length && <Card08Scatter results={results} />}
          {hasTrend && !results.chart_manifest?.length && <Card06Trend results={results} />}

          {/* Row 7: Findings (full-width) */}
          <Card18Findings results={results} />

          {/* Navigational CTAs */}
          <div className="eda-card eda-span-6" style={{ background: 'transparent', border: '1px dashed #1E2828' }}>
            <div className="eda-card-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <p style={{ fontSize: 11, color: '#5A6A6A', margin: 0 }}>Continue analysis →</p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Link to={`/visualizations?dataset=${selectedId}`} className="eda-secondary-btn">
                  <BarChart3 size={12} /> Visualizations
                </Link>
                <Link to={`/analysis?dataset=${selectedId}`} className="eda-secondary-btn">
                  <Layers size={12} /> AI Analysis
                </Link>
                <Link to={`/forecasting?dataset=${selectedId}`} className="eda-secondary-btn">
                  <TrendingUp size={12} /> Forecasting
                </Link>
                <Link to="/reports/create" className="eda-secondary-btn">
                  <Target size={12} /> Create Report
                </Link>
              </div>
            </div>
          </div>

          <div className="eda-card eda-span-6" style={{ background: 'transparent', border: '1px dashed #1E2828' }}>
            <div className="eda-card-body">
              <p style={{ fontSize: 10, color: '#3A4A4A', lineHeight: 1.6 }}>
                All values are computed by the backend analytics pipeline from your actual dataset.
                No statistics are fabricated or estimated beyond the declared adaptive sampling threshold.
                Use the export button to access the full JSON result for audit or downstream processing.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
