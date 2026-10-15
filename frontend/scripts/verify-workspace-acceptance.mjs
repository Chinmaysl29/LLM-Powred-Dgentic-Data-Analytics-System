import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';

const output = '.ui-review/integration-acceptance';
const workspaces = JSON.parse((await readFile(`${output}/workspaces.json`, 'utf8')).replace(/^\uFEFF/, ''));
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const results = [];
try {
  for (const workspace of workspaces) {
    if (process.env.ACCEPTANCE_PDF_ONLY && workspace.account !== 'A') continue;
    const context = await browser.newContext();
    const page = await context.newPage();
    const result = { account: workspace.account, checks: [], uploads: [] };
    try {
      await page.goto('http://localhost:5174/login');
      await page.locator('#login-email').fill(process.env[`ACCEPTANCE_${workspace.account}_EMAIL`]);
      await page.locator('#login-password').fill(process.env[`ACCEPTANCE_${workspace.account}_PASSWORD`]);
      await page.getByRole('button', { name: 'Sign in to your account', exact: true }).click();
      await page.waitForURL('**/dashboard');
      const access = await page.evaluate(async ({ own, other }) => {
        const { apiClient } = await import('/src/api/client.ts');
        const ownResult = await apiClient.get(`/api/v1/workspaces/${own}`);
        let denied = false;
        try { await apiClient.get(`/api/v1/workspaces/${other}`); }
        catch (error) { denied = error.status === 404; }
        return { own: ownResult.id, denied };
      }, { own: workspace.workspaceId, other: workspaces.find(w => w !== workspace).workspaceId });
      assert.equal(access.own, workspace.workspaceId);
      assert.equal(access.denied, true);
      result.checks.push('own workspace allowed; other workspace denied');
      const filenames = process.env.ACCEPTANCE_PDF_ONLY ? ['business_definitions.pdf'] : workspace.account === 'A'
        ? ['retail.csv', 'retail.xlsx', 'customers.csv', 'products.json', 'monthly_revenue.csv', 'missing_duplicates.csv', 'business_definitions.pdf']
        : ['retail.csv'];
      for (const filename of filenames) {
        await page.goto('http://localhost:5174/datasets/upload');
        await page.locator('input[type=file]').setInputFiles(path.resolve('../tests/fixtures/integration', filename));
        const pending = page.waitForResponse(r => r.url().includes('/api/v1/datasets/upload') && r.request().method() === 'POST', { timeout: 120000 });
        await page.getByRole('button', { name: 'Upload 1 file', exact: true }).click();
        const response = await pending;
        assert.equal(response.status(), 201, `${filename}: upload returned ${response.status()}`);
        const data = await response.json();
        const id = data.dataset?.dataset_id ?? data.dataset_id;
        assert.ok(id, 'Upload must return dataset identity');
        await page.evaluate(async ({ id, workspaceId }) => {
          const { apiClient } = await import('/src/api/client.ts');
          await apiClient.post(`/api/v1/datasets/${id}/workspace`, { workspace_id: workspaceId });
        }, { id, workspaceId: workspace.workspaceId });
        result.uploads.push({ filename, datasetId: id, status: 201 });
        if (filename === 'retail.csv') {
          const preview = await page.evaluate(async id => {
            const { apiClient } = await import('/src/api/client.ts');
            return apiClient.get(`/api/v1/datasets/${id}/preview`);
          }, id);
          assert.equal(preview.rows.reduce((sum, row) => sum + row.revenue, 0), 1500);
          result.checks.push('retail preview sum equals independent reference 1500');
        }
      }
      await page.goto('http://localhost:5174/datasets');
      await page.screenshot({ path: `${output}/account-${workspace.account}-datasets.png`, fullPage: true });
      result.status = 'PASS';
    } catch (error) {
      result.status = 'FAIL'; result.error = error.message;
      process.exitCode = 1;
    } finally { results.push(result); await context.close(); }
  }
} finally {
  await browser.close();
  await writeFile(`${output}/${process.env.ACCEPTANCE_PDF_ONLY ? 'pdf-retest' : 'workspace-acceptance'}.json`, JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
}
