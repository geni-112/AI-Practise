import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '@playwright/test';
import QRCode from 'qrcode';
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1100,height:900}});
const origin='https://mfa-ui.invalid';
let authenticated=false,enabled=false,verified=false;const errors=[];
const qr=await QRCode.toDataURL('otpauth://totp/Test?secret=JBSWY3DPEHPK3PXP');
const codes=Array.from({length:8},(_,i)=>('abcd-1234-'.repeat(3)+'abcd-123'+i));
await context.addInitScript(()=>localStorage.setItem('navigator-language','en'));
await context.route('**/*',async route=>{
 const p=new URL(route.request().url()).pathname;
 if(p==='/api/auth/status')return route.fulfill({json:{authenticated,email:'admin@example.invalid',mustChangePassword:false,mfa:{required:true,enabled,verified}}});
 if(p==='/api/auth/login'){authenticated=true;return route.fulfill({json:{ok:true}})}
 if(p==='/api/auth/mfa/enroll')return route.fulfill({json:{secret:'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',qr}});
 if(p==='/api/auth/mfa/confirm'){enabled=true;verified=true;return route.fulfill({json:{ok:true,recoveryCodes:codes}})}
 if(p==='/api/auth/mfa/verify'){
  const body=route.request().postDataJSON();
  if(body.code==='000000')return route.fulfill({status:400,json:{error:'验证码不正确、已使用或已过期'}});
  verified=true;return route.fulfill({json:{ok:true}});
 }
 if(p==='/')return route.fulfill({body:'<h1>Workspace</h1>',contentType:'text/html'});
 const file=p==='/login'?'login.html':p.slice(1);
 try{const body=await fs.readFile(new URL('../public/'+file,import.meta.url));return route.fulfill({body,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.svg')?'image/svg+xml':'text/html'})}catch{return route.abort()}
});
try{
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
 await page.goto(origin+'/login');await page.locator('[data-language="en"]').click();
 await page.locator('#email').fill('admin@example.invalid');await page.locator('#password').fill('synthetic-password');
 await page.locator('#loginButton').click();await page.locator('#mfaStartForm').waitFor({state:'visible'});
 assert.match(await page.locator('#authTitle').innerText(),/administrator/i);
 await page.locator('#mfaPassword').fill('synthetic-password');await page.locator('#mfaStartForm button').click();
 await page.locator('#mfaQr').waitFor({state:'visible'});assert((await page.locator('#mfaQr').getAttribute('src')).startsWith('data:image/png'));
 await page.locator('#mfaCode').fill('123456');await page.locator('#mfaCodeForm button[type="submit"]').click();
 await page.locator('#mfaRecovery').waitFor({state:'visible'});assert.equal(await page.locator('#mfaContinue').isDisabled(),true);
 assert.equal((await page.locator('#mfaRecoveryCodes').innerText()).split('\n').length,8);
 const download=page.waitForEvent('download');await page.locator('#mfaDownload').click();assert.equal((await download).suggestedFilename(),'data-solutions-hub-recovery-codes.txt');
 await page.locator('#mfaSaved').check();await page.locator('#mfaContinue').click();await page.waitForURL(origin+'/');
 verified=false;await page.goto(origin+'/login');await page.locator('#mfaCodeForm').waitFor({state:'visible'});
 await page.locator('#mfaCode').fill('000000');await page.locator('#mfaCodeForm button[type="submit"]').click();
 await page.getByText('The code is incorrect, already used or expired.').waitFor();
 await page.locator('[data-language="zh"]').click();await page.getByText('验证码不正确、已使用或已过期').waitFor();
 await page.locator('#mfaCode').fill(codes[0]);await page.locator('#mfaCodeForm button[type="submit"]').click();await page.waitForURL(origin+'/');
 assert.deepEqual(errors,[]);console.log('PASS: bilingual administrator enrollment, recovery download acknowledgement and challenge/error UI');
}finally{await browser.close()}
