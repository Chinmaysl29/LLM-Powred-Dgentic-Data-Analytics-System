// User-authorized synthetic upload through the real UI and existing manual sessions.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

export async function reviewDatasetFixture(sessions) {
  const output = '.ui-review/dataset-acceptance-v2';
  const filename = 'recovery_authorized_fixture_v2.csv';
  await mkdir(output, { recursive: true });
  const active = [];
  for (const session of sessions) {
    if (session.page.isClosed()) continue;
    const identity = await session.page.evaluate(async () => {
      const { supabase } = await import('/src/lib/supabase/client.ts');
      const { data, error } = await supabase.auth.getUser();
      if (!data.user || error) return null;
      const { apiClient } = await import('/src/api/client.ts');
      const server = await apiClient.get('/api/v1/auth/me');
      return { sdk: data.user.id, server: server.id };
    });
    if (identity) {
      const fingerprint = id => createHash('sha256').update(id).digest('hex').slice(0,16);
      console.log(JSON.stringify({ account: session.label, sdk: fingerprint(identity.sdk), server: fingerprint(identity.server) }));
      if (identity.sdk !== identity.server) throw new Error('Browser SDK and backend identity mismatch');
      active.push(session);
    }
  }
  if (!active.length) throw new Error('Manual sign-in required');
  const owner = active.find(s => s.label === 'B') ?? active[0];
  const page = owner.page;
  await page.goto('http://localhost:5173/datasets');
  // Keep retrying this acceptance command from uploading duplicate fixtures.
  let state;
  try { state = JSON.parse(await readFile(`${output}/fixture.json`, 'utf8')); } catch { /* first run */ }
  if (state && state.account !== owner.label) throw new Error('Fixture owner session changed');
  if (!state) {
    const existing = await page.evaluate(async filename => {
      const { datasetService } = await import('/src/services/datasetService.ts');
      const matches = (await datasetService.list()).filter(row => row.filename === filename);
      if (matches.length > 1) throw new Error('Multiple fixture datasets require review');
      return matches[0]?.dataset_id ?? null;
    }, filename);
    if (existing) state = { datasetId: existing, account: owner.label };
  }
  if (!state) {
    await page.goto('http://localhost:5173/datasets/upload');
    await page.locator('input[type="file"]').setInputFiles({ name: filename, mimeType: 'text/csv', buffer: await readFile(resolve('../tests/fixtures/recovery_acceptance.csv')) });
    const uploaded = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/datasets/upload' && r.request().method() === 'POST', { timeout: 60000 });
    void uploaded.catch(() => undefined);
    await page.getByRole('button', { name: /^Upload 1 file$/i }).click();
    const response = await uploaded;
    console.log(JSON.stringify({ uploadOrigin: new URL(response.url()).origin }));
    if (new URL(response.url()).origin !== 'http://127.0.0.1:8000') throw new Error('Upload used an unexpected backend origin');
    if (response.status() !== 201) throw new Error(`Upload returned ${response.status()}`);
    const result = await response.json();
    state = { datasetId: result.dataset_id, account: owner.label };
    await writeFile(`${output}/fixture.json`, JSON.stringify(state, null, 2));
  }
  await writeFile(`${output}/fixture.json`, JSON.stringify(state, null, 2));
  const preview = await page.evaluate(async id => {
    const { apiClient } = await import('/src/api/client.ts');
    return apiClient.get(`/api/v1/datasets/${id}/preview`, { params: { limit: '10' } });
  }, state.datasetId);
  const rows = preview.rows ?? preview.data ?? preview.records;
  if (!Array.isArray(rows) || rows.length !== 10) throw new Error('Expected 10 actual preview rows');
  const total = rows.reduce((sum, row) => sum + Number(row.revenue), 0);
  if (Math.abs(total - 975.5) > 1e-9) throw new Error(`Preview total mismatch: ${total}`);
  const groups = Object.fromEntries(['A','B'].map(category => [category, rows.filter(r => r.category === category).reduce((sum,r) => sum + Number(r.revenue),0)]));
  if (groups.A !== 535.5 || groups.B !== 440) throw new Error('Category totals mismatch');
  const peers = active.filter(s => s !== owner);
  const denials = [];
  for (const peer of peers) {
    denials.push(await peer.page.evaluate(async id => {
      const { apiClient } = await import('/src/api/client.ts');
      try { await apiClient.get(`/api/v1/datasets/${id}/preview`); return 200; }
      catch (error) { return error.status ?? 0; }
    }, state.datasetId));
  }
  if (denials.some(status => status !== 404)) throw new Error(`Cross-account preview statuses: ${denials.join(',')}`);
  await page.goto('http://localhost:5173/datasets');
  await page.getByText('recovery_authorized_fixture_v2', { exact: false }).first().waitFor({ timeout: 15000 });
  await page.screenshot({ path: `${output}/dataset-list.png`, fullPage: true });
  await page.goto('http://localhost:5173/visualizations');
  await page.getByLabel('Data source', { exact: true }).selectOption(state.datasetId);
  await page.getByLabel('Chart type', { exact: true }).selectOption('Bar');
  await page.getByLabel('X field', { exact: true }).selectOption('category');
  await page.getByLabel('Y field', { exact: true }).selectOption('revenue');
  await page.getByLabel('Aggregation', { exact: true }).selectOption('sum');
  await page.getByLabel('Group by', { exact: true }).selectOption('');
  const chart = page.locator('svg[aria-label="sum of revenue by category"]').first();
  await chart.waitFor({ timeout: 15000 });
  const barTitles = await chart.locator('rect title').allTextContents();
  if (!barTitles.includes('A: 535.5') || !barTitles.includes('B: 440')) throw new Error(`Actual chart values mismatch: ${barTitles.join(';')}`);
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export loaded records', exact: true }).click();
  const download = await downloadEvent;
  await download.saveAs(`${output}/fixture-export.json`);
  const exported = JSON.parse(await readFile(`${output}/fixture-export.json`, 'utf8'));
  if (exported.records?.length !== 10 || exported.records.reduce((sum,row) => sum + Number(row.revenue),0) !== 975.5) throw new Error('Export numerical mismatch');
  await page.screenshot({ path: `${output}/visualization.png`, fullPage: true });
  const result = { status: 'PASS', account: owner.label, datasetId: state.datasetId, rows: rows.length,
    total, groups, crossAccountChecks: denials.length, crossAccountStatuses: denials,
    renderedBars: barTitles, exportedRows: exported.records.length,
    limits: 'Synthetic CSV upload/preview/bar/export acceptance; LLM/provider and full pipeline success remain separate gates.' };
  await writeFile(`${output}/results.json`, JSON.stringify(result, null, 2));
  return result;
}
