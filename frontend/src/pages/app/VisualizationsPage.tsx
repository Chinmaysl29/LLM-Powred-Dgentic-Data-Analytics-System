import { useCallback, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowUpRight, Download, Save } from 'lucide-react';
import { workbenchService, downloadWorkbenchJson } from '../../services/workbenchService';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { dashboardService } from '../../services/dashboardService';
import { isSupabaseConfigured } from '../../lib/supabase/client';
import { normalizeRecords, filterRecords, buildVisualization } from '../../lib/visualizationData';
import { getSensibleDefaults, computeHistogram } from '../../lib/chartDataTransforms';
import type {
  ChartType,
  VisualizationConfig,
  TransformedChartData,
} from '../../lib/chartDataTransforms';
import ResultChart from '../../components/analytics/ResultChart';

const TYPES: ChartType[] = [
  'Bar',
  'Line',
  'Area',
  'Pie',
  'Scatter',
  'Histogram',
  'Heatmap',
  'Treemap',
  'Table',
];
interface ResultSource {
  records?: Record<string, unknown>[];
  datasetId?: string;
  question?: string;
}

const EMPTY_RECORDS: Record<string, unknown>[] = [];
const EMPTY_TYPES: Record<string, string> = {};
const isDocumentType = (type?: string) =>
  ['pdf', 'txt', 'text', 'md', 'markdown'].includes((type || '').toLowerCase());

