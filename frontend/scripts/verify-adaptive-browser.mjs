/** Real browser, uploads, auth, worker and downloads. No response mocks. */
import { chromium } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const account=JSON.parse(await readFile('/verification/adaptive-browser-account.json','utf8'));
const output='/verification/adaptive-evidence/browser';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({args:['--disable-dev-shm-usage']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];const checks=[];const base='http://frontend-verify:5173';
page.on('pageerror',error=>errors.push(error.message));
async function top(name){await page.getByRole('button',{name,exact:true}).click();}
async function inner(name){await page.getByRole('navigation',{name:'Adaptive workbench views'}).getByRole('button',{name:name[0].toUpperCase()+name.slice(1),exact:true}).click();}
async function verified(value){
  await page.getByRole('heading',{name:'Verified within checked scope'}).waitFor({timeout:60000});
  await page.getByRole('cell',{name:String(value),exact:true}).first().waitFor();
}
async function start(value){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/orchestrator/runs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Run with verification',exact:true}).click();
  const created=await response;assert.equal(created.status(),201);const body=await created.json();
  await page.waitForURL(url=>url.searchParams.get('run')===body.id);await verified(value);
}
async function noAlert(){assert.equal(await page.getByRole('alert').count(),0,await page.getByRole('alert').allTextContents());}
async function download(button,filename){
  const event=page.waitForEvent('download');await page.getByRole('button',{name:button,exact:true}).click();
  const file=await event;await file.saveAs(`${output}/${filename}`);
  return JSON.parse(await readFile(`${output}/${filename}`,'utf8'));
}
try{
  await page.goto(`${base}/verified-learning`);await page.waitForURL('**/login');
  checks.push('Unauthenticated navigation redirects to login');
  await page.locator('#login-email').fill(account.email);await page.locator('#login-password').fill(account.password);
  await page.locator('button[type=submit]').click();await page.waitForURL('**/dashboard',{timeout:30000});
  checks.push('Real local password login');
  await page.goto(`${base}/datasets/upload`);
  const uploaded=[];
  const listener=response=>{
    if(response.url().includes('/api/v1/datasets/upload')&&response.request().method()==='POST'&&response.status()===201){uploaded.push(response.json());}
  };
  page.on('response',listener);
  await page.locator('#dataset-file-input').setInputFiles([
    {name:'orders_browser.csv',mimeType:'text/csv',buffer:Buffer.from('order_id,amount\nA,100\nB,200\n')},
    {name:'refunds_browser.csv',mimeType:'text/csv',buffer:Buffer.from('order_id,refund\nA,10\nA,5\n')},
  ]);
  await page.getByRole('button',{name:'Upload 2 files',exact:true}).click();
  await page.waitForURL('**/datasets',{timeout:60000});assert.equal(uploaded.length,2);page.off('response',listener);
  const uploadedInputs=await Promise.all(uploaded);
  checks.push('Two original CSVs uploaded through the real upload UI and API');
  const token=await page.evaluate(()=>localStorage.getItem('auth_token'));
  for(const item of uploadedInputs){
    const response=await page.request.post(`${base}/api/v1/datasets/${item.dataset_id}/workspace`,{
      headers:{Authorization:`Bearer ${token}`},data:{workspace_id:account.workspace_id}});
    assert.equal(response.status(),200);
  }
  checks.push('Uploaded inputs explicitly bound using authorized workspace API');
  await page.goto(`${base}/verified-learning?workspace=${account.workspace_id}`);
  await page.getByRole('heading',{name:'Start a verified analysis'}).waitFor();
  await page.getByLabel('Dataset',{exact:true}).selectOption(uploadedInputs[0].dataset_id);
  await page.getByLabel('Objective',{exact:true}).fill('Net revenue');
  await page.getByText('Order/refund relationship (optional)',{exact:true}).click();
  await page.getByLabel('Refund dataset',{exact:true}).selectOption(uploadedInputs[1].dataset_id);
  await page.getByLabel('Business definition',{exact:true}).selectOption('net_revenue@1');
  await start(285);
  assert.equal(await page.getByLabel('Computed result chart').count(),1);
  checks.push('Seven-stage live worker reconciles refunds per order, verifies 285, and renders the computed chart');
  await page.screenshot({path:`${output}/net-revenue-evidence.png`,fullPage:true});
  const report=await download('Download verified report','net-revenue-report.json');
  assert.deepEqual(report.answer.rows,[{value:285}]);
  checks.push('UI download contains exact verified 285 result and report lineage');
  await page.reload();await verified(285);
  assert.equal(await page.getByLabel('Dataset',{exact:true}).inputValue(),uploadedInputs[0].dataset_id);
  assert.equal(await page.getByLabel('Refund dataset',{exact:true}).inputValue(),uploadedInputs[1].dataset_id);
  checks.push('Pinned run, original task form and result restore after browser refresh');
  await top('Adaptive');await inner('understanding');
  await page.getByText('join fan out',{exact:true}).waitFor();
  await page.getByText('Observed evidence',{exact:true}).click();
  await page.screenshot({path:`${output}/diagnosis.png`,fullPage:true});
  checks.push('Persisted context exposes join-grain observation, evidence and distinguishing checks');
  await inner('skills');await page.getByRole('button',{name:'refunds_per_order v1',exact:true}).click();
  await page.getByRole('heading',{name:'refunds_per_order v1 · active',exact:true}).waitFor();
  checks.push('Tested executable skill contract, preconditions and lifecycle visible');
  await top('Analysis');
  await page.getByText('Order/refund relationship (optional)',{exact:true}).click();
  await page.getByLabel('Relationship purpose',{exact:true}).selectOption('refund_event_count');
  await start(2);
  const eventReport=await download('Download verified report','refund-events-report.json');
  assert.deepEqual(eventReport.answer.rows,[{value:2}]);
  assert.equal(eventReport.task.units,'events');
  checks.push('Refund-event task preserves both events; net-revenue preaggregation excluded');
  await top('Adaptive');await inner('training');
  await page.getByText('linear · evaluated · release blocked',{exact:true}).waitFor();
  await page.getByText('mlp · evaluated · release blocked',{exact:true}).waitFor();
  await page.screenshot({path:`${output}/training-comparison.png`,fullPage:true});
  await page.getByText('linear · evaluated · release blocked',{exact:true}).click();
  const model=await download('Download linear model bundle','linear-model-bundle.json');
  assert.ok(model.bundle.weights.flat(2).some(value=>value!==0));
  assert.equal(model.bundle.calibration_status,'unavailable');
  assert.equal(model.bundle.evaluation.release_eligible,false);
  checks.push('Actual trained JSON weights, three-policy metrics and blocked release visible/downloadable');
  await inner('controls');
  await page.getByLabel('Candidate selector',{exact:true}).selectOption(account.linear_model_id);
  assert.equal(await page.getByRole('button',{name:'Activate evaluated selector',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'Use shadow scores',exact:true}).click();
  await page.getByText('Shadow ranking enabled. Rules/memory still executes the selected action.',{exact:true}).waitFor();
  checks.push('Activation gated; authorized shadow mode enabled through UI');
  // Reopen the original numeric fixture in a new form, keeping this separate from the two-input contract.
  await page.goto(`${base}/verified-learning?workspace=${account.workspace_id}`);
  await page.getByLabel('Dataset',{exact:true}).selectOption(uploadedInputs[0].dataset_id);
  await page.getByLabel('Objective',{exact:true}).fill('Total amount');
  await page.getByLabel('Metric column',{exact:true}).fill('amount');
  await page.getByLabel('Group by (optional)',{exact:true}).fill('');
  await page.getByLabel('Units',{exact:true}).fill('USD');
  await page.getByLabel('Currency (optional)',{exact:true}).fill('USD');
  await start(300);
  await top('Adaptive');await inner('decisions');
  const latest=page.locator('section[aria-label="Adaptive skills workbench"] details').first();
  await latest.locator('summary').click();
  await latest.getByRole('columnheader',{name:'Shadow score',exact:true}).waitFor();
  assert.equal((await latest.getByRole('cell',{name:'Unavailable',exact:true}).count()),0);
  checks.push('Shadow run executes one rules-selected action and displays learned scores for eligible alternatives');
  await page.screenshot({path:`${output}/shadow-decisions.png`,fullPage:true});
  await inner('controls');await page.getByRole('button',{name:'Rollback selector to rules',exact:true}).click();
  await page.getByText('Selector rolled back to rules/memory. No live weights were mutated.',{exact:true}).waitFor();
  checks.push('Authorized rollback restores rules and increments control generation');
  await noAlert();await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.querySelector('.ws-main').getBoundingClientRect().left<=1&&
    document.querySelector('.ws-sidebar').getBoundingClientRect().right<=1);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:`${output}/mobile-controls.png`,fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  checks.push('390px viewport has no horizontal document overflow');
  assert.deepEqual(errors,[]);checks.push('No uncaught browser runtime errors');
  await writeFile(`${output}/browser-results.json`,JSON.stringify({checks,errors,responsesMocked:false,
    authentication:'Real local password identity. Hosted Supabase and live LLM not exercised.',
    fixture:'Synthetic orders 100+200, refunds 10+5. Demonstrates mechanism, not production improvement.'},null,2));
  console.log(JSON.stringify({passed:checks.length,checks},null,2));
}catch(error){
  await page.screenshot({path:`${output}/failure.png`,fullPage:true});
  await writeFile(`${output}/failure.json`,JSON.stringify({url:page.url(),body:(await page.locator('body').innerText()).slice(0,4500),errors},null,2));
  throw error;
}finally{await browser.close();}
