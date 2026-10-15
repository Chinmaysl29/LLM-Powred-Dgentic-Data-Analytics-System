import { transformChartData, validateChartConfig, computeHistogram } from './chartDataTransforms';
import type { DataRow, FieldType, VisualizationConfig, TransformedChartData } from './chartDataTransforms';
export interface InferenceOptions {
  backendTypes?: Record<string, string>;
  overrides?: Record<string, FieldType>;
}
export interface FieldEvidence {
  physicalType: string; analyticalType: FieldType; source: 'backend' | 'inferred' | 'user';
  examined: number; numericMatches: number; reason: string; unit?: string;
}
function numericValue(value: unknown): { value: number; unit: string } | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) && Math.abs(value) <= Number.MAX_SAFE_INTEGER
      ? { value, unit: 'source units' }
      : null;
  }
  if (typeof value !== 'string') return null;
  let str = value.trim();
  if (!str || /^(?:N\/A|NA|null|none|-|--)$/i.test(str)) return null;

  let isNegative = false;
  if (str.startsWith('(') && str.endsWith(')')) {
    isNegative = true;
    str = str.slice(1, -1).trim();
  } else if (str.startsWith('-')) {
    isNegative = true;
    str = str.slice(1).trim();
  } else if (str.startsWith('+')) {
    str = str.slice(1).trim();
  }

  let unit = 'source units';
  const currencyMatch = str.match(/^([₹$€£]|Rs\.?|INR|USD|EUR|GBP)\s*/i);
  if (currencyMatch) {
    unit = currencyMatch[1];
    str = str.slice(currencyMatch[0].length).trim();
  }

  if (str.endsWith('%')) {
    unit = 'percent';
    str = str.slice(0, -1).trim();
  }

  str = str.replace(/,/g, '');
  if (!/^\d+(\.\d+)?$/.test(str)) return null;
  if (str.replace('.', '').length > 16) return null;

  let num = Number(str);
  if (!Number.isFinite(num) || Math.abs(num) > Number.MAX_SAFE_INTEGER) return null;
  if (isNegative) num = -num;

  return { value: num, unit };
}
export function normalizeRecords(records: Record<string, unknown>[], options: InferenceOptions = {}) {
  const originalRows = records.map(row => ({ ...row }));
  const rows: DataRow[] = records.map(row => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, value == null ? null : typeof value === 'number' ? (Number.isFinite(value) ? value : null) : typeof value === 'string' || typeof value === 'boolean' ? value : JSON.stringify(value)])));
  const columns: Record<string, FieldType> = {};
  const evidence: Record<string, FieldEvidence> = {};
  for (const key of new Set(rows.flatMap(row => Object.keys(row)))) {
    const values = rows.map(row => row[key]).filter(value => value != null && value !== '' && !(typeof value === 'string' && /^(?:N\/A|NA|null)$/i.test(value.trim())));
    const sample = values.length <= 256 ? values : Array.from({ length: 256 }, (_, i) => values[Math.floor(i * (values.length - 1) / 255)]);
    const physicalType = options.backendTypes?.[key] ?? [...new Set(values.map(v => typeof v))].join('|');
    const backendType: FieldType | undefined = /^(?:u?int\d*|float\d*|double|decimal|numeric|number)$/i.test(physicalType) ? 'number' : /date|timestamp/i.test(physicalType) ? 'date' : /^(bool|boolean)$/i.test(physicalType) ? 'boolean' : /^(category|categorical)$/i.test(physicalType) ? 'category' : undefined;
    const requested = options.overrides?.[key] ?? backendType;
    const identifier = /(?:^|[_ -])(id|identifier|zip|zipcode|postal|phone|telephone|account|code|sku)(?:$|[_ -])/i.test(key) || /(?:Id|ID)$/.test(key);
    const parsed = sample.map(numericValue);
    const numericMatches = parsed.filter(p => p !== null).length;
    const safeNumeric = !!values.length && !identifier && ((numericMatches / sample.length) >= 0.75);
    let type: FieldType = safeNumeric ? 'number' : values.length && values.every(v => typeof v === 'boolean') ? 'boolean' : values.length && values.every(v => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v) && Number.isFinite(Date.parse(v))) ? 'date' : 'category';
    if (requested) type = requested === 'number' && !safeNumeric ? 'category' : requested;
    columns[key] = type;
    evidence[key] = { physicalType, analyticalType: type, source: options.overrides?.[key] ? 'user' : backendType ? 'backend' : 'inferred', examined: sample.length, numericMatches,
      reason: identifier ? 'Identifier representation preserved' : requested === 'number' && !safeNumeric ? 'Numeric conversion rejected: mixed, formatted inconsistently, or unsafe precision' : 'Conservative loaded-record inference; original values retained', unit: type === 'number' ? parsed.find(p => p !== null)?.unit : undefined };
    if (type === 'number') for (const row of rows) row[key] = numericValue(row[key])?.value ?? null;
  }
  return { rows, columns, originalRows, evidence };
}
export function filterRecords(rows: DataRow[], field: string, value: string, dateField: string, start: string, end: string) {
  return rows.filter(row => {
    if (field && value && !String(row[field] ?? '').toLowerCase().includes(value.toLowerCase())) return false;
    if (!dateField || (!start && !end)) return true;
    const date = Date.parse(String(row[dateField]));
    return Number.isFinite(date) && (!start || date >= Date.parse(start)) && (!end || date < Date.parse(end) + 86400000);
  });
}
export function aggregateRecords(rows: DataRow[], x: string, y: string, group: string, operation: 'sum' | 'mean' | 'count') {
  const buckets = new Map<string, { row: DataRow; sum: number; count: number }>();
  for (const row of rows) {
    const value = row[y];
    if (operation !== 'count' && (typeof value !== 'number' || !Number.isFinite(value))) continue;
    const key = JSON.stringify([row[x] ?? null, group ? row[group] ?? null : null]);
    const bucket = buckets.get(key) ?? { row: { [x]: row[x] ?? null, ...(group ? { [group]: row[group] ?? null } : {}) }, sum: 0, count: 0 };
    bucket.sum += typeof value === 'number' ? value : 0; bucket.count++; buckets.set(key, bucket);
  }
  return [...buckets.values()].map(b => ({ ...b.row, [y]: operation === 'count' ? b.count : operation === 'mean' ? b.sum / b.count : b.sum }));
}
export function buildVisualization(rows: DataRow[], columns: Record<string, FieldType>, config: VisualizationConfig, operation: 'sum' | 'mean' | 'count'): TransformedChartData {
  if (config.chartType === 'Histogram') {
    const numericCols = Object.keys(columns).filter(c => columns[c] === 'number');
    const metric = config.yAxis && columns[config.yAxis] === 'number'
      ? config.yAxis
      : (config.xAxis && columns[config.xAxis] === 'number'
        ? config.xAxis
        : (numericCols[0] || ''));
    return computeHistogram(rows, metric);
  }
  const effectiveY = config.yAxis || (operation === 'count' ? config.xAxis : '');
  if (config.chartType !== 'Table') {
    if (!columns[config.xAxis] || (!columns[effectiveY] && operation !== 'count')) {
      return { type: config.chartType, isValid: false, validationMessage: 'Select fields available in the current dataset.' };
    }
  }
  if (config.chartType === 'Treemap' && rows.some(row => typeof row[effectiveY] === 'number' && Number(row[effectiveY]) < 0)) return { type: config.chartType, isValid: false, validationMessage: 'Treemaps require nonnegative values. Use a bar chart for signed values.' };
  if (!['Bar', 'Line', 'Area', 'Pie'].includes(config.chartType)) return transformChartData(rows, columns, { ...config, yAxis: effectiveY });
  const validity = validateChartConfig(columns, { ...config, yAxis: effectiveY });
  if (!validity.isValid && operation !== 'count') return { type: config.chartType, isValid: false, validationMessage: validity.message || 'Choose different X and Y fields.' };
  const grouped = config.chartType === 'Bar' ? config.groupBy : '';
  const aggregated = aggregateRecords(rows, config.xAxis, config.yAxis, grouped, operation);
  if (columns[config.xAxis] === 'date') aggregated.sort((a, b) => Date.parse(String(a[config.xAxis])) - Date.parse(String(b[config.xAxis])));
  const points = aggregated.map(row => ({ categoryKey: JSON.stringify(row[config.xAxis] ?? null), seriesKey: grouped ? JSON.stringify(row[grouped] ?? null) : undefined, label: String(row[config.xAxis] ?? 'Missing'), value: Number(row[config.yAxis]), group: grouped ? String(row[grouped] ?? 'Missing') : undefined }));
  if (config.chartType === 'Pie' && points.some(p => p.value < 0)) return { type: config.chartType, isValid: false, validationMessage: 'Pie charts require nonnegative values. Use a bar chart for signed values.' };
  return { type: config.chartType, isValid: true, points, metric: config.yAxis, aggregation: operation, unit: operation === 'count' ? 'records' : 'source units' };
}