export default function VisualizationsPage() {
  const context = useLocation().state as ResultSource | null;
  const [selectedId, setSelected] = useState<string | null>(
    context?.records?.length ? '__analysis' : (context?.datasetId ?? null),
  );
  const [typeOverrides, setTypeOverrides] = useState<
    Record<string, 'number' | 'category' | 'date' | 'boolean'>
  >({});
  const [attempt, setAttempt] = useState(0);
  const [config, setConfig] = useState<VisualizationConfig>({
    chartType: 'Bar',
    xAxis: '',
    yAxis: '',
    groupBy: '',
    filters: [],
  });
  const [operation, setOperation] = useState<'sum' | 'mean' | 'count'>('sum');
  const [filterField, setFilterField] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [dateField, setDateField] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [title, setTitle] = useState('');
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [requestedDistributionMetric, setDistributionMetric] = useState('');
  const fetchDatasets = useCallback((signal: AbortSignal) => workbenchService.datasets(signal), []);
  const registry = useAsyncResource(fetchDatasets, attempt);
  const datasets = registry.data ?? [];
  const selected =
    selectedId ??
    datasets.find((d) => !isDocumentType(d.file_type))?.dataset_id ??
    datasets[0]?.dataset_id ??
    '';
  const selectedDataset = datasets.find((d) => d.dataset_id === selected);
  const isSelectedDocument =
    selected !== '__analysis' && isDocumentType(selectedDataset?.file_type);
  const fetchPreview = useCallback(
    async (signal: AbortSignal) => {
      const data =
        selected === '__analysis'
          ? {
              rows: context?.records?.slice(0, 1000) ?? [],
              total_rows: context?.records?.length ?? 0,
              column_types: {},
            }
          : await workbenchService.preview(selected, signal);
      if (!Array.isArray(data.rows))
        throw new Error('The preview service returned invalid records.');
      if (!signal.aborted) {
        const types = data.column_types ?? {};
        const normalized = normalizeRecords(data.rows, { backendTypes: types });
        const fields = getSensibleDefaults('Bar', normalized.columns, {
          xAxis: '',
          yAxis: '',
          groupBy: '',
        });
        setConfig({ chartType: 'Bar', ...fields, filters: [] });
        setTypeOverrides({});
        setNotice('');
        setFilterField('');
        setFilterValue('');
        setDateField('');
        setStart('');
        setEnd('');
        setOperation('sum');
      }
      return data;
    },
    [selected, context?.records],
  );
  const preview = useAsyncResource(selected && !isSelectedDocument ? fetchPreview : null, attempt);
  const records = preview.data?.rows ?? EMPTY_RECORDS;
  const backendTypes = preview.data?.column_types ?? EMPTY_TYPES;
  const total = preview.data?.total_rows ?? 0;
  const busy = registry.loading || preview.loading;
  const error = registry.error || preview.error;

  const normalized = useMemo(
    () => normalizeRecords(records, { backendTypes, overrides: typeOverrides }),
    [records, backendTypes, typeOverrides],
  );
  const { columns, rows } = normalized;
  const fields = useMemo(() => Object.keys(columns), [columns]);
  const numbers = useMemo(() => fields.filter((f) => columns[f] === 'number'), [fields, columns]);
  const dates = useMemo(() => fields.filter((f) => columns[f] === 'date'), [fields, columns]);
  const invalidDates = Boolean(start && end && start > end);
  const filtered = useMemo(
    () => filterRecords(rows, filterField, filterValue, dateField, start, end),
    [rows, filterField, filterValue, dateField, start, end],
  );

  // Each full-population result is valid only for its exact source and controls.
  const fetchChart = useCallback(
    (signal: AbortSignal) =>
      workbenchService.chartData(
        selected,
        {
          chart_type: config.chartType,
          x_axis: config.xAxis,
          y_axis: config.yAxis,
          aggregation: operation,
          group_by: config.groupBy,
          filter_field: filterField,
          filter_value: filterValue,
          date_field: dateField,
          start_date: start,
          end_date: end,
        },
        signal,
      ),
    [
      selected,
      config.chartType,
      config.xAxis,
      config.yAxis,
      config.groupBy,
      operation,
      filterField,
      filterValue,
      dateField,
      start,
      end,
    ],
  );
  const chartRequest = useAsyncResource(
    selected && selected !== '__analysis' && !isSelectedDocument && fields.length
      ? fetchChart
      : null,
    attempt,
  );
  const backendChart = chartRequest.data;

  const chart: TransformedChartData = useMemo(() => {
    if (backendChart && backendChart.is_valid && config.chartType === backendChart.chart_type) {
      return {
        type: config.chartType,
        isValid: true,
        points: backendChart.points,
        scatterPoints: backendChart.scatter_points ?? undefined,
        scatterBounds: backendChart.scatter_bounds ?? undefined,
        metric: backendChart.metric,
        aggregation: backendChart.aggregation,
        unit: backendChart.unit,
      };
    }
    return buildVisualization(filtered, columns, config, operation);
  }, [backendChart, filtered, columns, config, operation]);

  const nonIdNumbers = numbers.filter(
    (n) => !/(?:^|_)(?:id|code|key|index|zip|postal)(?:$|_)/i.test(n),
  );
  const distributionMetric = numbers.includes(requestedDistributionMetric)
    ? requestedDistributionMetric
    : (nonIdNumbers[0] ?? numbers[0] ?? '');
  const fetchDistribution = useCallback(
    (signal: AbortSignal) =>
      workbenchService.chartData(
        selected,
        {
          chart_type: 'Histogram',
          x_axis: distributionMetric,
          y_axis: distributionMetric,
          filter_field: filterField,
          filter_value: filterValue,
          date_field: dateField,
          start_date: start,
          end_date: end,
        },
        signal,
      ),
    [selected, distributionMetric, filterField, filterValue, dateField, start, end],
  );
  const distributionRequest = useAsyncResource(
    selected && selected !== '__analysis' && !isSelectedDocument && distributionMetric
      ? fetchDistribution
      : null,
    attempt,
  );
  const backendDistribution = distributionRequest.data;
  const distributionBusy = distributionRequest.loading;

  const distribution: TransformedChartData = useMemo(() => {
    if (
      backendDistribution &&
      backendDistribution.is_valid &&
      backendDistribution.chart_type === 'Histogram'
    ) {
      return {
        type: 'Histogram',
        isValid: true,
        metric: backendDistribution.metric,
        aggregation: 'frequency',
        unit: 'observations',
        points: backendDistribution.points,
        histogramBins: backendDistribution.histogram_bins ?? undefined,
        summaryMetrics: backendDistribution.summary_metrics,
      };
    }
    if (numbers.length === 0) {
      return {
        type: 'Histogram',
        isValid: false,
        validationMessage:
          'No numerical field is available for a distribution chart in this dataset.',
      };
    }
    return computeHistogram(filtered, distributionMetric || numbers[0]);
  }, [backendDistribution, filtered, distributionMetric, numbers]);

  const scatter: TransformedChartData = useMemo(() => {
    if (backendChart?.scatter_points && backendChart.scatter_bounds) {
      return {
        type: 'Scatter',
        isValid: true,
        scatterPoints: backendChart.scatter_points,
        scatterBounds: backendChart.scatter_bounds,
        scatterSampling: {
          method: backendChart.is_sampled ? 'representative sample' : 'all valid pairs',
          totalValid: backendChart.computed_records,
          displayed: backendChart.scatter_points.length,
          domain: 'source bounds',
        },
      };
    }
    return buildVisualization(
      filtered,
      columns,
      {
        chartType: 'Scatter',
        xAxis: numbers[0] ?? '',
        yAxis: numbers[1] ?? '',
        groupBy: '',
        filters: [],
      },
      'sum',
    );
  }, [backendChart, filtered, columns, numbers]);

  const source =
    selected === '__analysis'
      ? 'Analysis result'
      : (datasets.find((d) => d.dataset_id === selected)?.dataset_name ?? 'Dataset');
  const effectiveMetric = backendChart?.metric || config.yAxis || numbers[0] || 'records';
  const effectiveDim = backendChart?.dimension || config.xAxis || fields[0] || 'all';
  const label =
    config.chartType === 'Table'
      ? 'Source records'
      : config.chartType === 'Scatter'
        ? `${config.yAxis || numbers[1] || 'Y'} versus ${config.xAxis || numbers[0] || 'X'}`
        : `${['Heatmap', 'Treemap'].includes(config.chartType) ? 'sum' : operation} of ${effectiveMetric} by ${effectiveDim}`;

  function setType(chartType: ChartType) {
    setConfig((current) => ({
      ...current,
      ...getSensibleDefaults(chartType, columns, current),
      chartType,
    }));
  }

  async function save() {
    setSaving(true);
    setNotice('');
    try {
      const result = await dashboardService.saveVisualization(
        title.trim() || label,
        config.chartType,
        {
          ...config,
          operation,
          filterField,
          filterValue,
          dateField,
          start,
          end,
          sourceScope: backendChart
            ? `Full population (${backendChart.total_records} records)`
            : 'Sample preview',
        },
        selected === '__analysis' ? context?.datasetId : selected,
      );
      if (!result) throw new Error('Saving is unavailable in this deployment.');
      setNotice('Visualization configuration saved to your account.');
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  }

  const tabularDatasets = datasets.filter((d) => !isDocumentType(d.file_type));
  const documentDatasets = datasets.filter((d) => isDocumentType(d.file_type));
  const totalCountDisplay = backendChart?.total_records ?? total ?? 0;
  const eligibleCountDisplay = backendChart?.eligible_records ?? filtered.length;

  return (
    <div className="ws-page">
      <header className="editorial-heading">
        <p className="eyebrow">ANALYTICS / VISUALIZATIONS</p>
        <h1 className="ws-page-heading">A different perspective.</h1>
        <p className="ws-page-sub">Explore the patterns. Keep the evidence in view.</p>
      </header>

      <div className="studio-toolbar">
        <label className="control-field">
          Data source
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="" disabled>
              Select a dataset
            </option>
            {context?.records?.length ? (
              <option value="__analysis">Returned analysis records</option>
            ) : null}
            {tabularDatasets.length > 0 && (
              <optgroup label="Structured Datasets (Charts & Visualizations)">
                {tabularDatasets.map((d) => (
                  <option key={d.dataset_id} value={d.dataset_id}>
                    {d.dataset_name} ({d.file_type ? d.file_type.toUpperCase() : 'Table'})
                  </option>
                ))}
              </optgroup>
            )}
            {documentDatasets.length > 0 && (
              <optgroup label="Unstructured Documents (RAG Evidence)">
                {documentDatasets.map((d) => (
                  <option key={d.dataset_id} value={d.dataset_id}>
                    {d.dataset_name} ({d.file_type ? d.file_type.toUpperCase() : 'DOC'})
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        <Link className="reports-btn-secondary" to="/datasets/upload">
          Upload dataset <ArrowUpRight size={15} />
        </Link>
      </div>

      {isSelectedDocument && (
        <div
          role="status"
          className="surface-panel"
          style={{ borderLeft: '3px solid #38bdf8', padding: 20, marginBottom: 20 }}
        >
          <h3 style={{ color: '#fff', margin: '0 0 8px 0' }}>
            Unstructured Document Source: {selectedDataset?.dataset_name}
          </h3>
          <p style={{ margin: '0 0 16px 0', color: 'var(--text-muted)' }}>
            This source is an unstructured text/PDF document (
            {selectedDataset?.file_type?.toUpperCase()}) ingested into the RAG vector store for
            document search and citation evidence. It does not contain tabular numerical rows for
            charting.
          </p>
          <div style={{ display: 'flex', gap: 12 }}>
            <Link
              className="reports-btn-primary"
              to="/rag"
              style={{
                background: '#38bdf8',
                color: '#0f172a',
                padding: '8px 16px',
                borderRadius: 8,
                textDecoration: 'none',
                fontWeight: 600,
              }}
            >
              Query Document in RAG →
            </Link>
            {tabularDatasets.length > 0 && (
              <button
                className="reports-btn-secondary"
                onClick={() => setSelected(tabularDatasets[0].dataset_id)}
              >
                Switch to Tabular Dataset ({tabularDatasets[0].dataset_name})
              </button>
            )}
          </div>
        </div>
      )}

      {error && (
        <div role="alert" className="surface-panel">
          <p>{error}</p>
          <button className="reports-btn-secondary" onClick={() => setAttempt((n) => n + 1)}>
            Retry data
          </button>
        </div>
      )}

      {busy && (
        <p role="status" className="source-note">
          Loading source records…
        </p>
      )}
      {!busy && !error && !records.length && !isSelectedDocument && (
        <div className="source-note">
          No records available. Upload a dataset or choose another source to begin.
        </div>
      )}

      {!!records.length && (
        <>
          <p className="source-note">
            {source} · Total Population:{' '}
            {totalCountDisplay ? totalCountDisplay.toLocaleString() : '—'} records
            {backendChart
              ? ` · Calculations performed across all ${eligibleCountDisplay.toLocaleString()} eligible records`
              : ''}
            .
            {selected === '__analysis'
              ? ` Showing up to 1,000 returned analysis records.`
              : ` Preview sample: up to ${records.length} loaded records for inspection.`}
          </p>

          <details className="surface-panel">
            <summary>Field types and inference evidence</summary>
            {fields.map((field) => (
              <label key={field} className="control-field">
                {field} ({normalized.evidence[field].physicalType})
                <select
                  aria-label={`Analytical type for ${field}`}
                  value={typeOverrides[field] ?? ''}
                  onChange={(e) =>
                    setTypeOverrides((current) => {
                      const next = { ...current };
                      if (e.target.value)
                        next[field] = e.target.value as 'number' | 'category' | 'date' | 'boolean';
                      else delete next[field];
                      return next;
                    })
                  }
                >
                  <option value="">Automatic: {columns[field]}</option>
                  <option value="category">Category</option>
                  <option value="number">Numeric measure</option>
                </select>
                <small>
                  {normalized.evidence[field].reason}; {normalized.evidence[field].numericMatches}/
                  {normalized.evidence[field].examined} sampled values numeric
                  {normalized.evidence[field].unit ? `; ${normalized.evidence[field].unit}` : ''}
                </small>
              </label>
            ))}
          </details>

          <section className="surface-panel" aria-labelledby="builder-heading">
            <h2 id="builder-heading">Build your view</h2>
            <div className="studio-builder">
              <label className="control-field">
                Chart type
                <select
                  value={config.chartType}
                  onChange={(e) => setType(e.target.value as ChartType)}
                >
                  {TYPES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label className="control-field">
                X field
                <select
                  value={config.xAxis}
                  onChange={(e) => setConfig({ ...config, xAxis: e.target.value })}
                >
                  <option value="">Select field</option>
                  {(config.chartType === 'Scatter'
                    ? numbers.length
                      ? numbers
                      : fields
                    : fields
                  ).map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </label>
              <label className="control-field">
                Y field
                <select
                  value={config.yAxis}
                  onChange={(e) => setConfig({ ...config, yAxis: e.target.value })}
                >
                  <option value="">Select numeric field</option>
                  {numbers.map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </label>
              <label className="control-field">
                Aggregation
                <select
                  disabled={!['Bar', 'Line', 'Area', 'Pie'].includes(config.chartType)}
                  value={operation}
                  onChange={(e) => setOperation(e.target.value as typeof operation)}
                >
                  <option value="sum">Sum</option>
                  <option value="mean">Average</option>
                  <option value="count">Record count</option>
                </select>
              </label>
              <label className="control-field">
                Group by
                <select
                  disabled={!['Bar', 'Heatmap', 'Treemap'].includes(config.chartType)}
                  value={config.groupBy}
                  onChange={(e) => setConfig({ ...config, groupBy: e.target.value })}
                >
                  <option value="">No grouping</option>
                  {fields
                    .filter((f) => f !== config.xAxis && f !== config.yAxis)
                    .map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                </select>
              </label>
              <label className="control-field">
                Filter field
                <select value={filterField} onChange={(e) => setFilterField(e.target.value)}>
                  <option value="">No filter</option>
                  {fields.map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </label>
              <label className="control-field">
                Contains
                <input
                  value={filterValue}
                  disabled={!filterField}
                  onChange={(e) => setFilterValue(e.target.value)}
                  placeholder="Filter records"
                />
              </label>
              <label className="control-field">
                Date field
                <select value={dateField} onChange={(e) => setDateField(e.target.value)}>
                  <option value="">No date filter</option>
                  {dates.map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </label>
              {dateField && (
                <>
                  <label className="control-field">
                    From
                    <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
                  </label>
                  <label className="control-field">
                    Through
                    <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
                  </label>
                </>
              )}
            </div>
            {invalidDates && <p role="alert">End date must be on or after the start date.</p>}
          </section>
        </>
      )}

      <div className="editorial-gallery" style={{ marginTop: 24 }}>
        <section className="gallery-card gallery-feature">
          <p className="eyebrow">01 / FEATURED ANALYSIS</p>
          <h2>{records.length ? label : 'Every pattern starts with a question.'}</h2>
          <div className="studio-chart">
            {records.length && !busy && !invalidDates ? (
              <ResultChart data={chart} label={label} />
            ) : (
              <p className="gallery-placeholder">Select a source to chart real observations.</p>
            )}
          </div>
          <p className="ws-page-sub">
            {records.length
              ? `${source} · ${config.chartType} · ${backendChart ? `Computed over full population (${eligibleCountDisplay.toLocaleString()} records)` : 'Loaded records'}`
              : 'Your analytical canvas is ready.'}
          </p>
        </section>

        <section className="gallery-card gallery-lime">
          <p className="eyebrow">02 / THE DATA BEHIND THE VIEW</p>
          <h2>
            Small details.
            <br />
            Better context.
          </h2>
          <div className="gallery-stat">
            <strong>{totalCountDisplay ? totalCountDisplay.toLocaleString() : '—'}</strong>
            <span>Total population records</span>
          </div>
          <div className="gallery-stat">
            <strong>{eligibleCountDisplay ? eligibleCountDisplay.toLocaleString() : '—'}</strong>
            <span>Matching eligible records</span>
          </div>
          <div className="gallery-stat">
            <strong>{records.length ? fields.length : '—'}</strong>
            <span>Available fields</span>
          </div>
          {backendChart?.summary_metrics &&
            Object.keys(backendChart.summary_metrics).length > 0 && (
              <div
                style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid rgba(0,0,0,0.1)' }}
              >
                <p
                  style={{
                    margin: 0,
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Full Population KPI ({backendChart.metric})
                </p>
                <p style={{ margin: '3px 0 0 0', fontSize: 12 }}>
                  Sum: <strong>{backendChart.summary_metrics.sum?.toLocaleString()}</strong> · Mean:{' '}
                  <strong>{backendChart.summary_metrics.mean?.toLocaleString()}</strong>
                </p>
                <p style={{ margin: '2px 0 0 0', fontSize: 11, color: 'rgba(0,0,0,0.7)' }}>
                  Range: [{backendChart.summary_metrics.min?.toLocaleString()} to{' '}
                  {backendChart.summary_metrics.max?.toLocaleString()}]
                </p>
              </div>
            )}
        </section>

        <section className="gallery-card">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <div>
              <p className="eyebrow">03 / DISTRIBUTION</p>
              <h2>Understand how values are distributed.</h2>
            </div>
            {numbers.length > 1 && (
              <div style={{ alignSelf: 'center' }}>
                <label style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Measure:{' '}
                  <select
                    aria-label="Distribution numeric measure"
                    value={distributionMetric}
                    onChange={(e) => setDistributionMetric(e.target.value)}
                    style={{
                      background: 'rgba(255, 255, 255, 0.08)',
                      color: 'var(--text-h)',
                      border: '1px solid rgba(255, 255, 255, 0.2)',
                      borderRadius: 4,
                      padding: '3px 8px',
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    {numbers.map((n) => (
                      <option key={n} value={n} style={{ background: '#101312', color: '#fff' }}>
                        {n}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>
          {numbers.length === 0 ? (
            <p className="gallery-placeholder">
              No numerical field is available for a distribution chart in this dataset.
            </p>
          ) : records.length && !busy && !distributionBusy ? (
            <ResultChart
              data={distribution}
              label={`Distribution of ${distributionMetric || 'values'}`}
            />
          ) : (
            <p className="gallery-placeholder">
              {busy || distributionBusy
                ? 'Computing distribution…'
                : 'Select a source to view value distribution.'}
            </p>
          )}
          <p className="ws-page-sub">
            Frequency of observations across value ranges.
            {backendDistribution?.total_records
              ? ` Computed across full population (${(backendDistribution.eligible_records ?? backendDistribution.total_records).toLocaleString()} records).`
              : ''}
          </p>
        </section>

        <section className="gallery-card gallery-relationships">
          <p className="eyebrow">04 / RELATIONSHIPS</p>
          <h2>Find the connection.</h2>
          {(numbers.length >= 2 ||
            (backendChart?.scatter_points && backendChart.scatter_points.length > 0)) &&
          !busy &&
          !invalidDates ? (
            <ResultChart
              data={scatter}
              label={`${numbers[1] ?? 'Y'} versus ${numbers[0] ?? 'X'}`}
            />
          ) : (
            <p className="gallery-placeholder">
              Load at least two numeric fields to compare individual observations.
            </p>
          )}
          <p className="ws-page-sub">
            {backendChart?.sampling_disclosure ||
              'Each point represents an observation. A relationship alone does not establish a cause.'}
          </p>
        </section>

        <section className="gallery-card">
          <p className="eyebrow">05 / CONVERSION</p>
          <h2>Follow the journey.</h2>
          <span className="capability-badge">Requires a verified funnel workflow</span>
          <p className="gallery-placeholder">
            Funnel analysis requires ordered stages and a consistent population. The current chart
            engine does not provide a verified funnel workflow.
          </p>
          <Link to="/analysis">Ask about conversion →</Link>
        </section>

        <section className="gallery-card">
          <p className="eyebrow">06 / RETENTION</p>
          <h2>Understand what lasts.</h2>
          <span className="capability-badge">Requires cohort data</span>
          <p className="gallery-placeholder">
            Retention needs customer identifiers, event dates and a defined cohort. No retention
            score has been inferred from this sample.
          </p>
          <Link to="/analysis">Explore your cohort question →</Link>
        </section>
      </div>

      {!!records.length && (
        <section className="surface-panel">
          <h2>Keep the evidence</h2>
          <label className="control-field">
            Visualization title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={120}
              placeholder={label}
            />
          </label>
          <div className="studio-actions">
            <button
              className="reports-create-btn"
              disabled={!chart.isValid || saving || busy || invalidDates || !isSupabaseConfigured()}
              onClick={() => void save()}
            >
              <Save size={15} /> {saving ? 'Saving…' : 'Save configuration'}
            </button>
            <button
              className="reports-btn-secondary"
              disabled={busy || invalidDates}
              onClick={() =>
                downloadWorkbenchJson(
                  {
                    source,
                    scope: backendChart
                      ? `full population (${backendChart.total_records} records)`
                      : 'loaded records only',
                    config,
                    operation,
                    filters: { filterField, filterValue, dateField, start, end },
                    records: filtered,
                  },
                  'visualization-records.json',
                )
              }
            >
              <Download size={15} /> Export loaded records
            </button>
            <Link className="reports-btn-secondary" to="/dashboard-studio">
              Open Dashboard Studio
            </Link>
          </div>
          {!isSupabaseConfigured() && (
            <p className="ws-page-sub">
              Account saving requires configured Supabase storage. Export remains available.
            </p>
          )}
          {notice && <p role="status">{notice}</p>}
          <details>
            <summary>View underlying records</summary>
            <div className="studio-values">
              <table>
                <caption>First 100 matching loaded records</caption>
                <thead>
                  <tr>
                    {fields.map((f) => (
                      <th key={f} scope="col">
                        {f}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, 100).map((r, i) => (
                    <tr key={i}>
                      {fields.map((f) => (
                        <td key={f}>{String(r[f] ?? '—')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </section>
      )}
    </div>
  );
}
