import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

// Credentials come only from the calling process. No cookies, tokens, passwords,
// request bodies or customer records are written to the evidence directory.
const output = '.ui-review/integration-acceptance';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const results = [];
try {
  for (const account of ['A', 'B']) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const result = { account, login: false, project: null, authStatus: null };
    page.on('response', response => {
      const url = new URL(response.url());
      if (url.pathname === '/auth/v1/token') {
        result.project = url.origin;
        result.authStatus = response.status();
      }
    });
    try {
      const email = process.env[`ACCEPTANCE_${account}_EMAIL`];
      const password = process.env[`ACCEPTANCE_${account}_PASSWORD`];
      if (!email || !password) throw new Error('Account environment variables are required');
      await page.goto(process.env.ACCEPTANCE_URL || 'http://localhost:5173/login');
      await page.locator('#login-email').fill(email);
      await page.locator('#login-password').fill(password);
      await page.getByRole('button', { name: 'Sign in to your account', exact: true }).click();
      await page.waitForURL('**/dashboard', { timeout: 45000 });
      result.login = true;
      if (process.env.ACCEPTANCE_URL) {
        result.actorId = await page.evaluate(async () => {
          const { apiClient } = await import('/src/api/client.ts');
          const user = await apiClient.get('/api/v1/auth/me');
          return user.id;
        });
      }
    } catch {
      result.error = result.authStatus === 400 ? 'Authentication rejected' : 'Login did not reach dashboard';
      process.exitCode = 1;
    } finally {
      results.push(result);
      await context.close();
    }
  }
} finally {
  await browser.close();
  await writeFile(`${output}/development-logins.json`, JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
}
