/** Real local-auth browser journey against the isolated synthetic API; no response mocks. */
import { chromium } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const account = JSON.parse(await readFile('/verification/learning-browser-account.json', 'utf8'));
const output = '/verification/learning-evidence/browser';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ args: ['--disable-dev-shm-usage'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
const checks = [];
page.on('pageerror', error => errors.push(error.message));
const base = 'http://frontend-verify:5173';

async function noAlert() {
  assert.equal(await page.getByRole('alert').count(), 0, await page.getByRole('alert').allTextContents());
}
async function tab(name) { await page.getByRole('button', { name, exact: true }).click(); }

try {
  await page.goto(`${base}/verified-learning`);
  await page.waitForURL('**/login');
  checks.push('unauthenticated verified-learning navigation redirects to login');
  await page.locator('#login-email').fill(account.email);
  await page.locator('#login-password').fill(account.password);
  await page.locator('button[type=submit]').click();
  await page.waitForURL('**/dashboard', { timeout: 30000 });
  checks.push('real synthetic backend password login succeeds');
  await page.goto(`${base}/verified-learning?workspace=${account.workspace_id}`);
  await page.getByRole('heading', { name: 'Start a verified analysis' }).waitFor();
  await page.getByLabel('Workspace', { exact: true }).selectOption(account.workspace_id);
  await page.getByLabel('Dataset', { exact: true }).selectOption(account.dataset_id);
  await page.getByLabel('Objective', { exact: true }).fill('Total amount by region');
  await page.getByLabel('Metric column', { exact: true }).fill('amount');
  await page.getByLabel('Group by (optional)', { exact: true }).fill('region');
  await page.getByLabel('Units', { exact: true }).fill('USD');
  await page.getByLabel('Currency (optional)', { exact: true }).fill('USD');
  await tab('Controls');
  await page.getByRole('button', { name: 'collection', exact: true }).click();
  await page.getByText('Mode: collection', { exact: false }).waitFor();
  checks.push('authorized collection control saved through UI');
  await tab('Analysis');
  await page.getByRole('button', { name: 'Run with verification', exact: true }).click();
  await page.getByRole('heading', { name: 'Verified within checked scope' }).waitFor({ timeout: 45000 });
  await page.getByRole('heading', { name: 'Answer evidence' }).waitFor();
  await page.getByRole('cell', { name: '180', exact: true }).waitFor();
  await page.getByRole('cell', { name: '1000', exact: true }).waitFor();
  // This explicit source aggregate includes cancelled records; no net-revenue semantics were asserted.
  checks.push('real seven-stage worker completes; independently known group totals 180 and 1000 appear');
  await page.screenshot({ path: `${output}/analysis-evidence.png`, fullPage: true });
  const savedUrl = page.url();
  await page.reload();
  await page.getByRole('heading', { name: 'Verified within checked scope' }).waitFor();
  assert.equal(page.url(), savedUrl);
  checks.push('URL-pinned run and evidence restore after refresh');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download verified report', exact: true }).click();
  const download = await downloadEvent;
  await download.saveAs(`${output}/verified-report.json`);
  const report = JSON.parse(await readFile(`${output}/verified-report.json`, 'utf8'));
  assert.deepEqual(report.answer.rows, [{ region: 'North', value: 180 }, { region: 'South', value: 1000 }]);
  checks.push('authorized UI report download contains the exact validated result');
  await page.getByText('Give structured feedback', { exact: true }).click();
  await page.getByLabel('Correction or supporting explanation', { exact: true }).fill('Synthetic calculation feedback. Result matches independent reference.');
  await page.getByRole('button', { name: 'Save feedback', exact: true }).click();
  await page.getByText('Feedback saved. It is not a verified numeric label.', { exact: true }).waitFor();
  checks.push('structured feedback persists without claiming a verified numeric label');
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await tab('Lessons');
  await page.getByRole('button', { name: 'amount: exact_decimal_parse', exact: true }).first().click();
  await page.getByLabel('Review reason', { exact: true }).fill('Synthetic reviewer confirms scoped decimal correction and independent checks.');
  await page.getByRole('button', { name: 'Verify', exact: true }).click();
  await page.getByText('Verified lesson saved.', { exact: true }).waitFor();
  await page.getByText('Passed: 3 positive cases and 8 counterexamples.', { exact: false }).waitFor();
  await page.getByRole('button', { name: 'Activate', exact: true }).click();
  await page.getByRole('heading', { name: 'active · Revision 3' }).waitFor();
  await page.screenshot({ path: `${output}/lesson-review.png`, fullPage: true });
  checks.push('real independent verification, authorized activation and immutable revisions visible');
  await tab('Evaluation');
  await page.getByRole('button', { name: 'Freeze active lesson bundle', exact: true }).click();
  await page.getByText('Candidate frozen. Subsequent lessons are excluded.', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Run paired evaluation', exact: true }).isDisabled(), true);
  checks.push('candidate freeze succeeds; absent held-out cases prevent evaluation submission');
  await page.screenshot({ path: `${output}/evaluation-empty.png`, fullPage: true });
  await tab('Controls');
  await page.getByRole('button', { name: 'Rollback to validated baseline', exact: true }).click();
  await page.getByText('Application stopped. Baseline active; previous bundle retained in shadow for review.', { exact: true }).waitFor();
  checks.push('authorized rollback stops application and exposes baseline state');
  await noAlert();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${output}/mobile-controls.png`, fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'mobile page must not overflow');
  checks.push('390px viewport has no horizontal document overflow');
  assert.deepEqual(errors, []);
  checks.push('no uncaught browser runtime errors');
  await writeFile(`${output}/browser-results.json`, JSON.stringify({ checks, errors,
    authentication: 'Real local backend password identity; hosted Supabase not exercised', responsesMocked: false }, null, 2));
  console.log(JSON.stringify({ passed: checks.length, checks }, null, 2));
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png`, fullPage: true });
  await writeFile(`${output}/failure.json`, JSON.stringify({ url: page.url(), title: await page.title(), body: (await page.locator('body').innerText()).slice(0, 2500), errors }, null, 2));
  throw error;
} finally { await browser.close(); }
