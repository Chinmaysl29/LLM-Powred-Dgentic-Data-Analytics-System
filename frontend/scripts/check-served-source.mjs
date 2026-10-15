// Compare normal Vite transforms, not cache-busted/raw requests, to this checkout.
import { readFile, appendFile, writeFile } from 'node:fs/promises';
const root = new URL('../', import.meta.url);
const origin = process.env.UI_REVIEW_ORIGIN || 'http://localhost:5173';
const pages = ['Dashboard', 'Datasets', 'Connections', 'DataWarehouse', 'Analysis', 'Visualizations', 'Insights', 'ForecastingWorkbench', 'Reports', 'DashboardStudio', 'AIMemoryExplorer', 'Profile', 'Settings'];
const files = ['src/main.tsx', 'src/App.tsx', 'src/layouts/AppLayout.tsx', ...pages.map(name => `src/pages/app/${name}Page.tsx`)];
async function servedSource(file) {
  const response = await fetch(`${origin}/${file}`, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
  const code = await response.text();
  const encoded = code.match(/sourceMappingURL=data:application\/json;base64,([^\s]+)/)?.[1];
  if (!encoded) throw new Error(`${file}: missing inline source map`);
  return JSON.parse(Buffer.from(encoded, 'base64').toString()).sourcesContent;
}
for (const file of files) {
  const local = await readFile(new URL(file, root), 'utf8');
  if (!(await servedSource(file)).includes(local)) throw new Error(`${file}: served transform differs from local source`);
  console.log(`PASS served source: ${file}`);
}
const css = await fetch(`${origin}/src/styles/workspace-design.css`, { signal: AbortSignal.timeout(15000) });
if (!css.ok || !(await css.text()).includes('--bg: #f1f2ec')) throw new Error('Redesign stylesheet is unavailable');
console.log('PASS redesign stylesheet served');
if (process.argv.includes('--check-watcher')) {
  const file = 'src/main.tsx';
  const url = new URL(file, root);
  const marker = `\n// UI watcher verification ${Date.now()}\n`;
  try {
    await appendFile(url, marker);
    let observed = false;
    for (let attempt = 0; attempt < 15; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      if ((await servedSource(file)).some(source => source?.includes(marker))) { observed = true; break; }
    }
    if (!observed) throw new Error('Windows host edit did not invalidate the normal Vite transform');
    console.log('PASS Windows host edit invalidated Vite transform');
  } finally {
    // Remove only our marker, retaining any intervening user edits.
    const current = await readFile(url, 'utf8');
    await writeFile(url, current.replace(marker, ''));
  }
}
