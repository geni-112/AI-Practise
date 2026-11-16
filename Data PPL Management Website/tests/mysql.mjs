import assert from 'node:assert/strict';
import { createApplication, httpServer } from '../server/index.mjs';
import { hashPassword } from '../server/auth.mjs';
import { transaction } from '../server/database.mjs';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

import {INITIAL_PASSWORD} from './test-credentials.mjs';
const env={INITIAL_ACCOUNT_PASSWORD:INITIAL_PASSWORD,DB_HOST:'127.0.0.1',DB_PORT:'13306',DB_USER:'navigator_test',DB_PASSWORD:'test-password-only',DB_NAME:'navigator_test',ADMIN_EMAIL:'owner@test.local',APP_ORIGIN:'http://127.0.0.1:3100',IMPORT_LEGACY_DATA:'false',UPLOAD_DIR:fileURLToPath(new URL('../.data/test-uploads',import.meta.url))};
let app=await createApplication({env});
const email=env.ADMIN_EMAIL,password='Test-only-password-2745';await transaction(app.pool,c=>c.query('DELETE FROM login_limits'));
await transaction(app.pool,async c=>{await c.query('UPDATE members SET user_id=COALESCE(user_id,$1) WHERE email=$2',[randomUUID(),email]);await c.query('INSERT INTO accounts(email,password_hash) VALUES($1,$2) ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash)',[email,await hashPassword(password)]);await c.query('UPDATE account_password_state SET must_change_password=0 WHERE email=$1',[email]);});
const call=async(path,method='GET',body,cookie='',extra={})=>{
 const request=new Request(env.APP_ORIGIN+path,{method,headers:{Origin:env.APP_ORIGIN,'Content-Type':'application/json',...(cookie?{cookie}:{}),...extra},body:method==='GET'?undefined:JSON.stringify(body)});
 const res=await app.handle(request,'test-client');let value;try{value=await res.clone().json()}catch{value=null}return {status:res.status,body:value,response:res};
};
try {
 assert.equal((await call('/api/workspace','GET',undefined,'',{'oai-authenticated-user-id':'forged','oai-authenticated-user-email':email})).status,401);
 const login=await call('/api/auth/login','POST',{email,password});assert.equal(login.status,200,JSON.stringify(login.body));
 const cookie=login.response.headers.get('Set-Cookie').split(';')[0];
 assert.equal((await call('/api/me','GET',undefined,cookie)).status,200);
 const created=await call('/api/projects','POST',{name:'MySQL事务验证',type:'大数据'},cookie);assert.equal(created.status,201,JSON.stringify(created.body));
 const id=created.body.id;
 const results=await Promise.all(['甲','乙'].map(next=>call('/api/projects/'+id,'PATCH',{_version:1,next},cookie)));
 assert.deepEqual(results.map(x=>x.status).sort(),[200,409]);
 await transaction(app.pool,c=>c.query("CREATE TRIGGER fail_test_audit BEFORE INSERT ON audit FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test audit failure'"));
 try { assert.equal((await call('/api/projects/'+id,'PATCH',{_version:2,next:'must roll back'},cookie)).status,500); }
 finally { await transaction(app.pool,c=>c.query('DROP TRIGGER fail_test_audit')); }
 const afterRollback=(await call('/api/workspace','GET',undefined,cookie)).body.projects.find(p=>p.id===id);assert.equal(afterRollback._version,2);assert.notEqual(afterRollback.next,'must roll back');
 const audits=await transaction(app.pool,c=>c.query("SELECT * FROM audit WHERE entity=$1 AND action='更新项目'",[id]));assert.equal(audits.rows.length,1,'only committed edit has an audit');
 const ws=(await call('/api/workspace','GET',undefined,cookie)).body;
 const current=ws.projects.find(p=>p.id===id);
 assert.equal((await call('/api/projects/'+id,'PATCH',{_version:current._version,next:'跨站'},cookie,{Origin:'https://untrusted.local'})).status,403);
 assert.equal((await call('/api/projects/'+id,'PATCH',{_version:current._version,stage:99},cookie)).status,400);
 assert.equal((await call('/api/projects/'+id+'/archive','POST',{_version:current._version},cookie)).status,200);
 assert.equal((await call('/api/projects/'+id,'PATCH',{_version:current._version+1,next:'bad'},cookie)).status,409);
 assert.equal((await call('/api/projects/'+id+'/restore','POST',{_version:current._version+1},cookie)).status,200);
 const member='member-'+Date.now()+'@test.local';
 assert.equal((await call('/api/admin/member','POST',{email:member,roleId:'sa'},cookie)).status,200);
 const initial=await call('/api/auth/login','POST',{email:member,password:INITIAL_PASSWORD});assert.equal(initial.body.mustChangePassword,true);
 const initialCookie=initial.response.headers.get('Set-Cookie').split(';')[0];
 assert.equal((await call('/api/workspace','GET',undefined,initialCookie)).status,403);
 assert.equal((await call('/api/auth/password','POST',{currentPassword:INITIAL_PASSWORD,password},initialCookie)).status,200);
 const memberLogin=await call('/api/auth/login','POST',{email:member,password});assert.equal(memberLogin.status,200);
 const memberCookie=memberLogin.response.headers.get('Set-Cookie').split(';')[0];
 assert.equal((await call('/api/admin/member','POST',{email:member,roleId:'sa',enabled:false,_version:1},cookie)).status,200);
 assert.equal((await call('/api/me','GET',undefined,memberCookie)).status,401);
 const file=await call('/api/files','POST',{name:'一致性测试.txt',type:'大数据',base64:Buffer.from('test file').toString('base64')},cookie);assert.equal(file.status,201,JSON.stringify(file.body));
 const downloaded=await call('/api/files/'+file.body.id,'GET',undefined,cookie);assert.equal(await downloaded.response.text(),'test file');
 await app.pool.end();app=await createApplication({env});
 assert.equal((await call('/api/me','GET',undefined,cookie)).status,200,'session survives a new application instance');
 assert.equal((await call('/api/workspace','GET',undefined,cookie)).body.projects.find(p=>p.id===id)._version,4,'committed record survives application restart');
 assert.equal(await (await call('/api/files/'+file.body.id,'GET',undefined,cookie)).response.text(),'test file','uploaded content survives application restart');
 assert.equal((await call('/api/auth/password','POST',{currentPassword:password,password:'New-test-password-2745'},cookie)).status,200);
 assert.equal((await call('/api/me','GET',undefined,cookie)).status,401);
 for(let i=0;i<10;i++) await call('/api/auth/login','POST',{email:'unknown@test.local',password:'wrong'});
 assert.equal((await call('/api/auth/login','POST',{email:'unknown@test.local',password:'wrong'})).status,429,'failed attempts must persist');
 console.log('PASS: MySQL 8 migrations; trusted login boundary; concurrent optimistic locking; atomic edit/audit; CSRF; input validation; archive/restore; mandatory initial password change; session revocation; durable file upload; password change; persistent rate limiting');
} finally { await app.pool.end(); }
