// Install the installed Playwright version's Linux requirements in this
// disposable verification container, then run the real browser journey.
import { spawnSync } from 'node:child_process';
const setup = spawnSync('npx', ['playwright', 'install', 'chromium'], { stdio: 'inherit' });
if (setup.status !== 0) process.exit(setup.status || 1);
await import('./verify-learning-browser.mjs');
