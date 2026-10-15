import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const directory = new URL('../.ui-review/', import.meta.url);
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const results = [];
try {
  for (const route of ['dashboard', 'datasets', 'connections', 'data-warehouse', 'analysis', 'visualizations', 'insights', 'forecasting', 'reports', 'dashboard-studio', 'memory', 'profile', 'settings']) {
    await page.goto(`http://localhost:5173/${route}`);
    await page.waitForURL('**/login');
    results.push({ route, signedOutRedirect: 'pass' });
  }
  for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 960 });
    await page.locator('input[type="password"]').waitFor();
    await page.screenshot({ path: fileURLToPath(new URL(`public-login-${width}.png`, directory)), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    results.push({ route: '/login', width, overflow });
    if (overflow) throw new Error(`Login has document overflow at ${width}px`);
  }
  if (errors.length) throw new Error('Browser runtime errors occurred');
  console.log(JSON.stringify({ results, errors }, null, 2));
} finally {
  await writeFile(new URL('public-results.json', directory), JSON.stringify({ results, errors }, null, 2));
  await browser.close();
}
