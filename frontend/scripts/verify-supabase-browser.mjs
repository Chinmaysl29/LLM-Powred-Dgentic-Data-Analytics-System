/** Read-only live project verification. Never creates accounts or sends email. */
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { lookup } from 'node:dns/promises';

const output=process.env.SUPABASE_EVIDENCE_DIR||'/tmp/supabase-proof';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({args:['--disable-dev-shm-usage']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const {address}=await lookup('frontend');
const base=process.env.SUPABASE_BROWSER_BASE||`http://${address}:5173`;
const errors=[];page.on('pageerror',error=>errors.push(error.message));
try{
  await page.goto(base+'/verified-learning');
  await page.waitForURL('**/login');
  await page.locator('#login-email').waitFor();
  const result=await page.evaluate(async()=>{
    const {getSupabaseClient,isSupabaseConfigured}=await import('/src/lib/supabase/client.ts');
    const client=getSupabaseClient();
    const session=await client.auth.getSession();
    const settings=await fetch(client.supabaseUrl+'/auth/v1/settings',{headers:{apikey:client.supabaseKey}});
    const auth=await settings.json();
    const probe=await client.from('profiles').select('id').limit(0);
    return {configured:isSupabaseConfigured(),project:new URL(client.supabaseUrl).hostname,
      projectScopedStorage:client.auth.storageKey.includes('qjcudbkamhldswcyxypv'),
      anonymousSession:session.data.session===null,sessionError:session.error?.name||null,
      authSettingsHttp:settings.status,emailAuthEnabled:auth.external?.email,
      profilesProbe:{http:probe.status,errorCode:probe.error?.code||null},returnedRows:probe.data?.length||0};
  });
  assert.equal(result.configured,true);assert.equal(result.project,'qjcudbkamhldswcyxypv.supabase.co');
  assert.equal(result.projectScopedStorage,true);assert.equal(result.sessionError,null);
  assert.equal(result.authSettingsHttp,200);assert.equal(result.emailAuthEnabled,true);
  assert.equal(result.returnedRows,0);assert.deepEqual(errors,[]);
  await page.screenshot({path:output+'/login.png',fullPage:true});
  const evidence={...result,errors,responsesMocked:false,accountCreated:false,
    signedInUserTest:'Not run: a confirmed project account and password were not supplied.',
    hostedDatabaseMigration:'Pending PostgreSQL connection credentials; no hosted schema/data writes performed.'};
  await writeFile(output+'/browser.json',JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence,null,2));
}catch(error){
  await writeFile(output+'/failure.json',JSON.stringify({url:page.url(),errors,body:(await page.locator('body').innerText()).slice(0,2000)},null,2));
  throw error;
}finally{await browser.close();}
