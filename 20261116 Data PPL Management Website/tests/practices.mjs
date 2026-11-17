import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
import {textModelReply,verifyPracticeWorkflows} from './practice-workflows.mjs';
import {createApplication,httpServer} from '../server/index.mjs';
import {transaction} from '../server/database.mjs';
import {hashPassword} from '../server/auth.mjs';
import {normalizeEndpoint,validateAnalysis,validateImage,visionProbe} from '../server/architecture-model.mjs';

import {fixture} from './architecture-fixture.mjs';
import {INITIAL_PASSWORD} from './test-credentials.mjs';
const env={INITIAL_ACCOUNT_PASSWORD:INITIAL_PASSWORD,OCR_ENDPOINT:process.env.PRACTICE_OCR_ENDPOINT,DB_HOST:'127.0.0.1',DB_PORT:'13306',DB_USER:'navigator_test',DB_PASSWORD:'test-password-only',DB_NAME:'navigator_i18n_test',ADMIN_EMAIL:'i18n@test.local',APP_ORIGIN:'http://127.0.0.1:3104',UPLOAD_DIR:fileURLToPath(new URL('../.data/practice-test/uploads',import.meta.url)),MAAS_KEY_DIR:fileURLToPath(new URL('../.data/practice-test/private',import.meta.url))};
assert.equal(env.DB_HOST,'127.0.0.1');assert.equal(env.DB_NAME,'navigator_i18n_test');
const probe=visionProbe(),secret='synthetic-maas-test-key',password='Practice-test-password-83',prefix='practice-'+Date.now();
let mode='normal',calls=0,app,server,browser;const records=[],members=[],errors=[];
const fakeFetch=async(url,options)=>{
 calls++;assert.equal(url,'https://api.modelarts-maas.com/v1/chat/completions');assert.equal(options.redirect,'error');assert.equal(options.headers.Authorization,'Bearer '+secret);
 const body=JSON.parse(options.body);if(body.model==='text-fixture')return textModelReply(body,fixture);assert.equal(body.model,'vision-fixture');assert(body.messages.at(-1).content.some(x=>x.type==='image_url'&&x.image_url.url.startsWith('data:image/png;base64,')));
 if(mode==='auth')return new Response('upstream-private-error-'+secret,{status:401});
 if(mode==='bad')return Response.json({choices:[{message:{content:'not JSON'},finish_reason:'stop'}]});
 if(mode==='truncated')return Response.json({choices:[{message:{content:'{}'},finish_reason:'length'}]});
 const content=body.messages.length===1?JSON.stringify({code:mode==='blind'?'wrong':probe.code}):JSON.stringify(fixture);
 return Response.json({choices:[{message:{content},finish_reason:'stop'}],usage:{prompt_tokens:80,completion_tokens:120,total_tokens:200}});
};
const call=async(p,method='GET',body,cookie='',headers={})=>{
 const response=await app.handle(new Request(env.APP_ORIGIN+'/api/'+p,{method,headers:{Origin:env.APP_ORIGIN,'Content-Type':'application/json',...(cookie?{cookie}:{}),...headers},body:method==='GET'?undefined:JSON.stringify(body)}),'practices-test');let value;try{value=await response.clone().json()}catch{}return {status:response.status,body:value,response};
};
const cookieOf=r=>r.response.headers.get('Set-Cookie')?.split(';')[0]||'';
const query=(sql,values=[])=>transaction(app.pool,c=>c.query(sql,values));
try{
 for(const endpoint of ['http://api.modelarts-maas.com/v1','https://evil.test/v1','https://api.modelarts-maas.com.evil.test/v1','https://api.modelarts-maas.com/v1?key=x','https://user:pass@api.modelarts-maas.com/v1'])assert.throws(()=>normalizeEndpoint(endpoint));
 assert.equal(normalizeEndpoint('https://api.modelarts-maas.com/v1'),'https://api.modelarts-maas.com/v1/chat/completions');assert.deepEqual(validateAnalysis(fixture),fixture);
 const invalid=structuredClone(fixture);invalid.mappings[0].serviceIds=['fictional-service'];assert.throws(()=>validateAnalysis(invalid));invalid.mappings[0].serviceIds=['obs'];invalid.flows[0].to='missing';assert.throws(()=>validateAnalysis(invalid));
 assert(validateImage(probe.image.toString('base64'),'image/png').length>0);assert.throws(()=>validateImage(Buffer.from('<svg/>').toString('base64'),'image/png'));
 app=await createApplication({mfaRequired:false,env,maasFetch:fakeFetch,visionProbe:()=>probe});
 await query("DELETE FROM architecture_analyses WHERE title IN ('Architecture fixture <script>alert(1)</script>','Malformed response fixture','Browser architecture fixture')");
 await query('DELETE FROM login_limits');await query("DELETE FROM architecture_usage WHERE owner_email=$1",[env.ADMIN_EMAIL]);
 await query("DELETE FROM integration_settings WHERE id='maas'");
 await query('UPDATE accounts SET password_hash=$1 WHERE email=$2',[await hashPassword(password),env.ADMIN_EMAIL]);await query('UPDATE account_password_state SET must_change_password=0 WHERE email=$1',[env.ADMIN_EMAIL]);
 const login=await call('auth/login','POST',{email:env.ADMIN_EMAIL,password}),cookie=cookieOf(login);assert.equal(login.status,200);
 assert.equal((await call('practices')).status,401);
 const cfg=(await call('practices/config','GET',undefined,cookie)).body;assert.equal(cfg.ready,false);
 const settings={inputMode:'vision',_version:cfg._version,endpoint:'https://api.modelarts-maas.com/v1',model:'vision-fixture',region:'test-region',apiKey:secret,enabled:true,dailyLimit:100,maxTokens:8192};
 const saved=await call('practices/config','POST',settings,cookie);assert.equal(saved.status,200);assert.equal(saved.body.ready,false);assert(!JSON.stringify(saved.body).includes(secret));
 const encrypted=(await query("SELECT payload FROM integration_settings WHERE id='maas'")).rows[0].payload;assert(!encrypted.includes(secret));assert(JSON.parse(encrypted).secret);
 assert.equal((await call('practices/config','POST',settings,cookie)).status,409,'stale configuration rejected');
 mode='blind';const blind=await call('practices/test','POST',{},cookie);assert.equal(blind.status,400);assert.equal(blind.body.ready,false);
 mode='auth';const authFailure=await call('practices/test','POST',{},cookie);assert.equal(authFailure.status,400);assert(!JSON.stringify(authFailure.body).includes(secret));
 mode='normal';assert.equal((await call('practices/test','POST',{},cookie)).body.ready,true);
 const upload={requestKey:crypto.randomUUID(),title:'Architecture fixture <script>alert(1)</script>',businessType:'大数据',targetRegion:'la-south-2 (Santiago)',language:'en',context:'Review the SQL path.',name:'diagram.png',mime:'image/png',base64:probe.image.toString('base64')};
 const created=await call('practices','POST',upload,cookie);assert.equal(created.status,202,JSON.stringify(created.body));records.push(created.body.id);assert.equal(created.body.status,'queued');
 assert.equal((await call('practices','POST',upload,cookie)).body.id,created.body.id,'duplicate submission does not duplicate a model call');
 assert.equal((await call('practices','POST',{...upload,requestKey:crypto.randomUUID()},cookie,{Origin:'https://untrusted.test'})).status,403);
 await app.practices.stop();await app.pool.end();app=await createApplication({mfaRequired:false,env,maasFetch:fakeFetch,visionProbe:()=>probe});
 assert.equal((await call('practices/'+created.body.id,'GET',undefined,cookie)).body.status,'queued','queue and session survive an application restart');
 assert.equal(await app.practices.runNext(),true);
 let done=(await call('practices/'+created.body.id,'GET',undefined,cookie)).body;assert.equal(done.status,'succeeded');assert.deepEqual(done.result,fixture);assert.equal(done.usage.total_tokens,200);
 assert.equal((await call('practices/'+done.id+'/image','GET',undefined,cookie)).response.headers.get('Content-Type'),'image/png');assert.equal((await call('practices/'+done.id+'/image')).status,401);
 const viewer=prefix+'-viewer@test.local';members.push(viewer);await call('admin/member','POST',{email:viewer,roleId:'viewer'},cookie);const initial=cookieOf(await call('auth/login','POST',{email:viewer,password:INITIAL_PASSWORD}));assert.equal((await call('practices','GET',undefined,initial)).status,403);await call('auth/password','POST',{currentPassword:INITIAL_PASSWORD,password,displayName:'Test Viewer'},initial);const viewerCookie=cookieOf(await call('auth/login','POST',{email:viewer,password}));assert.equal((await call('practices','GET',undefined,viewerCookie)).status,403);assert.equal((await call('practices/config','GET',undefined,viewerCookie)).status,403);
 mode='bad';const bad=await call('practices','POST',{...upload,requestKey:crypto.randomUUID(),title:'Malformed response fixture'},cookie);records.push(bad.body.id);await app.practices.runNext();const failed=(await call('practices/'+bad.body.id,'GET',undefined,cookie)).body;assert.equal(failed.status,'failed');assert.equal(failed.error_code,'INVALID_MODEL_RESPONSE');
 const failures=async()=>(await call('practices/'+failed.id+'/failures','GET',undefined,cookie)).body.items;
 const history=await failures();assert.equal(history.length,1);assert.equal(history[0].stage,'validation');assert.equal(history[0].validation_path,'$');assert.equal(history[0].validation_issue,'invalid_json');assert.equal(history[0].error_code,failed.error_code);assert.equal(history[0].timeout_seconds,600);
 assert.equal((await call('practices/'+failed.id+'/failures','GET')).status,401);
 mode='normal';assert.equal((await call('practices/'+failed.id+'/retry','POST',{_version:failed.version},cookie)).status,200);await app.practices.runNext();assert.equal((await call('practices/'+failed.id,'GET',undefined,cookie)).body.status,'succeeded');assert.deepEqual(await failures(),history);
 const archive=await call('practices/'+done.id+'/archive','POST',{_version:done.version},cookie);assert.equal(archive.status,200);assert.equal((await call('practices/'+done.id+'/restore','POST',{_version:done.version},cookie)).status,409);assert.equal((await call('practices/'+done.id+'/restore','POST',{_version:archive.body.version},cookie)).status,200);
 // Retry and connection tests are charged against the same explicit daily budget.
 const current=(await call('practices/config','GET',undefined,cookie)).body;
 assert.equal(current.analysisTimeoutMinutes,10);
 for(const minutes of [0,31,2.5])assert.equal((await call('practices/config','POST',{...current,apiKey:'',analysisTimeoutMinutes:minutes},cookie)).status,400);
 await call('practices/config','POST',{...current,apiKey:'',dailyLimit:1},cookie);const count=calls;assert.equal((await call('practices','POST',{...upload,requestKey:crypto.randomUUID()},cookie)).status,400);assert.equal(calls,count);
 await call('practices/config','POST',{...current,_version:current._version+1,apiKey:'',dailyLimit:100},cookie);
 await query('DELETE FROM architecture_usage WHERE owner_email=$1',[env.ADMIN_EMAIL]);
 server=httpServer(app);await new Promise(r=>server.listen(3104,'127.0.0.1',r));
 browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1600,height:1050},locale:'en-US'});page.on('pageerror',e=>errors.push(e.message));
 async function untranslated(label){const texts=await page.evaluate(()=>{const out=[],w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){const e=n.parentElement;if(e&&!e.closest('[data-user-content],[data-language],script,style,textarea')&&e.getClientRects().length&&/[\u3400-\u9fff]/.test(n.nodeValue))out.push(n.nodeValue.trim())}return [...new Set(out)].filter(Boolean)});assert.deepEqual(texts,[],label)}
 await page.goto(env.APP_ORIGIN+'/login');await page.getByLabel('Email',{exact:true}).fill(env.ADMIN_EMAIL);await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in'}).click();await page.locator('#nav button').filter({hasText:'Best practices'}).click();
 await page.locator('.practice-item').filter({hasText:'Architecture fixture'}).click();await page.getByRole('heading',{name:'Vendors and products'}).waitFor();await untranslated('architecture analysis');await page.screenshot({path:'artifacts/practice-review-en.png',fullPage:true});
 assert.equal(await page.locator('#practiceDetail script').count(),0,'model and title text are escaped');
 await page.getByRole('tab',{name:'Solution comparison'}).click();await page.getByRole('heading',{name:'Compare the designs'}).waitFor();await untranslated('solution comparison');await page.screenshot({path:'artifacts/practice-comparison-en.png',fullPage:true});
 const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Export analysis report'}).click();const download=await downloadEvent;await download.saveAs('artifacts/practice-report.html');const html=await fs.readFile('artifacts/practice-report.html','utf8');assert(html.includes('data:image/png;base64,'));assert(!html.includes('<script>'));assert(html.includes('Content-Security-Policy'));
 await page.getByRole('button',{name:'Upload architecture'}).click();await page.locator('[name=title]').fill('Browser architecture fixture');await page.locator('[name=image]').setInputFiles({name:'architecture.png',mimeType:'image/png',buffer:probe.image});await page.locator('[name=context]').fill('Synthetic architecture verification');await untranslated('upload form');
 await page.getByRole('button',{name:'Upload and analyze'}).click();await page.getByRole('heading',{name:'Browser architecture fixture',exact:true}).waitFor();await page.getByRole('heading',{name:'Compare the designs'}).waitFor({timeout:20000});
 const ws=(await call('practices','GET',undefined,cookie)).body;records.push(ws.items.find(i=>i.title==='Browser architecture fixture').id);
 await page.locator('header [data-language=zh]').click();await page.getByRole('tab',{name:'架构解读',exact:true}).click();await page.getByRole('heading',{name:'厂商与产品识别'}).waitFor();await page.screenshot({path:'artifacts/practice-review-zh.png',fullPage:true});
 await page.locator('header [data-language=en]').click();await page.setViewportSize({width:390,height:844});await page.screenshot({path:'artifacts/practice-mobile-en.png',fullPage:true});const overflow=await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2&&!e.closest('.practice-table,.practice-diagram,nav')).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width})).slice(0,12));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,JSON.stringify(overflow));
 await page.setViewportSize({width:1600,height:1050});await page.locator('#nav button').filter({hasText:'Members & roles'}).click();await page.getByRole('button',{name:'Configure MaaS'}).click();await page.getByRole('heading',{name:'Huawei Cloud MaaS settings'}).waitFor();await untranslated('MaaS settings');assert.equal(await page.locator('[name=inputMode] option[value=ocr]').textContent(),'Cloud-hosted OCR + text MaaS');assert.equal(await page.locator('[name=apiKey]').inputValue(),'');await page.screenshot({path:'artifacts/practice-maas-settings-en.png',fullPage:true});await page.getByRole('button',{name:'Save and test'}).click();await page.locator('#modal').waitFor({state:'hidden'});assert.deepEqual(errors,[]);
 if(env.OCR_ENDPOINT)await verifyPracticeWorkflows({app,call,cookie,viewerCookie,page,query,records,origin:env.APP_ORIGIN});
 assert.deepEqual(errors,[]);
 console.log('PASS: real MySQL queue and persistence, RBAC, forced-password gate, encrypted/redacted API keys, endpoint validation, actual visual challenge, structured output validation, daily limits, idempotency, retry, archive/version checks, bilingual UI, image upload, comparison diagram, standalone report export and mobile layout. MaaS provider mocked; live provider setup is still required.');
}finally{
 if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));if(app){await app.practices.stop();await transaction(app.pool,async c=>{await c.query('DELETE FROM architecture_usage');for(const id of records)await c.query('DELETE FROM architecture_analyses WHERE id=$1',[id]);await c.query("DELETE FROM architecture_analyses WHERE title='Browser architecture fixture'");for(const email of members){await c.query('DELETE FROM sessions WHERE email=$1',[email]);await c.query('DELETE FROM account_password_state WHERE email=$1',[email]);await c.query('DELETE FROM accounts WHERE email=$1',[email]);await c.query('DELETE FROM members WHERE email=$1',[email])}await c.query("DELETE FROM integration_settings WHERE id='maas'")});await app.pool.end()}
}
