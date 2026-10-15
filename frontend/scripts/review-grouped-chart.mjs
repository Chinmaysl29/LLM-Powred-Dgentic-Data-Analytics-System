// Isolated renderer fixture, not a substitute for authenticated app/API acceptance.
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { chromium } from '@playwright/test';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const source = await readFile(new URL('../src/components/analytics/ResultChart.tsx', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const exports = {};
new Function('exports', 'require', js)(exports, name => name.includes('animatedGlow') ? {} : require(name));
const points = [{ label: 'North', group: 'A', value: 10 }, { label: 'North', group: 'B', value: 20 }, { label: 'South', group: 'A', value: -5 }, { label: 'South', group: 'C', value: 0 }];
const chart = renderToStaticMarkup(createElement(exports.default, { label: 'Fixture: revenue by region and product', data: { type: 'Bar', isValid: true, points, metric: 'revenue', aggregation: 'sum', unit: 'source units' } }));
const directory = new URL('../.ui-review/recovery/', import.meta.url);
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const results = [];
try {
  const page = await browser.newPage();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.setContent(`<html><head><style>body{margin:0;padding:20px;background:#f1f2ec;font:16px system-ui;color:#172019}main{box-sizing:border-box;max-width:1100px;padding:24px;border-radius:16px;background:white;margin:auto}h1{font-size:24px}.studio-values{overflow:auto}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:8px;border-bottom:1px solid #ddd}.chart-scope{font-size:14px}svg{display:block}details{margin-top:20px}</style></head><body><main><h1>Isolated grouped-bar regression fixture</h1><p>Two regions, three products, missing combinations, a negative value and zero.</p>${chart}</main></body></html>`);
    await page.getByText('Exact chart values', { exact: true }).click();
    const result = await page.evaluate(() => {
      const bars = [...document.querySelectorAll('rect')];
      const groups = [...document.querySelectorAll('[data-category]')];
      const a = [...document.querySelectorAll('[data-series]')].filter(g => g.getAttribute('data-series') === '"A"');
      return { width: innerWidth, bars: bars.length, categories: groups.length, consistentSeriesColor: a[0].querySelector('rect').getAttribute('fill') === a[1].querySelector('rect').getAttribute('fill'), categoryBandsOrdered: Number(bars[1].getAttribute('x')) < Number(bars[2].getAttribute('x')), zeroHeight: Number(bars[3].getAttribute('height')) === 0, overflow: document.documentElement.scrollWidth > innerWidth };
    });
    if (result.bars !== 4 || result.categories !== 2 || !result.consistentSeriesColor || !result.categoryBandsOrdered || !result.zeroHeight || result.overflow) throw new Error(JSON.stringify(result));
    results.push(result);
    await page.screenshot({ path: fileURLToPath(new URL(`grouped-fixture-${width}.png`, directory)), fullPage: true });
  }
  await writeFile(new URL('grouped-fixture.json', directory), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results));
} finally { await browser.close(); }
