/** Real synthetic API and local login; only the failure-state test intercepts a response. */
import { chromium } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const account=JSON.parse(await readFile('/verification/dashboard-browser-account.json','utf8'));
const output='/verification/phase8-browser';await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/chromium-browser',args:['--no-sandbox','--disable-dev-shm-usage']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[],methods=[],checks=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('request',request=>{if(request.url().includes('/perceptron/dashboard'))methods.push(request.method());});
const base='http://frontend-verify:5173';
try {
  await page.goto(`${base}/learning-dashboard`);await page.waitForURL('**/login');
  checks.push('unauthenticated dashboard redirects to login');
  await page.locator('#login-email').fill(account.email);await page.locator('#login-password').fill(account.password);
  await page.locator('button[type=submit]').click();await page.waitForURL('**/dashboard',{timeout:30000});
  await page.goto(`${base}/learning-dashboard?workspace=${account.workspace_id}`);
  if(process.argv.includes('--disabled')){
    await page.getByRole('heading',{name:'Learning is disabled'}).waitFor();
    assert.equal(await page.getByRole('heading',{name:'Reviewed accuracy over time'}).count(),0);
    await page.screenshot({path:`${output}/disabled.png`,fullPage:true});
    checks.push('real disabled API hides historical evidence and renders disabled state');
  } else {
    const table=page.getByRole('region',{name:'Reviewed accuracy table'});
    await table.waitFor();
    assert.equal(await table.getByRole('row').count(),5);
    await table.getByRole('cell',{name:'0.9000',exact:true}).waitFor();
    await page.getByText('50.0%',{exact:true}).waitFor();
    await page.getByRole('heading',{name:'Top mistakes'}).waitFor();
    checks.push('real stored evaluations, provider reward and distinct 50% shadow agreement displayed');
    await page.getByRole('button',{name:'Next versions'}).click();
    await page.getByText('Page 2',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Previous versions'}).click();
    await page.getByText('Page 1',{exact:true}).waitFor();
    checks.push('weight history pagination works');
    await page.getByLabel('Evidence period').selectOption('90');
    await page.getByText('Validation rejected',{exact:true}).waitFor();
    await page.getByLabel('Evidence period').selectOption('7');
    await page.waitForFunction(()=>!document.body.textContent.includes('Validation rejected'));
    await table.waitFor();
    await page.screenshot({path:`${output}/dashboard-desktop.png`,fullPage:true});
    await page.getByRole('combobox',{name:'Workspace',exact:true}).selectOption(account.empty_workspace);
    await page.getByText('No reviewed promotion evaluations in this period.',{exact:true}).waitFor();
    assert.equal(await page.getByRole('region',{name:'Reviewed accuracy table'}).count(),0);
    await page.getByText('Not available',{exact:true}).waitFor();
    checks.push('period filter and empty workspace show no stale evidence or fabricated accuracy');
    await page.getByRole('combobox',{name:'Workspace',exact:true}).selectOption(account.workspace_id);await table.waitFor();
    await page.route('**/api/v1/perceptron/dashboard?**',route=>route.fulfill({status:503,contentType:'application/json',body:'{"detail":"synthetic outage"}'}));
    await page.getByRole('button',{name:'Refresh',exact:true}).click();
    await page.getByRole('alert').waitFor();assert.equal(await table.count(),0);
    await page.unroute('**/api/v1/perceptron/dashboard?**');
    await page.getByRole('button',{name:'Retry evidence'}).click();await table.waitFor();
    checks.push('injected outage clears stale data; retry recovers using real API');
    await page.reload();await table.waitFor();
    assert.ok(page.url().includes(account.workspace_id));
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:`${output}/dashboard-mobile.png`,fullPage:true});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'mobile page overflow');
    checks.push('workspace restores after reload; mobile page fits viewport with scrollable tables');
  }
  assert.deepEqual(errors,[]);assert.ok(methods.length>0 && methods.every(method=>method==='GET'));
  checks.push('no page errors and dashboard requests are GET only');
  const mode=process.argv.includes('--disabled')?'disabled':'enabled';
  await writeFile(`${output}/${mode}.json`,JSON.stringify({passed:true,checks},null,2));
  console.log(JSON.stringify({passed:true,mode,checks}));
} catch(error) {
  await page.screenshot({path:`${output}/failure.png`,fullPage:true});
  throw error;
} finally {await browser.close();}
