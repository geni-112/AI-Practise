import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1100,height:900}});
const origin='https://mfa-ui.invalid';
let authenticated=false,verified=false,confirmed=false,sends=0;const errors=[];
await context.addInitScript(()=>localStorage.setItem('data-ppl-language','en'));
await context.route('**/*',async route=>{
 const p=new URL(route.request().url()).pathname;
 if(p==='/api/auth/status')return route.fulfill({json:{authenticated,email:'admin@example.invalid',mustChangePassword:false,mfa:{required:true,enabled:true,verified,method:'email',destination:'ad***@example.invalid',retryAfter:0,deliveryStatus:'none'}}});
 if(p==='/api/auth/login'){authenticated=true;return route.fulfill({json:{ok:true}})}
 if(p==='/api/auth/mfa/email/send'){sends++;return route.fulfill({json:{status:confirmed?'sent':'confirmation_required',destination:'ad***@example.invalid',retryAfter:1}})}
 if(p==='/api/auth/mfa/email/verify'){
  if(route.request().postDataJSON().code==='000000')return route.fulfill({status:400,json:{error:'验证码不正确、已使用或已过期'}});
  verified=true;return route.fulfill({json:{ok:true}});
 }
 if(p==='/')return route.fulfill({body:'<h1>Workspace</h1>',contentType:'text/html'});
 const file=p==='/login'?'login.html':p.slice(1);
 try{const body=await fs.readFile(new URL('../public/'+file,import.meta.url));return route.fulfill({body,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.svg')?'image/svg+xml':'text/html'})}catch{return route.abort()}
});
try{
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
 await page.goto(origin+'/login');
 await page.locator('#email').fill('admin@example.invalid');await page.locator('#password').fill('synthetic-password');await page.locator('#loginButton').click();
 await page.getByText('Email sign-in verification',{exact:true}).waitFor();
 await page.getByText(/First time: open the Huawei Cloud confirmation email/).waitFor();
 assert.equal(await page.locator('#mfaDestination').innerText(),'ad***@example.invalid');
 assert.equal(await page.locator('#mfaQr').count(),0);
 assert.equal(sends,1);assert.equal(await page.locator('#mfaSend').isDisabled(),true);
 confirmed=true;await page.waitForFunction(()=>!document.querySelector('#mfaSend').disabled);await page.locator('#mfaSend').click();
 await page.getByText(/Code sent. It expires in 5 minutes/).waitFor();
 await page.locator('#mfaCode').fill('000000');await page.locator('#mfaCodeForm button[type="submit"]').click();
 await page.getByText('The code is incorrect, already used or expired.').waitFor();
 await page.locator('[data-language="zh"]').click();await page.getByText('验证码不正确、已使用或已过期').waitFor();
 await page.getByText('邮箱登录验证',{exact:true}).waitFor();
 await page.locator('#mfaCode').fill('123456');await page.locator('#mfaCodeForm button[type="submit"]').click();await page.waitForURL(origin+'/');
 assert.deepEqual(errors,[]);console.log('PASS: bilingual email sign-in, first-mail confirmation, automatic sending, resend cooldown and incorrect-code UI');
}finally{await browser.close()}
