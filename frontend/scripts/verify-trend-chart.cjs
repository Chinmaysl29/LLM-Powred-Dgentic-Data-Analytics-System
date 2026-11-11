// Render the actual TSX component with React; verify data-preserving SVG output.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const errors = [];
console.error = (...args) => errors.push(args.join(' '));
const source = fs.readFileSync('src/components/analytics/VerifiedTrendChart.tsx', 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText;
const exported = {};
new Function('require', 'exports', compiled)(require, exported);
const chart = { chart_type: 'line', x_field: 'month', y_field: 'amount', chart_label: 'Monthly amount', points: [
  { label: '2025-01', value: -10 }, { label: '2025-02', value: 0 }, { label: '2025-04', value: 30 }
] };
const original = JSON.stringify(chart);
const markup = renderToStaticMarkup(React.createElement(exported.default, { chart }));
assert.equal(JSON.stringify(chart), original);
assert.match(markup, /role="img"/);
assert.match(markup, /<td>-10<\/td>/);
assert.match(markup, /<td>0<\/td>/);
assert.match(markup, /<td>30<\/td>/);
const xs = Array.from(markup.matchAll(/<circle[^>]*cx="([^"]+)"/g), match => Number(match[1]));
assert.equal(xs.length, 3);
assert.ok(Math.abs((xs[1] - xs[0]) * 2 - (xs[2] - xs[1])) < 1e-9, 'Missing March must retain its time-axis gap');
for (const points of [[{ label: '2025-01', value: NaN }, chart.points[1]], [chart.points[1], chart.points[0]],
  [{ label: '2025-13', value: 1 }, chart.points[1]], [chart.points[0], chart.points[0]]]) {
  assert.equal(renderToStaticMarkup(React.createElement(exported.default, { chart: { ...chart, points } })), '');
}
const flat = renderToStaticMarkup(React.createElement(exported.default, { chart: { ...chart, points: chart.points.map(p => ({ ...p, value: 0 })) } }));
assert.ok(!/NaN|Infinity/.test(flat));
assert.deepEqual(errors, [], 'React rendered without warnings');
console.log('PASS: actual React trend renderer preserves values, negative/zero series, time gaps and accessible labels; invalid series rejected');
