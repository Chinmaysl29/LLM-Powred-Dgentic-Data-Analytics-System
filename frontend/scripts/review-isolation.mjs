// Two real, independent browser sessions. Sign in manually; no session injection.
import { chromium } from '@playwright/test';
import { createInterface } from 'node:readline';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const sessions = [];
for (const label of ['A', 'B']) {
  const context = await chromium.launchPersistentContext(resolve(`.ui-review/isolation/account-${label}`), {
    channel: 'chrome', headless: false, viewport: { width: 1440, height: 900 },
  });
  const page = context.pages()[0] ?? await context.newPage();
  await page.goto('http://localhost:5173/login');
  sessions.push({ label, context, page });
  console.log(`Account ${label} browser opened at the real login page.`);
}
console.log('Sign in manually with different test accounts. Commands: check, run, close.');
for await (const command of createInterface({ input: process.stdin })) {
  if (command.trim() === 'close') break;
  if (command.trim() === 'dataset') {
    try {
      const { reviewDatasetFixture } = await import(`./review-dataset-fixture.mjs?run=${Date.now()}`);
      console.log(JSON.stringify(await reviewDatasetFixture(sessions)));
    } catch (error) {
      console.log(JSON.stringify({ status: 'FAIL', message: error.message }));
    }
    continue;
  }
  if (command.trim() === 'faults') {
    try {
      const { reviewReliability } = await import(`./review-reliability.mjs?run=${Date.now()}`);
      console.log(JSON.stringify(await reviewReliability(sessions[0])));
    } catch (error) {
      console.log(JSON.stringify({ status: 'FAIL', message: error.message }));
    }
    continue;
  }
  if (command.trim() === 'run') {
    try {
      const { reviewWorkspaceIsolation } = await import(`./review-workspace-isolation.mjs?run=${Date.now()}`);
      console.log(JSON.stringify(await reviewWorkspaceIsolation(sessions)));
    } catch (error) {
      console.log(JSON.stringify({ status: 'FAIL', message: error.message }));
    }
    continue;
  }
  if (command.trim() !== 'check') continue;
  const results = [];
  for (const { label, page } of sessions) {
    if (page.isClosed()) {
      results.push({ account: label, signedIn: false, closed: true, identityFingerprint: null });
      continue;
    }
    const state = await page.evaluate(async () => {
      const { supabase } = await import('/src/lib/supabase/client.ts');
      const { data, error } = await supabase.auth.getUser();
      return { id: data?.user?.id ?? null, signedIn: Boolean(data?.user && !error), path: location.pathname };
    });
    results.push({ account: label, signedIn: state.signedIn, path: state.path,
      identityFingerprint: state.id ? createHash('sha256').update(state.id).digest('hex').slice(0, 16) : null });
  }
  const distinctAccounts = results.every(r => r.signedIn) && results[0].identityFingerprint !== results[1].identityFingerprint;
  await mkdir('.ui-review/isolation', { recursive: true });
  await writeFile('.ui-review/isolation/session-check.json', JSON.stringify({ results, distinctAccounts }, null, 2));
  console.log(JSON.stringify({ results, distinctAccounts }));
}
for (const { context } of sessions) await context.close();
