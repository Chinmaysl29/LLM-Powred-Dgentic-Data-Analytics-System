import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const mode = process.argv[2];
assert.ok(['before', 'after'].includes(mode));
const account = JSON.parse(await readFile('/verification/learning-browser-account.json', 'utf8'));
const browser = await chromium.launch({ executablePath: '/usr/bin/chromium-browser', args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
page.setDefaultTimeout(60000);
const errors = [], requests = [];
const responses = [], failures = [];
page.on('pageerror', e => errors.push(e.message));
page.on('response', r => {
  const url = new URL(r.url());
  if (url.pathname.includes('/company/')) responses.push({ path: url.pathname, search: url.searchParams.get('search'), status: r.status() });
});
page.on('requestfailed', r => {
  const url = new URL(r.url());
  if (url.pathname.includes('/company/')) failures.push({ path: url.pathname, search: url.searchParams.get('search'), error: r.failure()?.errorText });
});
page.on('request', request => {
  const url = new URL(request.url());
  const panel = url.pathname.match(/\/dataplane\/company\/(dictionary|workflows|policy|incidents)$/)?.[1];
  if (panel && request.method() === 'GET') requests.push({ panel, search: url.searchParams.get('search') });
});
const base = 'http://frontend-verify:5173';
try {
  await page.goto(base + '/login');
  await page.locator('#login-email').fill(account.email);
  await page.locator('#login-password').fill(account.password);
  await page.locator('button[type=submit]').click();
  await page.waitForURL('**/dashboard');
  await page.goto(base + '/data-health?workspace=' + account.workspace_id);
  const search = page.getByLabel('Search dictionary', { exact: true });
  await search.waitFor();
  await page.waitForTimeout(1500);
  const samples = [];
  for (let run = 0; run < 6; run++) {
    await search.fill('');
    await page.waitForTimeout(650);
    requests.length = 0;
    const phrase = 'zzperf' + run;
    const response = page.waitForResponse(r => {
      const url = new URL(r.url());
      return url.pathname.endsWith('/company/dictionary') && url.searchParams.get('search') === phrase;
    });
    await search.pressSequentially(phrase, { delay: 75 });
    const completed = await response;
    assert.equal(completed.status(), 200, 'Dictionary search must succeed');
    const value = await completed.json();
    assert.equal(value.items.length, 0);
    await page.getByText('No matching definitions. Create a draft using an uploaded snapshot.', { exact: true }).waitFor();
    await page.waitForTimeout(400);
    const counts = Object.fromEntries(['dictionary', 'workflows', 'policy', 'incidents'].map(panel => [panel, requests.filter(r => r.panel === panel).length]));
    if (mode === 'after') assert.deepEqual(counts, { dictionary: 1, workflows: 0, policy: 0, incidents: 0 });
    if (run) samples.push(counts); // one warm-up, five measured searches
  }
  requests.length = 0;
  await page.getByRole('button', { name: 'Refresh company review', exact: true }).click();
  await page.waitForTimeout(1200);
  for (const panel of ['dictionary', 'workflows', 'policy', 'incidents']) assert.ok(requests.some(r => r.panel === panel), 'Manual refresh must reload ' + panel);
  const checks = ['Latest search is displayed', 'Manual refresh reloads every panel', 'No browser errors'];
  if (mode === 'after') {
    await page.route('**/api/v1/dataplane/company/dictionary?**', async route => {
      if (new URL(route.request().url()).searchParams.get('search') === 'zzerror') {
        await route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic dictionary failure' }) });
      } else await route.continue();
    });
    await search.fill('zzerror');
    const region = page.getByRole('region', { name: 'Company review', exact: true });
    await region.getByRole('alert').filter({ hasText: 'Synthetic dictionary failure' }).waitFor();
    const recovered = page.waitForResponse(r => new URL(r.url()).searchParams.get('search') === 'zzrecovered' && r.status() === 200);
    await search.fill('zzrecovered');
    await recovered;
    await region.getByRole('alert').waitFor({ state: 'detached' });
    checks.push('Search failure is visible and clears after successful retry');
  }
  assert.deepEqual(errors, []);
  const result = { mode, browser: browser.version(), samples, warmups: 1, characters_per_search: 7, inter_key_delay_ms: 75,
    checks, scope: 'Development server Chromium request counts; render duration and production load time not measured' };
  await writeFile('/verification/optimization-browser-' + mode + '.json', JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} catch (error) {
  const failure = { mode, requests, responses, failures, errors, searchValue: await page.getByLabel('Search dictionary', { exact: true }).inputValue().catch(() => null) };
  await writeFile('/verification/optimization-browser-' + mode + '-failure.json', JSON.stringify(failure, null, 2));
  console.log(JSON.stringify(failure));
  throw error;
} finally {
  await browser.close();
}
