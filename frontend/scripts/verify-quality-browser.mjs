/** UI regression checks with explicitly synthetic HTTP responses; no live database writes. */
import { chromium, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

const base = process.env.QUALITY_BASE_URL || 'http://dataanalyst-quality-node:5173';
const output = process.env.QUALITY_OUTPUT || '/verification/quality-browser';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: '/usr/bin/chromium-browser', args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [], checks = [];
page.on('pageerror', error => errors.push(error.message));
const datasets = ['a', 'b', 'doc'].map(id => ({
  dataset_id: id, dataset_name: `Fixture ${id}`, file_name: `${id}.csv`,
  file_type: id === 'doc' ? 'pdf' : 'csv', row_count: 2, column_count: 2,
  created_at: '2026-01-01T00:00:00Z', status: 'ready',
}));
const reports = [{ id: 'r1', title: 'Fixture report', created_at: '2026-01-01T00:00:00Z', markdown: 'Stored fixture evidence' }];
const session = title => ({ session_id: title, title, latest_status: 'complete', turn_count: 0 });
const eda = id => ({ eda_results: {
  dataset_summary: { dataset_id: id, dataset_type: 'tabular', business_domain: `Fixture domain ${id}`, row_count: 2, column_count: 1, column_names: ['region'], numeric_columns: [], categorical_columns: ['region'], datetime_columns: [], data_categories: [], memory_usage_mb: 0.01, is_sampled: false },
  statistics: {}, distributions: {}, outliers: {}, categorical_analysis: {}, business_insights: [],
  correlations: { correlation_matrix: {}, strongest_correlations: [] },
  trends: { has_time_series: false, date_columns: [], trends: [] },
  missing_values: { total_missing_cells: 0, missing_percentage: 0, affected_columns_count: 0, affected_columns: [], column_details: {} },
} });
let registryFailure = false, reportFailure = false, edaFailure = false;
let holdInsight = false, releaseInsight, holdSession = false, releaseSession;
let edaCalls = 0;
await page.route('**/api/v1/**', async route => {
  const url = new URL(route.request().url());
  const path = url.pathname;
  let body = [], status = 200;
  if (path === '/api/v1/auth/me') body = { id: 'quality-fixture', email: 'quality@example.invalid', full_name: 'Quality Fixture' };
  else if (path === '/api/v1/datasets') { body = registryFailure ? { detail: 'Synthetic registry outage' } : datasets; status = registryFailure ? 422 : 200; }
  else if (path.endsWith('/recommendations')) {
    const id = path.split('/')[4];
    if (holdInsight && id === 'a') await new Promise(resolve => { releaseInsight = resolve; });
    body = { recommendations: [{ recommendation_id: id, description: `Finding ${id}`, suggested_action: 'Inspect fixture', severity: 'low' }] };
  } else if (path === '/api/v1/os/reports/studio/history') { body = reportFailure ? { detail: 'Synthetic report outage' } : reports; status = reportFailure ? 422 : 200; }
  else if (path === '/api/v1/analysis/sessions') {
    const search = url.searchParams.get('search') || 'initial';
    if (holdSession && search === 'older') await new Promise(resolve => { releaseSession = resolve; });
    body = [session(`Session ${search}`)];
  } else if (path.endsWith('/preview')) {
    body = { rows: [{ region: 'North', revenue: 10 }, { region: 'South', revenue: 20 }], total_rows: 2, column_types: { region: 'object', revenue: 'int64' } };
  } else if (path.endsWith('/chart-data')) {
    // Exercise the documented local fallback after a chart-service error.
    body = { detail: 'Synthetic chart outage' }; status = 422;
  } else if (path.startsWith('/api/v1/eda/')) {
    edaCalls++;
    body = edaFailure ? { detail: 'Synthetic EDA outage' } : eda(path.split('/').at(-1));
    status = edaFailure ? 422 : 200;
  } else if (path === '/api/v1/os/dashboards') {
    body = [{ id: 'dash1', title: 'Finite fixture dashboard', created_at: '2026-01-01T00:00:00Z', population_size: 2, filtered_rows: 2, kpis: [{ id: 'valid', label: 'Source total', value: 30 }, { id: 'null', label: 'Missing metric', value: null }] }];
  }
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
});

try {
  registryFailure = true;
  await page.goto(`${base}/dashboard`);
  await expect(page.getByText('Synthetic registry outage', { exact: true })).toBeVisible();
  registryFailure = false;
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByText('Fixture a', { exact: true })).toBeVisible();
  checks.push('overview initial failure and retry load the registry');

  await page.keyboard.press('Control+k');
  const search = page.getByRole('textbox', { name: 'Command search' });
  await search.fill('dataset'); await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Escape'); await page.keyboard.press('Control+k');
  await expect(search).toHaveValue('');
  await expect(page.locator('[data-idx="0"]')).toHaveAttribute('aria-selected', 'true');
  await search.fill('reports');
  await expect(page.locator('[data-idx="0"]')).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('Escape');
  checks.push('command palette resets search and keyboard selection on reopening');

  holdInsight = true;
  await page.goto(`${base}/insights`);
  await expect.poll(() => Boolean(releaseInsight)).toBe(true);
  await page.getByLabel('Dataset', { exact: true }).selectOption('b');
  await expect(page.getByRole('heading', { name: 'Finding b' })).toBeVisible();
  releaseInsight(); holdInsight = false;
  await page.waitForTimeout(100);
  await expect(page.getByRole('heading', { name: 'Finding a' })).toHaveCount(0);
  await page.getByLabel('Dataset', { exact: true }).selectOption('');
  await expect(page.getByRole('heading', { name: 'Finding b' })).toHaveCount(0);
  await page.getByLabel('Dataset', { exact: true }).selectOption('b');
  await expect(page.getByRole('heading', { name: 'Finding b' })).toBeVisible();
  checks.push('insights ignore a late response and clear results when no dataset is selected');

  await page.goto(`${base}/analysis`);
  const sessionSearch = page.getByPlaceholder(/Search previous questions/);
  holdSession = true; await sessionSearch.fill('older');
  await expect.poll(() => Boolean(releaseSession)).toBe(true);
  await sessionSearch.fill('newer');
  await expect(page.getByText('Session newer', { exact: true })).toBeVisible();
  releaseSession(); holdSession = false;
  await page.waitForTimeout(100);
  await expect(page.getByText('Session older', { exact: true })).toHaveCount(0);
  checks.push('session search ignores out-of-order completions');

  reportFailure = true; await page.goto(`${base}/reports/r1`);
  await expect(page.getByRole('alert')).toContainText('Synthetic report outage');
  reportFailure = false; await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByText('Stored fixture evidence', { exact: true })).toBeVisible();
  await page.goto(`${base}/reports`);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeVisible();
  checks.push('report detail recovers after retry and report lists refresh');

  edaFailure = true; await page.goto(`${base}/eda?dataset=a`);
  await expect(page.getByText('Synthetic EDA outage', { exact: true })).toBeVisible();
  edaFailure = false; await page.getByRole('button', { name: 'Re-run EDA analysis' }).click();
  await expect(page.getByText('Fixture domain a', { exact: true })).toBeVisible();
  await page.getByLabel('Select dataset for EDA').selectOption('b');
  await expect(page.getByText('Fixture domain b', { exact: true })).toBeVisible();
  await expect(page.getByText('Fixture domain a', { exact: true })).toHaveCount(0);
  assert.ok(edaCalls >= 3);
  checks.push('EDA recovers, refreshes and switches dataset without stale results');

  await page.goto(`${base}/visualizations`);
  await expect(page.getByText(/Preview sample: up to 2 loaded records/)).toBeVisible();
  await page.getByRole('combobox', { name: /Data source/ }).selectOption('doc');
  await expect(page.getByText(/Unstructured Document Source/)).toBeVisible();
  await expect(page.getByText(/Preview sample: up to/)).toHaveCount(0);
  await page.getByRole('button', { name: /Switch to Tabular Dataset/ }).click();
  await expect(page.getByText(/Preview sample: up to 2 loaded records/)).toBeVisible();
  checks.push('visualization document selection clears rows and tabular selection restores local chart fallback');

  await page.goto(`${base}/dashboard-studio`);
  await expect(page.getByRole('heading', { name: 'Finite fixture dashboard' })).toBeVisible();
  await expect(page.getByText('Source total', { exact: true })).toBeVisible();
  await expect(page.getByText('Missing metric', { exact: true })).toHaveCount(0);
  checks.push('dashboard studio excludes null metrics without inventing values');

  await page.goto(`${base}/scripts/quality-toast.html`);
  await page.getByRole('button', { name: 'Timed toast' }).click();
  await expect(page.getByText('Timed fixture', { exact: true })).toBeVisible();
  await expect(page.getByText('Timed fixture', { exact: true })).toHaveCount(0, { timeout: 5000 });
  await page.getByRole('button', { name: 'Persistent toast' }).click();
  await expect(page.getByText('Persistent fixture', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Dismiss notification' }).click();
  await expect(page.getByText('Persistent fixture', { exact: true })).toHaveCount(0);
  checks.push('toast auto-dismiss and manual dismissal work in React StrictMode');

  assert.deepEqual(errors, []);
  const result = { passed: true, fixture_mode: 'mock HTTP, no real provider/database', checks, page_errors: errors };
  await writeFile(`${output}/results.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png`, fullPage: true });
  console.error(JSON.stringify({ checks, page_errors: errors }));
  throw error;
} finally { await browser.close(); }
