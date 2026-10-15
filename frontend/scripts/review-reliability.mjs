// Browser-only fault injection: no auth alteration, database writes or provider outage.
import { mkdir, writeFile } from 'node:fs/promises';

export async function reviewReliability({ context, page }) {
  const output = '.ui-review/reliability';
  await mkdir(output, { recursive: true });
  const issues = [];
  const onError = error => issues.push(error.message);
  page.on('pageerror', onError);
  let attempts = 0;
  let fallbackRequests = 0;
  const onRequest = request => {
    if (new URL(request.url()).pathname === '/api/v1/os/reports/studio/history') fallbackRequests++;
  };
  page.on('request', onRequest);
  const pattern = '**/rest/v1/reports?*';
  await context.route(pattern, async route => {
    attempts++;
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'Controlled test outage' }) });
  });
  try {
    await page.goto('http://localhost:5173/reports');
    await page.locator('.ws-shell').waitFor({ timeout: 15000 });
    await page.getByRole('alert').filter({ hasText: 'Report library is unavailable' }).waitFor({ timeout: 15000 });
    await page.screenshot({ path: `${output}/reports-degraded.png`, fullPage: true });
    // StrictMode may mount twice; each operation must still have at most 3 attempts.
    if (attempts < 1 || attempts > 6) throw new Error(`Unexpected retry count ${attempts}`);
    if (fallbackRequests !== 0) throw new Error('Read crossed into backend report store');
    await context.unroute(pattern);
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('[role="alert"]') && !document.querySelector('[role="status"]'), undefined, { timeout: 15000 });
    await page.screenshot({ path: `${output}/reports-recovered.png`, fullPage: true });
    const result = { status: 'PASS', scenario: 'Supabase reports 503 and recovery', attempts,
      fallbackRequests, pageErrors: issues.length, authenticatedShell: await page.locator('.ws-shell').count() === 1 };
    if (issues.length) throw new Error('Browser rendering error during fault scenario');
    await writeFile(`${output}/results.json`, JSON.stringify(result, null, 2));
    return result;
  } finally {
    await context.unroute(pattern);
    page.off('pageerror', onError);
    page.off('request', onRequest);
  }
}
