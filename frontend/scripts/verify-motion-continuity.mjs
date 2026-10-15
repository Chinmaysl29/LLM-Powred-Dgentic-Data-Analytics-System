import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const origin = process.env.MOTION_ORIGIN || 'http://localhost:5173';
const duration = Number(process.env.MOTION_QA_MS || 600000);
const out = new URL('../.ui-review/motion-validation/', import.meta.url);
await mkdir(out, {recursive:true});
const browser = await chromium.launch({channel:'msedge', headless:true});
const context = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'no-preference'});
const page = await context.newPage();
const errors=[]; const requests=[]; const samples=[]; const screenshots=new Set();
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>requests.push({time:Date.now(),url:r.url(),type:r.resourceType()}));
const report={origin,duration,errors,samples,checks:{},completed:false};
try {
  await page.goto(origin+'/login');
  await page.bringToFront();
  await page.waitForSelector('[data-motion="running"]',{timeout:30000});
  await page.evaluate(()=>{
    window.motionQA={frames:0,cycles:[],cycle:{stages:[],minBarHeight:999,maxBarHeight:0,morphPaths:[]},last:0,blank:0,hidden:0,bounds:[],start:performance.now()};
    const q=window.motionQA; let lastSample=0;
    function frame(now){
      q.frames++;
      if(now-lastSample>40){
        lastSample=now;
        if(document.hidden)q.hidden++;
        const t=parseFloat(document.querySelector('.progress-meta-right span span')?.textContent || '0');
        const stage=document.querySelector('.viewport-stage-tag')?.textContent;
        const title=document.querySelector('.viewport-stage-title')?.textContent;
        if(t<q.last && q.last>6){q.cycles.push(q.cycle);q.cycle={stages:[],minBarHeight:999,maxBarHeight:0,morphPaths:[]};}
        q.last=t;
        if(!q.cycle.stages.includes(title))q.cycle.stages.push(title);
        const layers=['.raw-stage-layer','.cleaning-stage-layer','.chart-morph-container'].map(s=>Number(getComputedStyle(document.querySelector(s)).opacity));
        if(Math.max(...layers)<.45)q.blank++;
        const p=document.querySelector('.chart-morph-container path');
        if(t>=4 && t<4.2)q.cycle.minBarHeight=Math.min(q.cycle.minBarHeight,p.getBBox().height);
        if(t>4.8 && t<4.95)q.cycle.maxBarHeight=Math.max(q.cycle.maxBarHeight,p.getBBox().height);
        if(t>=5.1 && t<5.8 && q.cycle.morphPaths.length<3){const d=p.getAttribute('d');if(!q.cycle.morphPaths.includes(d))q.cycle.morphPaths.push(d);}
        const r=document.querySelector('.single-motion-viewport').getBoundingClientRect();
        const f=document.querySelector('.cinematic-auth-card').getBoundingClientRect();
        if(q.bounds.length<1600)q.bounds.push([r.x,r.y,r.width,r.height,f.x,f.y,f.width,f.height]);
      }
      q.raf=requestAnimationFrame(frame);
    }
    q.raf=requestAnimationFrame(frame);
  });
  const cdp=await context.newCDPSession(page);
  await cdp.send('Performance.enable');
  const started=Date.now();const requestBaseline=requests.length;let sampleIndex=0;
  // Real wall-clock playback. No accelerated clock or synthetic elapsed time.
  while(Date.now()-started<duration){
    await page.waitForTimeout(1000);
    const info=await page.evaluate(()=>({stage:document.querySelector('.viewport-stage-title').textContent,cycles:window.motionQA.cycles.length,frames:window.motionQA.frames,elapsed:performance.now()-window.motionQA.start,visibility:document.visibilityState}));
    if(!screenshots.has(info.stage) && screenshots.size<8){screenshots.add(info.stage);await page.locator('.pipeline-card').screenshot({path:fileURLToPath(new URL(`stage-${screenshots.size}.png`,out))});}
    if(Date.now()-started>=sampleIndex*60000){
      const metrics=await cdp.send('Performance.getMetrics'); const dom=await cdp.send('Memory.getDOMCounters');
      const heap=metrics.metrics.find(m=>m.name==='JSHeapUsedSize')?.value;
      await cdp.send('HeapProfiler.collectGarbage');
      const retained=(await cdp.send('Runtime.getHeapUsage')).usedSize;
      samples.push({seconds:(Date.now()-started)/1000,...info,heap,retained,...dom});
      console.log(JSON.stringify(samples.at(-1)));sampleIndex++;
    }
  }
  const q=await page.evaluate(()=>{cancelAnimationFrame(window.motionQA.raf);return window.motionQA;});
  report.runtime={seconds:(Date.now()-started)/1000,frames:q.frames,rafFps:q.frames/(q.elapsed||((Date.now()-started)/1000)),cycles:q.cycles.length,blankSamples:q.blank,hiddenSamples:q.hidden,cyclesDetail:q.cycles};
  report.runtime.rafFps=q.frames/((Date.now()-started)/1000);
  const complete=q.cycles.slice(1);
  assert(complete.length>=10,'Ten full loops required');
  assert(complete.every(c=>c.stages.length===8 && c.minBarHeight<16 && c.maxBarHeight>=35 && c.morphPaths.length===3),'Stage/growth/morph regression');
  assert.equal(q.blank,0);assert.equal(q.hidden,0);
  assert(q.bounds.every(b=>b.every((v,i)=>Math.abs(v-q.bounds[0][i])<.5)),'Layout moved');
  report.checks.loops=true;report.checks.stableLayout=true;report.checks.noBlank=true;
  report.animationRequests=requests.slice(requestBaseline).filter(r=>!r.url.includes('/@vite'));
  assert.equal(report.animationRequests.length,0,'Unexpected requests during playback');
  await page.locator('input[type=email]').pressSequentially('motion.qa@example.com',{delay:30});
  const password=page.locator('input[type=password]');await password.pressSequentially('illustrative-test-only',{delay:30});
  assert.equal(await password.inputValue(),'illustrative-test-only');assert(await password.evaluate(e=>e===document.activeElement));
  report.checks.input=true;
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForSelector('[data-motion="reduced"]');
  const reduced=await page.locator('.chart-morph-container').innerHTML();await page.waitForTimeout(1200);
  assert.equal(await page.locator('.chart-morph-container').innerHTML(),reduced);
  assert.equal(await page.locator('.chart-morph-container').evaluate(e=>getComputedStyle(e).opacity),'1');
  report.checks.reducedMotion=true;
  await page.emulateMedia({reducedMotion:'no-preference'});await page.waitForSelector('[data-motion="running"]');
  const second=await context.newPage();await second.goto('about:blank');await second.bringToFront();
  report.tabSwitchHidden=await page.evaluate(()=>document.hidden);await page.waitForTimeout(1000);
  await page.bringToFront();await second.close();await page.waitForSelector('[data-motion="running"]');
  // Chromium's headless tabs may remain visible; separately exercise real lifecycle suspension.
  await cdp.send('Page.setWebLifecycleState',{state:'frozen'});await new Promise(r=>setTimeout(r,1200));
  await cdp.send('Page.setWebLifecycleState',{state:'active'});await page.bringToFront();await page.waitForTimeout(500);
  const before=await page.locator('.progress-meta-right').innerText();await page.waitForTimeout(500);
  assert.notEqual(await page.locator('.progress-meta-right').innerText(),before);report.checks.lifecycle=true;
  await page.setViewportSize({width:375,height:900});await page.waitForTimeout(1000);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:fileURLToPath(new URL('mobile.png',out)),fullPage:true});report.checks.mobile=true;
  assert.equal(errors.length,0);
  report.completed=true;
} catch(error){report.failure=error.stack;console.error(error);process.exitCode=1;}
finally {await writeFile(new URL('report.json',out),JSON.stringify(report,null,2));await browser.close();}
