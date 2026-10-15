import { InvalidConfigMessage, SelfFormingHeatmap, SelfFormingTable } from '../animatedGlowVisualizations';
import type { TransformedChartData } from '../../lib/chartDataTransforms';
const COLORS = ['#b3d779', '#789b48', '#a0b69a', '#52755b', '#c8fd39', '#829b8b', '#d5ddc9'];
export default function ResultChart({ data, label }: { data: TransformedChartData; label: string }) {
  if (!data.isValid) return <InvalidConfigMessage message={data.validationMessage} />;
  if (data.type === 'Table') return <SelfFormingTable tableData={data.tableData} ariaLabel={label} />;
  if (data.type === 'Bar' && data.points?.some(p => p.group !== undefined)) return <GroupedBars data={data} label={label} />;
  if (data.type === 'Scatter') return <Scatter data={data} label={label} />;
  if (data.type === 'Heatmap') return <><SelfFormingHeatmap heatmapData={data.heatmapData} ariaLabel={label} /><p className="chart-scope">Sum by category pair; limited to the engine's displayed categories.</p></>;
  if (data.type === 'Treemap') return <Treemap data={data} label={label} />;
  if (data.type === 'Histogram') return <HistogramChart data={data} label={label} />;
  const points = data.points ?? [];
  if (!points.length) return <p className="gallery-placeholder">No values match this field mapping and filter.</p>;
  const shown = points.slice(0, 30);
  const min = Math.min(0, ...shown.map(p => p.value)); const max = Math.max(0, ...shown.map(p => p.value));
  const range = max - min || 1; const y = (v: number) => 220 - (v - min) / range * 180;
  const x = (i: number) => 60 + (i + .5) / shown.length * 480;
  const zero = y(0); const path = shown.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.value)}`).join(' ');
  const total = points.reduce((sum, p) => sum + p.value, 0);
  const offsets = [0];
  for (const point of points) offsets.push(offsets[offsets.length - 1] + point.value);
  return <div className="analytical-chart">
    {data.type === 'Pie' ? total > 0 ? <><svg viewBox="0 0 240 240" role="img" aria-label={label} style={{ width: '100%', maxHeight: 220 }}><title>{`${label}. Exact values follow.`}</title>{points.map((p, i) => { const length = p.value / total * 100; const start = offsets[i] / total * 100; return <circle key={i} cx="120" cy="120" r="75" fill="none" stroke={COLORS[i % COLORS.length]} strokeWidth="42" pathLength="100" strokeDasharray={`${length} ${100 - length}`} strokeDashoffset={-start} transform="rotate(-90 120 120)"><title>{`${p.label}: ${p.value.toLocaleString()} (${length.toFixed(1)}%)`}</title></circle>; })}<text x="120" y="125" textAnchor="middle" fill="currentColor" fontSize="18">{total.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 2 })}</text></svg><p className="chart-scope">Total in source units; every category is included.</p></> : <p>No positive total for a share chart.</p> : <><svg viewBox="0 0 580 260" role="img" aria-label={label} style={{ width: '100%', overflow: 'visible' }}><title>{`${label}. Signed scale with zero baseline; exact values follow.`}</title>{[0, .5, 1].map(f => { const v = min + f * range; return <g key={f}><line x1="60" x2="540" y1={y(v)} y2={y(v)} stroke="currentColor" opacity=".15" /><text x="52" y={y(v) + 4} textAnchor="end" fill="currentColor" fontSize="10">{v.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 })}</text></g>; })}<line x1="60" x2="540" y1={zero} y2={zero} stroke="currentColor" opacity=".4" />{data.type === 'Bar' ? shown.map((p, i) => <rect key={i} x={x(i) - 160 / shown.length} y={Math.min(y(p.value), zero)} width={320 / shown.length} height={Math.abs(y(p.value) - zero)} rx="2" fill={COLORS[i % COLORS.length]}><title>{`${p.label}${p.group ? ` / ${p.group}` : ''}: ${p.value.toLocaleString()}`}</title></rect>) : <>{data.type === 'Area' && <path d={`${path} L${x(shown.length - 1)},${zero} L${x(0)},${zero} Z`} fill="#b3d779" opacity=".15" />}<path d={path} fill="none" stroke="#b3d779" strokeWidth="2.5" />{shown.map((p, i) => <circle key={i} cx={x(i)} cy={y(p.value)} r="3" fill="#b3d779"><title>{`${p.label}: ${p.value.toLocaleString()}`}</title></circle>)}</>}{shown.filter((_, i) => i === 0 || i === shown.length - 1 || (shown.length < 7)).map(p => <text key={`${p.label}-${p.group}`} x={x(shown.indexOf(p))} y="244" textAnchor="middle" fontSize="10" fill="currentColor">{p.label.length > 14 ? p.label.slice(0, 12) + '…' : p.label}</text>)}</svg><p className="chart-scope">{shown.length} of {points.length} category values shown · source units · {min < 0 ? 'includes negative values' : 'zero baseline'}</p></>}
    <details><summary>Exact chart values</summary><div className="studio-values"><table><caption>{label}</caption><thead><tr><th scope="col">Category</th><th scope="col">Value</th></tr></thead><tbody>{points.map((p, i) => <tr key={i}><th scope="row">{p.label}{p.group ? ` / ${p.group}` : ''}</th><td>{p.value.toLocaleString(undefined, { maximumSignificantDigits: 15 })}</td></tr>)}</tbody></table></div></details>
  </div>;
}

function Scatter({ data, label }: { data: TransformedChartData; label: string }) {
  const points = data.scatterPoints ?? []; const bounds = data.scatterBounds;
  if (!points.length || !bounds) return <p>No paired numeric observations available.</p>;
  const { minX, maxX, minY, maxY } = bounds;
  const rangeX = maxX - minX || 1; const rangeY = maxY - minY || 1;
  return <><svg viewBox="0 0 580 260" role="img" aria-label={label} style={{ width: '100%' }}><title>{`${label}. Exact records available below.`}</title>{[0, .5, 1].map(f => <g key={f}><line x1="65" x2="530" y1={215 - f * 180} y2={215 - f * 180} stroke="currentColor" opacity=".15" /><text x="57" y={219 - f * 180} textAnchor="end" fill="currentColor" fontSize="10">{(minY + f * rangeY).toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 2 })}</text><text x={65 + f * 465} y="242" textAnchor="middle" fill="currentColor" fontSize="10">{(minX + f * rangeX).toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 2 })}</text></g>)}{points.map((p, i) => <circle key={i} cx={65 + (p.x - minX) / rangeX * 465} cy={215 - (p.y - minY) / rangeY * 180} r="4" fill="#b3d779" opacity=".8"><title>{`${p.label}: X ${p.x}, Y ${p.y}`}</title></circle>)}</svg><p className="chart-scope">{points.length} of {data.scatterSampling?.totalValid ?? points.length} valid loaded observations displayed. Selection: {data.scatterSampling?.method ?? 'all provided points'}. Axes: {data.scatterSampling?.domain ?? 'provided bounds'}. Source units; inspect loaded records for exact values.</p></>;
}
function Treemap({ data, label }: { data: TransformedChartData; label: string }) {
  const items = data.treemapData?.items ?? []; const total = items.reduce((sum, item) => sum + item.value, 0);
  const offsets = [0];
  for (const item of items) offsets.push(offsets[offsets.length - 1] + item.value);
  return total > 0 ? <><svg viewBox="0 0 540 240" role="img" aria-label={label} style={{ width: '100%' }}><title>{`${label}. Area is proportional to each displayed category.`}</title>{items.map((item, i) => { const width = item.value / total * 540; const left = offsets[i] / total * 540; return <rect key={item.id} x={left} y="0" width={width} height="240" fill={COLORS[i % COLORS.length]} stroke="#101312" strokeWidth="1"><title>{`${item.label}: ${item.value} (${item.percent.toFixed(1)}% of total)`}</title></rect>; })}</svg><p className="chart-scope">Slice-and-dice treemap: area normalized to the largest {items.length} positive categories shown.</p><ul>{items.map((item, i) => <li key={item.id}><span aria-hidden="true" style={{ color: COLORS[i % COLORS.length] }}>● </span>{item.label}: {item.value.toLocaleString()} ({item.percent.toFixed(1)}% of total)</li>)}</ul></> : <p>No positive values to display.</p>;
}

function GroupedBars({ data, label }: { data: TransformedChartData; label: string }) {
  const points = data.points ?? [];
  const categoryKey = (p: typeof points[number]) => p.categoryKey ?? JSON.stringify(p.label);
  const seriesKey = (p: typeof points[number]) => p.seriesKey ?? JSON.stringify(p.group ?? 'Value');
  const categories = [...new Map(points.map(p => [categoryKey(p), p.label])).entries()];
  const series = [...new Map(points.map(p => [seriesKey(p), p.group ?? 'Value'])).entries()].sort(([a], [b]) => a.localeCompare(b));
  const categoriesShown = categories.slice(0, 30);
  const shown = points.filter(p => categoriesShown.some(([key]) => key === categoryKey(p)));
  const palette = ['#D6FA43', '#67c8d0', '#c3a1ed', '#f1b66d', '#8bc8a4', '#ee9fac', '#c5d4e8'];
  const color = (key: string) => palette[Array.from(key).reduce((hash, c) => (hash * 31 + c.charCodeAt(0)) >>> 0, 0) % palette.length];
  const min = Math.min(0, ...shown.map(p => p.value));
  const max = Math.max(0, ...shown.map(p => p.value));
  const range = max - min || 1;
  const width = Math.max(580, categoriesShown.length * Math.max(70, series.length * 22));
  const band = (width - 100) / categoriesShown.length;
  const barWidth = band * .8 / series.length;
  const y = (value: number) => 220 - (value - min) / range * 180;
  const zero = y(0);
  return <div className="analytical-chart">
    <ul aria-label="Chart series legend" style={{ display: 'flex', gap: 16, flexWrap: 'wrap', listStyle: 'none', padding: 0 }}>
      {series.map(([key, name], i) => <li key={key}><span aria-hidden="true" style={{ display: 'inline-block', background: color(key), width: 12, height: 12, border: '1px solid #101313', marginRight: 6 }} />{i + 1}. {name}</li>)}
    </ul>
    <div style={{ overflowX: 'auto' }} tabIndex={0} aria-label="Scrollable grouped bar chart">
      <svg viewBox={`0 0 ${width} 280`} role="img" aria-label={label} style={{ width: '100%', minWidth: width }}>
        <title>{`${label}. Aligned categories; numbered series match the legend.`}</title>
        {[0, .5, 1].map(f => { const value = min + f * range; return <g key={f}><line x1="65" x2={width - 35} y1={y(value)} y2={y(value)} stroke="currentColor" opacity=".2" /><text x="57" y={y(value) + 4} textAnchor="end" fill="currentColor" fontSize="10">{value.toLocaleString(undefined, { notation: 'compact' })}</text></g>; })}
        <line x1="65" x2={width - 35} y1={zero} y2={zero} stroke="currentColor" />
        {categoriesShown.map(([key, name], categoryIndex) => <g key={key} data-category={key}>
          {series.map(([seriesId, seriesName], seriesIndex) => {
            const point = shown.find(p => categoryKey(p) === key && seriesKey(p) === seriesId);
            if (!point) return null;
            const x = 65 + categoryIndex * band + band * .1 + seriesIndex * barWidth;
            const description = `${name} / ${seriesName}: ${data.aggregation} ${data.metric} = ${point.value} ${data.unit}`;
            return <g key={seriesId} data-series={seriesId}><rect x={x} y={Math.min(y(point.value), zero)} width={Math.max(1, barWidth - 2)} height={Math.abs(y(point.value) - zero)} fill={color(seriesId)} stroke="#101313" strokeWidth=".6" aria-label={description}><title>{description}</title></rect><text x={x + barWidth / 2} y={point.value >= 0 ? y(point.value) - 4 : y(point.value) + 12} textAnchor="middle" fontSize="9" fill="currentColor">{seriesIndex + 1}</text></g>;
          })}
          <text x={65 + (categoryIndex + .5) * band} y="256" textAnchor="middle" fill="currentColor" fontSize="10"><title>{name}</title>{name.length > 16 ? name.slice(0, 14) + '…' : name}</text>
        </g>)}
      </svg>
    </div>
    <p className="chart-scope">{categoriesShown.length} of {categories.length} categories · {data.aggregation} · {data.unit}. Missing combinations are not plotted. Numbers identify series.</p>
    <details><summary>Exact chart values</summary><div className="studio-values"><table><caption>{label}</caption><thead><tr><th>Category</th><th>Series</th><th>Value</th></tr></thead><tbody>{points.map((p, i) => <tr key={i}><th scope="row">{p.label}</th><td>{p.group}</td><td>{p.value.toLocaleString(undefined, { maximumSignificantDigits: 15 })}</td></tr>)}</tbody></table></div></details>
  </div>;
}

function HistogramChart({ data, label }: { data: TransformedChartData; label: string }) {
  const bins = data.histogramBins ?? [];
  const summary = data.summaryMetrics;

  if (!bins.length) {
    return <p className="gallery-placeholder">No numeric distribution bins available.</p>;
  }

  const maxCount = Math.max(1, ...bins.map(b => b.count));
  const totalObs = summary?.count ?? bins.reduce((sum, b) => sum + b.count, 0);

  const svgWidth = 580;
  const svgHeight = 240;
  const paddingLeft = 52;
  const paddingRight = 20;
  const paddingTop = 25;
  const paddingBottom = 48;
  const plotWidth = svgWidth - paddingLeft - paddingRight;
  const plotHeight = svgHeight - paddingTop - paddingBottom;

  const binWidth = plotWidth / bins.length;
  const barGap = Math.max(2, Math.min(6, binWidth * 0.12));
  const actualBarWidth = Math.max(2, binWidth - barGap);

  const yTicks = [0, Math.round(maxCount / 2), maxCount];

  return (
    <div className="analytical-chart histogram-chart">
      {summary && (
        <div
          className="histogram-summary-strip"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            marginBottom: '10px',
            padding: '8px 12px',
            background: 'rgba(255, 255, 255, 0.05)',
            borderRadius: '6px',
            fontSize: '11px',
            color: 'var(--text-muted, #94a3b8)',
          }}
        >
          <div>
            <span>Obs: </span>
            <strong style={{ color: 'var(--text-h, #f8fafc)' }}>{totalObs.toLocaleString()}</strong>
          </div>
          {summary.sum !== undefined && (
            <div>
              <span>Sum: </span>
              <strong style={{ color: 'var(--text-h, #f8fafc)' }}>{summary.sum.toLocaleString()}</strong>
            </div>
          )}
          {summary.mean !== undefined && (
            <div>
              <span>Mean: </span>
              <strong style={{ color: 'var(--text-h, #f8fafc)' }}>{summary.mean.toLocaleString()}</strong>
            </div>
          )}
          {summary.median !== undefined && (
            <div>
              <span>Median: </span>
              <strong style={{ color: 'var(--text-h, #f8fafc)' }}>{summary.median.toLocaleString()}</strong>
            </div>
          )}
          {summary.min !== undefined && summary.max !== undefined && (
            <div>
              <span>Range: </span>
              <strong style={{ color: 'var(--text-h, #f8fafc)' }}>
                [{summary.min.toLocaleString()} to {summary.max.toLocaleString()}]
              </strong>
            </div>
          )}
          {summary.excluded_count !== undefined && summary.excluded_count > 0 && (
            <div>
              <span>Excluded/Null: </span>
              <strong style={{ color: '#f59e0b' }}>{summary.excluded_count.toLocaleString()}</strong>
            </div>
          )}
        </div>
      )}

      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        role="img"
        aria-label={label}
        style={{ width: '100%', overflow: 'visible' }}
      >
        <title>{`${label}. Histogram distribution showing observation frequencies across value ranges.`}</title>

        {yTicks.map((tick, i) => {
          const yPos = paddingTop + plotHeight - (tick / maxCount) * plotHeight;
          return (
            <g key={i}>
              <line
                x1={paddingLeft}
                x2={svgWidth - paddingRight}
                y1={yPos}
                y2={yPos}
                stroke="currentColor"
                opacity={tick === 0 ? 0.35 : 0.15}
                strokeDasharray={tick === 0 ? undefined : '3 3'}
              />
              <text
                x={paddingLeft - 8}
                y={yPos + 4}
                textAnchor="end"
                fill="currentColor"
                fontSize="10"
                opacity="0.8"
              >
                {tick.toLocaleString()}
              </text>
            </g>
          );
        })}

        <text
          x={paddingLeft}
          y={paddingTop - 10}
          textAnchor="start"
          fill="currentColor"
          fontSize="9"
          fontWeight="600"
          opacity="0.65"
          letterSpacing="0.05em"
        >
          FREQUENCY (OBSERVATIONS)
        </text>

        {bins.map((bin, i) => {
          const barHeight = maxCount > 0 ? (bin.count / maxCount) * plotHeight : 0;
          const x = paddingLeft + i * binWidth + barGap / 2;
          const y = paddingTop + plotHeight - barHeight;
          const tooltip = `${bin.label || `${bin.bin_start} to ${bin.bin_end}`}: ${bin.count.toLocaleString()} observations (${bin.percentage.toFixed(1)}%)`;

          return (
            <g key={i} className="histogram-bar-group">
              <rect
                x={x}
                y={y}
                width={actualBarWidth}
                height={Math.max(barHeight, bin.count > 0 ? 1 : 0)}
                fill="#b3d779"
                stroke="#101313"
                strokeWidth="0.75"
                rx="2"
                style={{
                  transition: 'opacity 0.15s, fill 0.15s',
                  cursor: 'pointer',
                }}
              >
                <title>{tooltip}</title>
              </rect>

              {bin.count > 0 && barHeight > 16 && (
                <text
                  x={x + actualBarWidth / 2}
                  y={y - 4}
                  textAnchor="middle"
                  fill="currentColor"
                  fontSize="9"
                  opacity="0.85"
                >
                  {bin.count > 999 ? `${(bin.count / 1000).toFixed(1)}k` : bin.count}
                </text>
              )}

              {(i === 0 || i === bins.length - 1 || bins.length <= 6 || i === Math.floor(bins.length / 2)) && (
                <text
                  x={x + actualBarWidth / 2}
                  y={paddingTop + plotHeight + 16}
                  textAnchor="middle"
                  fill="currentColor"
                  fontSize="9"
                  opacity="0.75"
                >
                  {bin.bin_start.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 })}
                </text>
              )}
            </g>
          );
        })}

        <text
          x={paddingLeft + plotWidth / 2}
          y={svgHeight - 4}
          textAnchor="middle"
          fill="currentColor"
          fontSize="10"
          fontWeight="500"
          opacity="0.8"
        >
          Value Ranges ({data.metric || 'Observations'})
        </text>
      </svg>

      <p className="chart-scope" style={{ marginTop: '8px' }}>
        Histogram distribution of {data.metric || 'values'} · {bins.length} value bins · {totalObs.toLocaleString()} valid observations
        {summary?.excluded_count ? ` · ${summary.excluded_count.toLocaleString()} excluded/null` : ''}
      </p>

      <details style={{ marginTop: '10px' }}>
        <summary>Exact frequency distribution table</summary>
        <div className="studio-values">
          <table>
            <caption>{label}</caption>
            <thead>
              <tr>
                <th scope="col">Bin Range</th>
                <th scope="col">Frequency (Count)</th>
                <th scope="col">Percentage</th>
              </tr>
            </thead>
            <tbody>
              {bins.map((bin, i) => (
                <tr key={i}>
                  <th scope="row">{bin.label || `${bin.bin_start} to ${bin.bin_end}`}</th>
                  <td>{bin.count.toLocaleString()}</td>
                  <td>{bin.percentage.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
