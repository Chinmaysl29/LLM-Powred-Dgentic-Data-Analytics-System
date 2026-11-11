import { chromium } from '@playwright/test';
import { lookup } from 'node:dns/promises';
import { mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

// Use the service's IP: Vite permits IP hosts, and the browser runs in Docker.
const { address } = await lookup('frontend');
const base = `http://${address}:5173`;
const output = '.ui-review/setup';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ args: ['--disable-dev-shm-usage'] });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
const checks = [];
try {
  await page.goto(`${base}/login`, { waitUntil: 'networkidle' });
  await page.locator('#login-email').waitFor({ state: 'visible' });
  checks.push('direct /login navigation renders the login form');
  await page.reload({ waitUntil: 'networkidle' });
  await page.locator('#login-email').waitFor({ state: 'visible' });
  checks.push('/login refresh retains a working form');
  for (const route of ['/datasets', '/reports', '/analysis']) {
    await page.goto(`${base}${route}`);
    await page.waitForURL('**/login');
    checks.push(`unauthenticated ${route} redirects to login`);
  }
  await page.screenshot({ path: `${output}/login.png`, fullPage: true });
  assert.deepEqual(errors, [], 'browser runtime errors');
  checks.push('no uncaught browser runtime errors');
  console.log(JSON.stringify({ checks, authenticatedSupabaseJourney: 'not tested: no test account credentials' }, null, 2));
  await writeFile(`${output}/browser.json`, JSON.stringify({ checks, errors }, null, 2));
} finally {
  await browser.close();
}
