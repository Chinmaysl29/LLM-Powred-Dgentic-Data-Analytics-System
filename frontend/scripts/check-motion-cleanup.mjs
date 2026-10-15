import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const b=await chromium.launch({channel:'msedge',headless:true});const p=await b.newPage({reducedMotion:'no-preference'});
await p.addInitScript(()=>{
 const request=window.requestAnimationFrame.bind(window),cancel=window.cancelAnimationFrame.bind(window);
 window.pipelineCallbacks=new Set();window.pipelineMaxCallbacks=0;
 window.requestAnimationFrame=cb=>{
  const pipeline=(new Error().stack||'').includes('useDataPipelineMotion');
  let id;id=request(t=>{window.pipelineCallbacks.delete(id);cb(t);});
  if(pipeline){window.pipelineCallbacks.add(id);window.pipelineMaxCallbacks=Math.max(window.pipelineMaxCallbacks,window.pipelineCallbacks.size);}return id;
 };
 window.cancelAnimationFrame=id=>{window.pipelineCallbacks.delete(id);cancel(id);};
});
try{
 await p.goto('http://localhost:5173/login');await p.waitForSelector('[data-motion=running]');
 for(let i=0;i<5;i++){
  await p.locator('.pipeline-motion-toggle-btn').click();await p.waitForSelector('[data-motion=reduced]');assert.equal(await p.evaluate(()=>window.pipelineCallbacks.size),0);
  await p.locator('.pipeline-motion-toggle-btn').click();await p.waitForSelector('[data-motion=running]');assert.equal(await p.evaluate(()=>window.pipelineCallbacks.size),1);
 }
 const maximum=await p.evaluate(()=>window.pipelineMaxCallbacks);assert.equal(maximum,1);
 await p.getByRole('link',{name:'Privacy Policy'}).click();await p.waitForURL('**/privacy');await p.locator('.pipeline-card').waitFor({state:'detached'});
 await p.waitForTimeout(300);assert.equal(await p.evaluate(()=>window.pipelineCallbacks.size),0);
 const result={pauseResumeCycles:5,maximumPendingPipelineCallbacks:maximum,pendingAfterUnmount:0};
 await writeFile('.ui-review/motion-validation/cleanup.json',JSON.stringify(result,null,2));console.log('PASS',result);
}finally{await b.close();}

