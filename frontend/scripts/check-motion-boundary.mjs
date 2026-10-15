import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'no-preference'});
try {
 await page.goto('http://localhost:5173/login');await page.waitForSelector('[data-motion=running]');
 const boundary=await page.evaluate(()=>new Promise(resolve=>{
  let previous;
  function sample(){
   const snapshot={raw:Number(getComputedStyle(document.querySelector('.raw-stage-layer')).opacity),chart:Number(getComputedStyle(document.querySelector('.chart-morph-container')).opacity),transforms:[...document.querySelectorAll('.raw-token-board > div')].map(e=>e.style.transform),clock:parseFloat(document.querySelector('.progress-meta-right span span').textContent)};
   if(previous?.clock>6.8 && snapshot.clock<.1 && previous.raw>.9){resolve({before:previous,after:snapshot});return;}
   previous=snapshot;requestAnimationFrame(sample);
  }requestAnimationFrame(sample);
 }));
 assert(boundary.before.raw>.94 && boundary.after.raw>.94);
 assert(boundary.before.chart<.06 && boundary.after.chart<.06);
 const nums=s=>s.match(/-?[\d.]+(?=px)/g).map(Number);
 boundary.maxTokenDisplacement=Math.max(...boundary.before.transforms.flatMap((s,i)=>nums(s).map((v,j)=>Math.abs(v-nums(boundary.after.transforms[i])[j]))));
 assert(boundary.maxTokenDisplacement<1);
 await writeFile('.ui-review/motion-validation/boundary.json',JSON.stringify(boundary,null,2));
 console.log('PASS actual adjacent loop-boundary frames',JSON.stringify(boundary));
}finally{await browser.close();}
