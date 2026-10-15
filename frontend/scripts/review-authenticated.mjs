// Runs against an already authenticated Playwright page. Never sets auth state.
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
export async function reviewAuthenticated({ page }) {
  const directory = new URL('../.ui-review/authenticated/', import.meta.url);
  await mkdir(directory, { recursive: true });
  const routes = ['dashboard', 'datasets', 'connections', 'data-warehouse', 'analysis', 'visualizations', 'insights', 'forecasting', 'reports', 'dashboard-studio', 'memory', 'profile', 'settings'];
  const results = [], issues = [], interactions = [];
  const onError = error => issues.push({ kind: 'pageerror', message: error.message });
  const onResponse = response => { if (response.status() >= 400) issues.push({ kind: 'http', status: response.status(), path: new URL(response.url()).pathname }); };
  page.on('pageerror', onError); page.on('response', onResponse);
  try {
    for (const width of [1440, 1280, 1024, 768, 390, 360]) {
      await page.setViewportSize({ width, height: 960 });
      for (const route of routes) {
        await page.goto(`http://localhost:5173/${route}`);
        await page.locator('.ws-shell').waitFor({ timeout: 15000 });
        await page.locator('h1').first().waitFor();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
        await page.screenshot({ path: fileURLToPath(new URL(`${route}-${width}.png`, directory)), fullPage: true });
        results.push(await page.evaluate(() => ({ route: location.pathname, width: innerWidth, heading: document.querySelector('h1')?.textContent, overflow: document.documentElement.scrollWidth > innerWidth, background: getComputedStyle(document.querySelector('.ws-main')).backgroundColor, sidebar: getComputedStyle(document.querySelector('.ws-sidebar')).backgroundColor, activeLinks: document.querySelectorAll('.ws-sidebar a[aria-current="page"]').length, mainMargin: getComputedStyle(document.querySelector('.ws-main')).marginLeft, alerts: [...document.querySelectorAll('[role="alert"]')].map(element => element.textContent?.slice(0, 250)), loading: [...document.querySelectorAll('[role="status"]')].map(element => element.textContent?.slice(0, 100)) })));
        if (route === 'dashboard') {
          const account = page.getByLabel('Account options', { exact: true });
          await account.click();
          if (!await page.getByRole('link', { name: 'View profile', exact: true }).isVisible()) throw new Error('Account disclosure did not open');
          await account.press('Escape');
          interactions.push({ width, accountDisclosure: 'pass' });
          if (width <= 768) {
            await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
            await page.locator('.ws-sidebar--open').waitFor();
            await page.waitForFunction(() => { const rect = document.querySelector('.ws-sidebar--open')?.getBoundingClientRect(); return rect && Math.abs(rect.left) < 1 && rect.width >= 240; });
            await page.screenshot({ path: fileURLToPath(new URL(`navigation-${width}.png`, directory)), fullPage: true });
            await page.keyboard.press('Escape');
            if (await page.locator('.ws-sidebar--open').count()) throw new Error('Mobile drawer did not close');
            interactions.push({ width, mobileDrawer: 'pass' });
          }
        }
      }
      console.log(`Authenticated review: ${width}px completed`);
    }
  } finally {
    page.off('pageerror', onError); page.off('response', onResponse);
    await writeFile(new URL('results.json', directory), JSON.stringify({ results, issues, interactions }, null, 2));
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto('http://localhost:5173/dashboard');
  }
  return { captures: results.length, overflow: results.filter(result => result.overflow), incorrectActiveLinks: results.filter(result => result.activeLinks !== 1), issues: [...new Map(issues.map(issue => [JSON.stringify(issue), issue])).values()], interactions };
}
