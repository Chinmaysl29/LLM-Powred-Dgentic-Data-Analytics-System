import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({channel:'chrome',headless:false,ignoreDefaultArgs:['--disable-backgrounding-occluded-windows','--disable-background-timer-throttling','--disable-renderer-backgrounding']});
const context=await browser.newContext({reducedMotion:'no-preference'});
const page=await context.newPage();
try{
 await page.goto('http://localhost:5173/login');await page.bringToFront();await page.waitForSelector('[data-motion=running]');
 const client=await context.newCDPSession(page);await client.send('Emulation.setFocusEmulationEnabled',{enabled:false});
 const other=await context.newPage();await other.goto('about:blank');const otherClient=await context.newCDPSession(other);await otherClient.send('Emulation.setFocusEmulationEnabled',{enabled:false});await other.bringToFront();
 await page.waitForFunction(()=>document.hidden===true);
 const paused=await page.locator('.progress-meta-right').innerText();await other.waitForTimeout(1500);
 assert.equal(await page.locator('.progress-meta-right').innerText(),paused);
 await page.bringToFront();await page.waitForSelector('[data-motion=running]');
 const before=await page.locator('.progress-meta-right').innerText();await page.waitForTimeout(500);
 assert.notEqual(await page.locator('.progress-meta-right').innerText(),before);
 const result={actualBrowserTabSwitch:true,hiddenWhileOtherTabActive:true,clockPausedWhileHidden:true,resumed:true};
 await writeFile('.ui-review/motion-validation/tab-switch.json',JSON.stringify(result,null,2));console.log('PASS',result);
}finally{await browser.close();}

