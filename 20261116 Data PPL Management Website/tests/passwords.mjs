import assert from 'node:assert/strict';
import {chromium} from '@playwright/test';
import {createApplication,httpServer} from '../server/index.mjs';
import {transaction} from '../server/database.mjs';
import {hashPassword,digest} from '../server/auth.mjs';

import {INITIAL_PASSWORD} from './test-credentials.mjs';
const env={INITIAL_ACCOUNT_PASSWORD:INITIAL_PASSWORD,DB_HOST:'127.0.0.1',DB_PORT:'13306',DB_USER:'navigator_test',DB_PASSWORD:'test-password-only',DB_NAME:'navigator_test',ADMIN_EMAIL:'owner@test.local',APP_ORIGIN:'http://127.0.0.1:3103'};
assert.equal(env.DB_HOST,'127.0.0.1');assert.equal(env.DB_NAME,'navigator_test');
let app=await createApplication({mfaRequired:false,env}),browser,server;
const adminPassword='Owner-personal-test-4936',personalPassword='Member-personal-test-4936';
const prefix='password-'+Date.now(),member=prefix+'@test.local',pending=prefix+'-pending@test.local',legacy=prefix+'-legacy@test.local',uiMember=prefix+'-ui@test.local',failed=prefix+'-rollback@test.local';
const testEmails=[member,pending,legacy,uiMember,failed];
const call=async(path,method='GET',body,cookie='',application=app,headers={})=>{
 const res=await application.handle(new Request(env.APP_ORIGIN+path,{method,headers:{Origin:env.APP_ORIGIN,'Content-Type':'application/json',...(cookie?{cookie}:{}),...headers},body:method==='GET'?undefined:JSON.stringify(body)}),'password-test');
 let value;try{value=await res.clone().json()}catch{value=null}return {status:res.status,body:value,response:res};
};
const cookieOf=r=>r.response.headers.get('Set-Cookie')?.split(';')[0]||'';
const login=(email,password)=>call('/api/auth/login','POST',{email,password});
const query=(sql,params=[])=>transaction(app.pool,c=>c.query(sql,params));
try{
 await transaction(app.pool,async c=>{
  await c.query('DELETE FROM login_limits');
  await c.query('UPDATE accounts SET password_hash=$1 WHERE email=$2',[await hashPassword(adminPassword),env.ADMIN_EMAIL]);
  await c.query('UPDATE account_password_state SET must_change_password=0 WHERE email=$1',[env.ADMIN_EMAIL]);
  for(const email of [pending,legacy])await c.query("INSERT INTO members(email,user_id,role_id,enabled) VALUES($1,NULL,'sa',1)",[email]);
  await c.query('UPDATE members SET user_id=$1 WHERE email=$2',[prefix+'-legacy-id',legacy]);
  await c.query('INSERT INTO accounts(email,password_hash) VALUES($1,$2)',[legacy,await hashPassword(personalPassword)]);
 });
 const preserved=(await query('SELECT password_hash FROM accounts WHERE email=$1',[legacy])).rows[0].password_hash;
 await app.pool.end();app=await createApplication({mfaRequired:false,env});
 assert.equal((await query('SELECT password_hash FROM accounts WHERE email=$1',[legacy])).rows[0].password_hash,preserved,'existing personal credentials are preserved');
 assert.equal((await login(legacy,personalPassword)).body.mustChangePassword,false);
 assert.equal((await login(pending,INITIAL_PASSWORD)).body.mustChangePassword,true,'previously unactivated members receive an initial credential');
 const adminLogin=await login(env.ADMIN_EMAIL,adminPassword);assert.equal(adminLogin.status,200);const admin=cookieOf(adminLogin);
 assert.equal((await call('/api/auth/reset-password','POST',{email:member})).status,401);
 const created=await call('/api/admin/member','POST',{email:member,roleId:'sa'},admin);assert.equal(created.status,200);assert.equal(created.body.accountCreated,true);
 const stored=(await query('SELECT password_hash FROM accounts WHERE email=$1',[member])).rows[0].password_hash;
 assert(stored.startsWith('scrypt:'));assert(!stored.includes(INITIAL_PASSWORD));
 const initial=await login(member,INITIAL_PASSWORD);assert.equal(initial.status,200);assert.equal(initial.body.mustChangePassword,true);
 const restricted=cookieOf(initial),secondRestricted=cookieOf(await login(member,INITIAL_PASSWORD));
 for(const path of ['/api/me','/api/workspace','/api/admin','/api/source/download','/api/files/nonexistent','/api/reports/current/export?period=2026-11']){
  const r=await call(path,'GET',undefined,restricted,app,{'oai-authenticated-user-email':env.ADMIN_EMAIL,'oai-authenticated-user-id':'forged'});
  assert.equal(r.status,403,path);assert.equal(r.body.code,'PASSWORD_CHANGE_REQUIRED');
 }
 assert.equal((await call('/api/projects','POST',{name:'Blocked',type:'大数据'},restricted)).status,403);
 assert.equal((await call('/api/auth/reset-password','POST',{email:legacy},restricted)).status,403);
 assert.equal((await call('/','GET',undefined,restricted)).response.headers.get('Location'),'/login?change-password=required');
 assert.equal((await call('/api/auth/status','GET',undefined,restricted)).body.mustChangePassword,true);
 for(const values of [{currentPassword:'wrong',password:personalPassword},{currentPassword:INITIAL_PASSWORD,password:'short'},{currentPassword:INITIAL_PASSWORD,password:INITIAL_PASSWORD}])assert.equal((await call('/api/auth/password','POST',values,restricted)).status,400);
 assert.equal((await call('/api/auth/password','POST',{currentPassword:INITIAL_PASSWORD,password:personalPassword,displayName:'Test Member'},restricted,app,{Origin:'https://untrusted.local'})).status,403);
 assert.equal((await call('/api/auth/password','POST',{currentPassword:INITIAL_PASSWORD,password:personalPassword,displayName:'Test Member'},restricted)).status,200);
 for(const cookie of [restricted,secondRestricted])assert.equal((await call('/api/workspace','GET',undefined,cookie)).status,401);
 assert.equal((await login(member,INITIAL_PASSWORD)).status,401);
 const normal=await login(member,personalPassword);assert.equal(normal.body.mustChangePassword,false);const memberCookie=cookieOf(normal);
 assert.equal((await call('/api/workspace','GET',undefined,memberCookie)).status,200);
 assert.equal((await call('/api/auth/password','POST',{currentPassword:personalPassword,password:personalPassword},memberCookie)).status,400);
 assert.equal((await call('/api/auth/reset-password','POST',{email:legacy},memberCookie)).status,403,'member cannot reset another account');
 assert.equal((await call('/api/auth/reset-password','POST',{email:env.ADMIN_EMAIL},admin)).status,400,'self reset uses change-password instead');
 const update=await call('/api/admin/member','POST',{email:member,roleId:'sa',_version:2},admin);assert.equal(update.status,200);assert.equal(update.body.accountCreated,false);
 assert.equal((await login(member,personalPassword)).body.mustChangePassword,false,'role edit does not reset the password');
 const activeCookie=cookieOf(await login(member,personalPassword));
 await query("CREATE TRIGGER fail_password_audit BEFORE INSERT ON audit FOR EACH ROW BEGIN IF NEW.action LIKE '重置为初始密码：%' OR NEW.action LIKE '创建初始密码账号：%' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test password audit failure'; END IF; END");
 try{
  assert.equal((await call('/api/auth/reset-password','POST',{email:member},admin)).status,500);
  assert.equal((await call('/api/workspace','GET',undefined,activeCookie)).status,200,'failed reset rolls back session revocation');
  assert.equal((await login(member,personalPassword)).body.mustChangePassword,false,'failed reset preserves password state');
  assert.equal((await call('/api/admin/member','POST',{email:failed,roleId:'sa'},admin)).status,500);
  assert.equal((await query('SELECT email FROM members WHERE email=$1',[failed])).rows.length,0,'account and member creation roll back together');
 }finally{await query('DROP TRIGGER fail_password_audit')}
 // Pause a request after it has looked up a session, before it locks credentials.
 // A concurrent administrator reset must make that in-flight session invalid.
 let reached,release;const reachedPromise=new Promise(r=>reached=r),releasePromise=new Promise(r=>release=r);let pause=false;
 const tokenHash=digest(activeCookie.split('=')[1]);
 const pausedPool={...app.pool,connect:async()=>{const c=await app.pool.connect();return {...c,query:async(sql,values=[])=>{const r=await c.query(sql,values);if(pause&&sql.startsWith('SELECT email FROM sessions')&&values[0]===tokenHash){pause=false;reached();await releasePromise}return r}}}};
 const pausedApp=await createApplication({mfaRequired:false,env,pool:pausedPool});pause=true;
 const staleChange=call('/api/auth/password','POST',{currentPassword:personalPassword,password:'Racing-password-test-4936'},activeCookie,pausedApp);
 await reachedPromise;
 try{assert.equal((await call('/api/auth/reset-password','POST',{email:member},admin)).status,200)}finally{release()}
 assert.equal((await staleChange).status,401,'reset wins over stale password-change request');
 assert.equal((await call('/api/workspace','GET',undefined,activeCookie)).status,401);
 assert.equal((await login(member,personalPassword)).status,401);
 assert.equal((await login(member,INITIAL_PASSWORD)).body.mustChangePassword,true);
 const adminState=(await call('/api/admin','GET',undefined,admin)).body;assert.equal(adminState.members.find(m=>m.email===member).must_change_password,true);
 for(const path of ['/api/auth/invite','/api/auth/activate'])assert.equal((await call(path,'POST',{email:member,token:'a'.repeat(64),password:personalPassword},admin)).status,410);
 const disabled=await call('/api/admin/member','POST',{email:member,roleId:'sa',enabled:false,_version:3},admin);assert.equal(disabled.status,200);
 assert.equal((await login(member,INITIAL_PASSWORD)).status,401);assert.equal((await call('/api/auth/reset-password','POST',{email:member},admin)).status,403);
 await query('DELETE FROM login_limits');

 server=httpServer(app);await new Promise(r=>server.listen(3103,'127.0.0.1',r));
 browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000},locale:'en-US'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(env.APP_ORIGIN+'/login');await page.getByLabel('Email',{exact:true}).fill(env.ADMIN_EMAIL);await page.getByLabel('Password',{exact:true}).fill(adminPassword);await page.getByRole('button',{name:'Sign in'}).click();
 await page.locator('#nav button').filter({hasText:'Members & roles'}).click();await page.getByRole('button',{name:'Add member'}).click();
 await page.locator('[name=email]').fill(uiMember);await page.locator('[name=roleId]').selectOption('sa');await page.getByRole('button',{name:'Save',exact:true}).click();
 await page.getByRole('heading',{name:'Account initial password'}).waitFor();assert.equal(await page.getByLabel('Initial password',{exact:true}).inputValue(),INITIAL_PASSWORD);
 await page.locator('#modal button[type=button]').last().click();
 const row=page.locator('#members .listrow').filter({hasText:uiMember});await row.getByRole('button',{name:'Reset password',exact:true}).click();
 await page.getByRole('heading',{name:'Reset password'}).waitFor();await page.getByRole('button',{name:'Confirm reset'}).click();await page.getByRole('heading',{name:'Account initial password'}).waitFor();
 await page.locator('#modal button[type=button]').last().click();await page.screenshot({path:'artifacts/password-admin-en.png',fullPage:true});
 const context=await browser.newContext({viewport:{width:390,height:844},locale:'zh-CN'}),first=await context.newPage();first.on('pageerror',e=>errors.push(e.message));
 await first.goto(env.APP_ORIGIN+'/login');await first.getByLabel('邮箱',{exact:true}).fill(uiMember);await first.getByLabel('密码',{exact:true}).fill(INITIAL_PASSWORD);await first.getByRole('button',{name:'登录'}).click();
 await first.getByRole('heading',{name:'首次登录，请修改密码'}).waitFor();assert.equal(await first.locator('#email').inputValue(),uiMember);
 await first.reload();await first.getByRole('heading',{name:'首次登录，请修改密码'}).waitFor();
 await first.goto(env.APP_ORIGIN+'/');await first.getByRole('heading',{name:'首次登录，请修改密码'}).waitFor();
 assert.equal(await first.evaluate(()=>fetch('/api/workspace').then(r=>r.status)),403);
 await first.screenshot({path:'artifacts/password-first-login-zh.png',fullPage:true});
 await first.getByRole('button',{name:'English',exact:true}).click();await first.getByRole('heading',{name:'Change your initial password'}).waitFor();
 assert.equal(await first.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'English mobile password page fits');
 await first.getByLabel('Display name *',{exact:true}).fill('Test Member');await first.getByLabel('Current password',{exact:true}).fill(INITIAL_PASSWORD);await first.getByLabel('New password (at least 12 characters)',{exact:true}).fill(personalPassword);await first.getByLabel('Confirm new password',{exact:true}).fill('Mismatched-test-password');
 await first.getByRole('button',{name:'Save new password'}).click();await first.getByText('Passwords do not match.',{exact:true}).waitFor();
 await first.getByLabel('Confirm new password',{exact:true}).fill(personalPassword);await first.screenshot({path:'artifacts/password-first-login-en.png',fullPage:true});await first.getByRole('button',{name:'Save new password'}).click();
 await first.getByText('Password updated. Sign in with your new password.',{exact:true}).waitFor();
 await first.getByLabel('Password',{exact:true}).fill(personalPassword);await first.getByRole('button',{name:'Sign in'}).click();await first.locator('#nav button').filter({hasText:'Projects'}).waitFor();
 await first.reload();await first.locator('#nav button').filter({hasText:'Projects'}).waitFor();
 await row.getByRole('button',{name:'Reset password',exact:true}).click();await page.getByRole('button',{name:'Confirm reset'}).click();await page.getByRole('heading',{name:'Account initial password'}).waitFor();
 assert.equal(await first.evaluate(()=>fetch('/api/workspace').then(r=>r.status)),401);
 await first.reload();await first.getByRole('heading',{name:'Sign in to your workspace'}).waitFor();await first.getByLabel('Email',{exact:true}).fill(uiMember);await first.getByLabel('Password',{exact:true}).fill(INITIAL_PASSWORD);await first.getByRole('button',{name:'Sign in'}).click();await first.getByRole('heading',{name:'Change your initial password'}).waitFor();
 await first.getByRole('button',{name:'Sign out',exact:true}).click();await first.getByRole('heading',{name:'Sign in to your workspace'}).waitFor();
 await first.goto(env.APP_ORIGIN+'/login#activate='+'a'.repeat(64));await first.getByText('Password links are no longer supported. Ask your administrator to reset your initial password.',{exact:true}).waitFor();
 assert.deepEqual(errors,[]);
 console.log('PASS: personal passwords preserved; pending accounts initialized; password hashes; mandatory server-side gate; policy and CSRF; old session revocation; reset/change race; atomic rollback; permissions and disabled accounts; retired links; bilingual admin and mobile first-login/reset browser flow');
}finally{
 if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));
 await transaction(app.pool,async c=>{for(const email of testEmails){await c.query('DELETE FROM sessions WHERE email=$1',[email]);await c.query('DELETE FROM invitations WHERE email=$1',[email]);await c.query('DELETE FROM account_password_state WHERE email=$1',[email]);await c.query('DELETE FROM accounts WHERE email=$1',[email]);await c.query('DELETE FROM members WHERE email=$1',[email])}});
 await app.pool.end();
}
