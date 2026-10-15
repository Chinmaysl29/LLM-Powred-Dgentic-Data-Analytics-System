// Run only against the isolated acceptance stack after its API and worker restart.
// node scripts/verify-pdf-lifecycle.mjs [--verify-existing]
// Credentials come only from ACCEPTANCE_A_EMAIL/PASSWORD and B equivalents.
import { chromium, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createHash } from 'node:crypto';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(frontend, '.ui-review/integration-acceptance');
const base = process.env.ACCEPTANCE_BASE_URL || 'http://localhost:5174';
const expectedApiPort = process.env.ACCEPTANCE_API_PORT || '8011';
const verifyExisting = process.argv.includes('--verify-existing');
const stateFile = path.join(output, 'pdf-lifecycle-state.json');
const evidenceFile = path.join(output, verifyExisting ? 'pdf-lifecycle-after-restart.json' : 'pdf-lifecycle.json');
const fixture = path.resolve(frontend, '../tests/fixtures/integration/business_definitions.pdf');
const parseJson = text => JSON.parse(text.replace(/^\uFEFF/, ''));
const baseUrl = new URL(base);
assert.ok(['localhost', '127.0.0.1'].includes(baseUrl.hostname) && baseUrl.port === '5174', 'Acceptance requires the isolated frontend on port 5174');
for (const account of ['A', 'B']) for (const field of ['EMAIL', 'PASSWORD']) {
  assert.ok(process.env[`ACCEPTANCE_${account}_${field}`], `Missing acceptance ${account} ${field.toLowerCase()} environment variable`);
}
await mkdir(output, { recursive: true });
const workspaces = parseJson(await readFile(path.join(output, 'workspaces.json'), 'utf8'));
const ownerWorkspace = workspaces.find(w => w.account === 'A');
assert.ok(ownerWorkspace?.workspaceId, 'Account A workspace fixture is required');
const evidence = { mode: verifyExisting ? 'after-restart' : 'fresh-upload', startedAt: new Date().toISOString(), checks: [], indexingStates: [], screenshots: [], status: 'RUNNING' };
let record = verifyExisting ? parseJson(await readFile(stateFile, 'utf8')) : null;
let currentStep = 'launch';
let panel;
const pendingObservations = new Set();
const browser = await chromium.launch({ channel: process.env.ACCEPTANCE_BROWSER_CHANNEL || 'msedge', headless: true });
console.log('Acceptance browser launched');

