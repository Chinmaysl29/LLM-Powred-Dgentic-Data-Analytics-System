import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({reducedMotion:'no-preference'});
const report={login:false};
try {
 await page.goto('http://localhost:5173/login');await page.waitForSelector('[data-motion=running]');
 await page.locator('#login-email').fill(process.env.MOTION_QA_EMAIL);
 await page.locator('#login-password').fill(process.env.MOTION_QA_PASSWORD);
 await page.getByRole('button',{name:'Sign in to your account',exact:true}).click();
 await page.waitForURL('**/dashboard',{timeout:45000});
 assert.equal(await page.locator('.pipeline-card').count(),0);
 report.login=true;report.animationUnmounted=true;
 await page.goto('http://localhost:5173/datasets');
 await page.waitForTimeout(3000);
 report.datasetsPageLoaded=await page.locator('h1').innerText();
 console.log(JSON.stringify(report));
} catch(e){report.error=e.message;console.log(JSON.stringify(report));process.exitCode=1;}
finally{await writeFile('.ui-review/motion-validation/login.json',JSON.stringify(report,null,2));await browser.close();}

