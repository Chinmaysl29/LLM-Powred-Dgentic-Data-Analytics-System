// Opens the real app for manual sign-in. No credentials, fake sessions or auth overrides.
import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { reviewAuthenticated } from './review-authenticated.mjs';
import { reviewInteractions } from './review-workflows.mjs';

const origin = 'http://localhost:5173';
const directory = new URL('../.ui-review/', import.meta.url);
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: false });
const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
const page = await context.newPage();
const issues = [];
page.on('pageerror', error => issues.push({ kind: 'pageerror', message: error.message }));
page.on('response', response => {
  if (response.status() >= 400) issues.push({ kind: 'http', status: response.status(), path: new URL(response.url()).pathname });
});
await page.goto(`${origin}/login`);
console.log('Real login page opened. Sign in manually, then send "check" to capture the authenticated routes.');
console.log('Send "audit" for all widths and navigation checks, "login" for the current page, or "close" to close this browser.');
const routes = ['dashboard', 'datasets', 'connections', 'data-warehouse', 'analysis', 'visualizations', 'insights', 'forecasting', 'reports', 'dashboard-studio', 'memory', 'profile', 'settings'];
for await (const command of createInterface({ input: process.stdin })) {
  if (command.trim() === 'close') break;
  if (command.trim() === 'audit') { console.log(JSON.stringify(await reviewAuthenticated({ page }))); continue; }
  if (command.trim() === 'interactions') { console.log(JSON.stringify(await reviewInteractions({ page }))); continue; }
  if (command.trim() === 'login') {
    await page.screenshot({ path: fileURLToPath(new URL('login.png', directory)), fullPage: true });
    console.log(JSON.stringify({ path: new URL(page.url()).pathname, title: await page.title(), issues }));
    continue;
  }
  if (command.trim() !== 'check') continue;
  const results = [];
  for (const route of routes) {
    await page.goto(`${origin}/${route}`);
    try { await page.locator('.ws-shell').waitFor({ timeout: 8000 }); }
    catch { console.log('BLOCKED: authenticate in this browser through the real login form first.'); break; }
    await page.locator('h1').first().waitFor();
    await page.screenshot({ path: fileURLToPath(new URL(`${route}-1440.png`, directory)), fullPage: true });
    results.push(await page.evaluate(() => ({ route: location.pathname, heading: document.querySelector('h1')?.textContent, sidebar: getComputedStyle(document.querySelector('.ws-sidebar')).backgroundColor, activeLinks: document.querySelectorAll('.ws-sidebar a[aria-current="page"]').length, overflow: document.documentElement.scrollWidth > innerWidth })));
  }
  if (results.length === routes.length) {
    for (const width of [1280, 1024, 768, 390, 360]) {
      await page.setViewportSize({ width, height: 960 });
      for (const route of routes) {
        await page.goto(`${origin}/${route}`);
        await page.locator('h1').first().waitFor();
        await page.screenshot({ path: fileURLToPath(new URL(`${route}-${width}.png`, directory)), fullPage: true });
        results.push(await page.evaluate(() => ({ route: location.pathname, width: innerWidth, overflow: document.documentElement.scrollWidth > innerWidth, mainMargin: getComputedStyle(document.querySelector('.ws-main')).marginLeft })));
      }
    }
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto(`${origin}/dashboard`);
  }
  await writeFile(new URL('results.json', directory), JSON.stringify({ results, issues }, null, 2));
  console.log(JSON.stringify({ results, issues }));
}
await browser.close();