async function authenticatedPage(account) {
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1365, height: 1000 } });
  // Prevent an incorrectly configured Vite instance from writing customer data.
  await context.route('**/api/v1/datasets/**', async route => {
    const url = new URL(route.request().url());
    if (!['localhost', '127.0.0.1'].includes(url.hostname) || url.port !== expectedApiPort) {
      evidence.checks.push({ id: 'ISOLATED_API_TARGET', status: 'FAIL' });
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  console.log(`Verifying account ${account} login`);
  await page.goto(`${base}/login`);
  await page.locator('#login-email').fill(process.env[`ACCEPTANCE_${account}_EMAIL`]);
  await page.locator('#login-password').fill(process.env[`ACCEPTANCE_${account}_PASSWORD`]);
  await page.getByRole('button', { name: 'Sign in to your account', exact: true }).click();
  await page.waitForURL('**/dashboard', { timeout: 60_000 });
  console.log(`Account ${account} login verified`);
  evidence.checks.push({ id: `FORM_LOGIN_${account}`, status: 'PASS' });
  return { page, context };
}

function observeIndexing(page) {
  page.on('response', response => {
    const url = new URL(response.url());
    if (!record || !url.pathname.endsWith(`/datasets/${record.datasetId}/indexing`) || response.status() !== 200) return;
    const task = (async () => {
      try {
        const state = await response.json();
        // Retain only lifecycle metadata. No raw API body, document text or tokens.
        evidence.indexingStates.push({ at: new Date().toISOString(), status: state.status,
          attempt: state.attempt, datasetVersion: state.dataset_version,
          indexedChunkCount: state.indexed_chunk_count, errorCode: state.error_code });
      } catch { /* A page closing may cancel an observation; UI assertions remain authoritative. */ }
    })();
    pendingObservations.add(task);
    void task.finally(() => pendingObservations.delete(task));
  });
}

async function checkQuestionAndCitation(page, prefix) {
  await panel.getByLabel('Ask this PDF').fill('How should missing revenue be handled?');
  await panel.getByRole('button', { name: 'Ask document', exact: true }).click();
  const answer = panel.getByRole('article', { name: 'Document answer' });
  await expect(answer).toBeVisible({ timeout: 120_000 });
  const text = (await answer.innerText()).replace(/\s+/g, ' ');
  assert.match(text, /exclude missing revenue from mean/i, 'Answer must contain independently specified missing-value policy');
  assert.match(text, /never replace it with zero/i, 'Answer must preserve the prohibition on zero substitution');
  await expect(answer.getByRole('heading', { name: 'Sources', exact: true })).toBeVisible();
  const citations = answer.locator('li');
  assert.ok(await citations.count() > 0, 'Grounded answer must expose a source citation');
  evidence.checks.push({ id: `${prefix}_GROUNDED_ANSWER`, status: 'PASS', citationCount: await citations.count(), expectedPolicyMatched: true });
  const downloadPromise = page.waitForEvent('download');
  await answer.getByRole('button', { name: 'Download cited source', exact: true }).first().click();
  const download = await downloadPromise;
  const downloaded = path.join(output, `${prefix.toLowerCase()}-cited-source.pdf`);
  await download.saveAs(downloaded);
  const bytes = await readFile(downloaded);
  assert.equal(bytes.subarray(0, 5).toString(), '%PDF-');
  const expected = await readFile(fixture);
  assert.equal(createHash('sha256').update(bytes).digest('hex'), createHash('sha256').update(expected).digest('hex'), 'Downloaded citation must equal the uploaded original PDF');
  evidence.checks.push({ id: `${prefix}_AUTHENTICATED_CITATION_DOWNLOAD`, status: 'PASS', bytes: bytes.length, matchesOriginal: true });
}

try {
  currentStep = 'owner-login';
  const { page, context } = await authenticatedPage('A');
  observeIndexing(page);
  try {
    if (!verifyExisting) {
      currentStep = 'upload-pdf';
      await page.goto(`${base}/datasets/upload`);
      await page.locator('input[type=file]').setInputFiles(fixture);
      const uploadResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/datasets/upload' && response.request().method() === 'POST', { timeout: 120_000 });
      await page.getByRole('button', { name: 'Upload 1 file', exact: true }).click();
      const response = await uploadResponse;
      assert.equal(response.status(), 201, 'PDF upload must return HTTP 201');
      const uploaded = await response.json();
      const dataset = uploaded.dataset ?? uploaded;
      record = { datasetId: dataset.dataset_id, version: dataset.version ?? 1, workspaceId: ownerWorkspace.workspaceId };
      assert.ok(record.datasetId, 'Upload must return a dataset identity');
      await writeFile(stateFile, JSON.stringify(record, null, 2));
      evidence.checks.push({ id: 'PDF_UPLOAD_UI', status: 'PASS', httpStatus: 201 });
    }
    evidence.datasetId = record.datasetId;
    currentStep = 'open-document';
    await page.goto(`${base}/datasets/${encodeURIComponent(record.datasetId)}`);
    panel = page.getByRole('region', { name: 'Document indexing and questions' });
    await expect(panel).toBeVisible({ timeout: 30_000 });
    await panel.getByLabel('Document version', { exact: true }).selectOption(String(record.version));
    if (!verifyExisting) {
      currentStep = 'bind-workspace-ui';
      const selector = panel.getByLabel('Workspace for this document');
      await expect(selector).toBeVisible({ timeout: 30_000 });
      await expect(panel.getByLabel('Ask this PDF')).toBeDisabled();
      await expect(selector.locator(`option[value="${ownerWorkspace.workspaceId}"]`)).toHaveCount(1, { timeout: 30_000 });
      await selector.selectOption(ownerWorkspace.workspaceId);
      await panel.getByRole('button', { name: 'Assign workspace and index', exact: true }).click();
      evidence.checks.push({ id: 'EXPLICIT_WORKSPACE_ASSIGNMENT_UI', status: 'PASS' });
    }
    currentStep = 'wait-ready';
    await expect(panel.getByRole('status')).toContainText('Indexing status: READY', { timeout: 120_000 });
    await expect(panel.getByLabel('Ask this PDF')).toBeEnabled();
    evidence.checks.push({ id: verifyExisting ? 'READY_AFTER_SERVICE_RESTART' : 'DURABLE_INDEX_READY_UI', status: 'PASS' });
    currentStep = 'question-citation-download';
    await checkQuestionAndCitation(page, verifyExisting ? 'RESTART' : 'INITIAL');
    const screenshot = verifyExisting ? 'pdf-after-service-restart.png' : 'pdf-ready-answer.png';
    await panel.screenshot({ path: path.join(output, screenshot) });
    evidence.screenshots.push(screenshot);
    currentStep = 'refresh-recovery';
    await page.reload();
    panel = page.getByRole('region', { name: 'Document indexing and questions' });
    await expect(panel.getByRole('status')).toContainText('Indexing status: READY', { timeout: 30_000 });
    evidence.checks.push({ id: 'READY_AFTER_BROWSER_REFRESH', status: 'PASS' });
  } finally { await context.close(); }

  currentStep = 'other-account-login';
  const other = await authenticatedPage('B');
  try {
    currentStep = 'other-account-resource-denial';
    const denials = await other.page.evaluate(async ({ id, version }) => {
      const { apiClient } = await import('/src/api/client.ts');
      const base = `/api/v1/datasets/${encodeURIComponent(id)}`;
      const operations = [
        ['state', () => apiClient.get(`${base}/indexing`, { params: { version: String(version) } })],
        ['ask', () => apiClient.post(`${base}/ask`, { version, query: 'How should missing revenue be handled?' })],
        ['source', () => apiClient.getBlob(`${base}/source`, { params: { version: String(version) } })],
      ];
      const results = [];
      for (const [operation, run] of operations) {
        try { await run(); results.push({ operation, status: 200 }); }
        catch (error) { results.push({ operation, status: error.status ?? 0 }); }
      }
      return results;
    }, { id: record.datasetId, version: record.version });
    for (const denial of denials) {
      assert.equal(denial.status, 404, `Other account ${denial.operation} must be denied`);
      evidence.checks.push({ id: `OTHER_ACCOUNT_${denial.operation.toUpperCase()}_DENIED`, status: 'PASS', httpStatus: denial.status });
    }
  } finally { await other.context.close(); }
  evidence.status = 'PASS';
} catch (error) {
  // Playwright errors can contain input values or page excerpts. Never persist them.
  evidence.status = 'FAIL'; evidence.failedStep = currentStep;
  evidence.errorType = error?.name || 'Error'; process.exitCode = 1;
  if (!currentStep.includes('login')) console.error(error.message);
} finally {
  await Promise.allSettled([...pendingObservations]);
  await browser.close();
  evidence.finishedAt = new Date().toISOString();
  await writeFile(evidenceFile, JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({ status: evidence.status, failedStep: evidence.failedStep, evidence: evidenceFile, checks: evidence.checks.length }));
}

