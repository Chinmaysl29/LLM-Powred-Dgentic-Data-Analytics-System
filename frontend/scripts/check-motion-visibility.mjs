import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const b=await chromium.launch({channel:'msedge',headless:true});const p=await b.newPage({reducedMotion:'no-preference'});
try{
 await p.goto('http://localhost:5173/login');await p.waitForSelector('[data-motion=running]');
 await p.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
 const paused=await p.locator('.progress-meta-right').innerText();await p.waitForTimeout(1200);assert.equal(await p.locator('.progress-meta-right').innerText(),paused);
 await p.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});await p.waitForSelector('[data-motion=running]');
 const resumed=await p.locator('.progress-meta-right').innerText();await p.waitForTimeout(500);assert.notEqual(await p.locator('.progress-meta-right').innerText(),resumed);
 const result={syntheticVisibilityEvent:true,pausePass:true,resumePass:true,actualTabHiddenUnverified:'Automated Edge and Chrome tabs remained document.hidden=false after activation changes, even with focus emulation disabled.'};
 await writeFile('.ui-review/motion-validation/visibility.json',JSON.stringify(result,null,2));console.log(result);
}finally{await b.close();}
