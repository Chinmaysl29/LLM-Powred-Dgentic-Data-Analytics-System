import type { ChartSpec } from '../../types/analysis';

/** Display the server's exact ordered points; no resampling or interpolation. */
export default function VerifiedTrendChart({ chart }: { chart: ChartSpec }) {
  const points = chart.points;
  if (points.length < 2 || points.length > 50 || points.some((p) => !Number.isFinite(p.value)))
    return null;
  if (points.some((p) => !/^\d{4}-(0[1-9]|1[0-2])$/.test(p.label))) return null;
  const months = points.map(
    (p) => Number(p.label.slice(0, 4)) * 12 + Number(p.label.slice(5, 7)) - 1,
  );
  if (months.some((month, index) => index > 0 && month <= months[index - 1])) return null;
  const low = Math.min(0, ...points.map((p) => p.value));
  const high = Math.max(0, ...points.map((p) => p.value));
  const span = high - low || 1;
  const x = (index: number) =>
    64 + ((months[index] - months[0]) / (months[months.length - 1] - months[0])) * 496;
  const y = (value: number) => 214 - ((value - low) / span) * 178;
  const path = points
    .map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(point.value)}`)
    .join(' ');
  const label = chart.chart_label || `${chart.y_field} by ${chart.x_field}`;
  return (
    <figure
      style={{
        margin: 0,
        padding: 20,
        borderRadius: 12,
        background: 'var(--surface-raised)',
        border: '1px solid var(--border)',
      }}
    >
      <figcaption style={{ fontWeight: 600, color: 'var(--text-h)' }}>{label}</figcaption>
      <svg
        viewBox="0 0 600 255"
        role="img"
        aria-label={label}
        style={{ width: '100%', color: 'var(--text-muted)' }}
      >
        <title>{`${label}. Exact values are listed below.`}</title>
        <line x1="64" x2="560" y1={y(0)} y2={y(0)} stroke="currentColor" opacity="0.3" />
        <text x="56" y="40" textAnchor="end" fontSize="10" fill="currentColor">
          {high.toLocaleString()}
        </text>
        <text x="56" y="218" textAnchor="end" fontSize="10" fill="currentColor">
          {low.toLocaleString()}
        </text>
        <path d={path} fill="none" stroke="var(--brand-lime)" strokeWidth="2" />
        {points.map((point, index) => (
          <circle key={index} cx={x(index)} cy={y(point.value)} r="3" fill="var(--brand-lime)">
            <title>{`${point.label}: ${String(point.value)}`}</title>
          </circle>
        ))}
        <text x="64" y="243" fontSize="11" fill="currentColor">
          {points[0].label}
        </text>
        <text x="560" y="243" textAnchor="end" fontSize="11" fill="currentColor">
          {points[points.length - 1].label}
        </text>
      </svg>
      <details style={{ color: 'var(--text)', fontSize: 12 }}>
        <summary>View exact values</summary>
        <table style={{ width: '100%', textAlign: 'left' }}>
          <thead>
            <tr>
              <th scope="col">{chart.x_field}</th>
              <th scope="col">{chart.y_field}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point, index) => (
              <tr key={index}>
                <th scope="row">{point.label}</th>
                <td>{String(point.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
