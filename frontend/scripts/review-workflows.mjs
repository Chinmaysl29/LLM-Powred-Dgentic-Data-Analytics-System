import { writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
export async function reviewInteractions({ page }) {
  const results = [];
  const directory = new URL('../.ui-review/authenticated/', import.meta.url);
  async function go(route) {
    await page.goto(`http://localhost:5173/${route}`);
    await page.locator('.ws-shell').waitFor();
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await go('datasets');
  const search = page.getByRole('searchbox', { name: 'Search datasets by filename' });
  await search.fill('ui-review-no-match-97136');
  if (await page.locator('.dataset-table tbody tr').count()) throw new Error('Dataset search did not filter rows');
  await search.fill('');
  await page.getByLabel('Filter datasets by status').selectOption('ready');
  const badges = await page.locator('.status-badge').allTextContents();
  if (!badges.length || badges.some(label => label !== 'Ready')) throw new Error('Ready status filter or labels failed');
  results.push({ check: 'Dataset search, Ready filter and visible status labels', pass: true });
  await page.getByLabel('Filter datasets by status').selectOption('all');
  await page.getByRole('link', { name: 'Upload Dataset', exact: true }).click();
  await page.waitForURL('**/datasets/upload');
  await page.locator('input[type="file"]').waitFor({ state: 'attached' });
  if (!await page.locator('input[type="file"]').count()) throw new Error('Upload route is missing its file input');
  results.push({ check: 'Existing upload route and file input', pass: true });
  await go('visualizations');
  await page.getByLabel('Chart type', { exact: false }).waitFor();
  for (const type of ['Line', 'Area', 'Pie', 'Scatter', 'Heatmap', 'Treemap', 'Table', 'Bar']) {
    await page.getByLabel('Chart type', { exact: false }).selectOption(type);
    if (await page.getByLabel('Chart type', { exact: false }).inputValue() !== type) throw new Error(`Chart selection failed: ${type}`);
  }
  const field = await page.getByLabel('Filter field', { exact: false }).locator('option').nth(1).getAttribute('value') || await page.getByLabel('Filter field', { exact: false }).locator('option').nth(1).textContent();
  await page.getByLabel('Filter field', { exact: false }).selectOption(field);
  await page.getByLabel('Contains', { exact: true }).fill('ui-review-no-match-97136');
  await page.getByText(/0 of \d+ loaded records match your filters/).waitFor();
  await page.getByLabel('Contains', { exact: true }).fill('');
  await page.getByLabel('Filter field', { exact: false }).selectOption('');
  await page.getByText('View underlying records', { exact: true }).click();
  if (!await page.getByRole('table', { name: 'First 100 matching loaded records' }).isVisible()) throw new Error('Underlying chart records are not accessible');
  results.push({ check: 'All chart selectors, actual-record filter and underlying values', pass: true });
  await go('reports');
  await page.getByLabel('Search reports', { exact: true }).fill('ui-review-no-match-97136');
  await page.getByRole('heading', { name: 'No matching reports' }).waitFor();
  results.push({ check: 'Report search empty state', pass: true });
  await go('settings');
  const theme = page.getByLabel('Theme', { exact: false });
  const original = await theme.inputValue();
  try {
    await theme.selectOption('dark');
    await page.reload();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    if (await page.getByLabel('Theme', { exact: false }).inputValue() !== 'dark') throw new Error('Theme did not persist');
    results.push({ check: 'Theme persistence across reload', pass: true });
  } finally { await page.getByLabel('Theme', { exact: false }).selectOption(original); }
  await go('dashboard');
  await page.getByRole('button', { name: 'Collapse sidebar', exact: true }).click();
  await page.locator('.ws-main--collapsed').waitFor();
  await page.getByRole('button', { name: 'Expand sidebar', exact: true }).click();
  results.push({ check: 'Desktop sidebar collapse and restore', pass: true });
  for (const width of [768, 390, 360]) {
    await page.setViewportSize({ width, height: 960 });
    await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
    await page.waitForFunction(() => { const box = document.querySelector('.ws-sidebar--open')?.getBoundingClientRect(); return box && Math.abs(box.left) < 1; });
    await page.screenshot({ path: fileURLToPath(new URL(`navigation-${width}.png`, directory)), fullPage: false });
    await page.locator('.ws-sidebar').getByRole('link', { name: 'Visualizations', exact: true }).click();
    await page.waitForURL('**/visualizations');
    if (await page.locator('.ws-sidebar--open').count()) throw new Error('Drawer did not close after navigation');
    results.push({ check: `Mobile drawer navigation ${width}px`, pass: true });
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await go('dashboard');
  await writeFile(new URL('interactions.json', directory), JSON.stringify(results, null, 2));
  return results;
}
