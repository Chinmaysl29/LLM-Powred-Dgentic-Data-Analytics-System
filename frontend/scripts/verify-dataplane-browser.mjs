import { chromium } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const account = JSON.parse(await readFile('/verification/learning-browser-account.json', 'utf8'));
const output = '/verification/dataplane-browser';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: '/usr/bin/chromium-browser', args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
const errors = [], checks = [];
page.on('pageerror', e => errors.push(e.message));
const base = 'http://frontend-verify:5173';
try {
  await page.goto(base + '/data-health');
  await page.waitForURL('**/login');
  await page.locator('#login-email').fill(account.email);
  await page.locator('#login-password').fill(account.password);
  await page.locator('button[type=submit]').click();
  await page.waitForURL('**/dashboard', { timeout: 60000 });
  checks.push('authentication required and local login succeeds');
  await page.goto(base + '/data-health?workspace=' + account.workspace_id);
  await page.getByRole('heading', { name: 'Upload for background processing' }).waitFor();
  await page.getByLabel('Dataset file').setInputFiles({
    name: 'browser-dataplane.csv', mimeType: 'text/csv',
    buffer: Buffer.from('region,amount\nNorth,10\nSouth,20\nNorth,5\nSouth,\n'),
  });
  await page.getByRole('button', { name: 'Upload dataset', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('select[aria-label="Snapshot"]')?.options.length > 1, { timeout: 60000 });
  const snapshotSelect = page.getByLabel('Snapshot', { exact: true });
  const snapshot = await snapshotSelect.locator('option').nth(1).getAttribute('value');
  await snapshotSelect.selectOption(snapshot);
  checks.push('real streamed upload processed by the separate worker');
  const definitions = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Define a metric', exact: true }) });
  await definitions.getByLabel('Name', { exact: true }).fill('source_amount');
  await definitions.getByLabel('Column', { exact: true }).selectOption('amount');
  await definitions.getByLabel('Definition', { exact: true }).fill('Sum the source amount; exclude missing values.');
  await definitions.getByRole('button', { name: 'Save definition' }).click();
  await page.waitForFunction(() => Array.from(document.querySelectorAll('select')).some(s => Array.from(s.options).some(o => o.text === 'source_amount')));
  const calculation = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Calculate a result', exact: true }) });
  await calculation.getByLabel('Metric', { exact: true }).selectOption({ label: 'source_amount' });
  await calculation.getByLabel('Group by', { exact: true }).selectOption('region');
  await calculation.getByRole('button', { name: 'Calculate', exact: true }).click();
  await page.getByRole('heading', { name: 'Calculated result', exact: true }).first().waitFor({ timeout: 60000 });
  const result = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Calculated result', exact: true }) }).first();
  await result.getByRole('cell', { name: '15', exact: true }).waitFor();
  await result.getByRole('cell', { name: '20', exact: true }).waitFor();
  checks.push('registered metric yields independently expected grouped totals');
  const [download] = await Promise.all([page.waitForEvent('download'), result.getByRole('button', { name: 'Download evidence PDF' }).click()]);
  await download.saveAs(output + '/evidence.pdf');
  assert.ok((await readFile(output + '/evidence.pdf')).subarray(0, 4).toString() === '%PDF');
  checks.push('authenticated evidence PDF downloads');
  await page.getByRole('button', { name: 'Run health check' }).click();
  await page.getByRole('heading', { name: 'Health findings' }).first().waitFor({ timeout: 60000 });
  await page.getByText('amount: 1 missing (25.0%)', { exact: true }).waitFor();
  const cleaning = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Propose a cleaning change', exact: true }) });
  await cleaning.getByLabel('Column', { exact: true }).selectOption('amount');
  await cleaning.getByLabel('Reason', { exact: true }).fill('Exclude missing amount in a new version');
  await cleaning.getByRole('button', { name: 'Test proposal' }).click();
  await page.getByRole('heading', { name: 'Cleaning approval' }).first().waitFor({ timeout: 60000 });
  await page.getByText('Sample: 4 rows before, 3 after, 1 removed.', { exact: false }).waitFor();
  await page.getByRole('button', { name: 'Approve and create new version' }).first().click();
  await page.waitForFunction(() => document.querySelector('select[aria-label="Snapshot"]')?.options.length > 2, { timeout: 60000 });
  checks.push('health missingness, sample review, approval and new cleaned snapshot work');
  await page.screenshot({ path: output + '/desktop.png', fullPage: true });
  await page.getByLabel('Workspace', { exact: true }).selectOption('');
  await page.waitForFunction(() => !Array.from(document.querySelectorAll('h2')).some(h => h.textContent === 'Calculated result'));
  assert.equal(await page.getByRole('heading', { name: 'Calculated result', exact: true }).count(), 0);
  await page.getByLabel('Workspace', { exact: true }).selectOption(account.workspace_id);
  await page.getByRole('heading', { name: 'Calculated result', exact: true }).first().waitFor();
  await page.route('**/api/v1/dataplane/dashboard?**', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Synthetic outage"}' }));
  await page.getByRole('alert').waitFor({ timeout: 15000 });
  assert.equal(await page.getByRole('heading', { name: 'Calculated result', exact: true }).count(), 0);
  await page.unroute('**/api/v1/dataplane/dashboard?**');
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await page.getByRole('heading', { name: 'Calculated result', exact: true }).first().waitFor();
  checks.push('workspace change and outage clear stale results; retry recovers');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: output + '/mobile.png', fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'mobile overflow');
  assert.deepEqual(errors, []);
  checks.push('mobile layout fits viewport; no browser errors');
  await writeFile(output + '/results.json', JSON.stringify({ passed: true, checks }, null, 2));
  console.log(JSON.stringify({ passed: true, checks }));
} catch (e) {
  await page.screenshot({ path: output + '/failure.png', fullPage: true });
  throw e;
} finally { await browser.close(); }

