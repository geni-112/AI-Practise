import assert from 'node:assert/strict';
import {createApplication} from '../server/index.mjs';
import {transaction} from '../server/database.mjs';
import {hashPassword} from '../server/auth.mjs';
import {randomUUID} from 'node:crypto';
import {INITIAL_PASSWORD} from './test-credentials.mjs';
const env={INITIAL_ACCOUNT_PASSWORD:INITIAL_PASSWORD,DB_HOST:'127.0.0.1',DB_PORT:'13306',DB_USER:'navigator_test',DB_PASSWORD:'test-password-only',DB_NAME:'navigator_i18n_test',ADMIN_EMAIL:'i18n@test.local',APP_ORIGIN:'http://127.0.0.1:3101'};
assert.equal(env.DB_HOST,'127.0.0.1');assert.equal(env.DB_NAME,'navigator_i18n_test');
const app=await createApplication({mfaRequired:false,env}),password='Dictionary-test-password';
await transaction(app.pool,async c=>{
 await c.query("DELETE FROM records WHERE kind='dictionary'");await c.query('DELETE FROM login_limits');
 await c.query('UPDATE members SET user_id=COALESCE(user_id,$1) WHERE email=$2',[randomUUID(),env.ADMIN_EMAIL]);
 await c.query('INSERT INTO accounts(email,password_hash) VALUES($1,$2) ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash)',[env.ADMIN_EMAIL,await hashPassword(password)]);await c.query('UPDATE account_password_state SET must_change_password=0 WHERE email=$1',[env.ADMIN_EMAIL]);
});
async function call(path,method='GET',body,cookie=''){
 const response=await app.handle(new Request(env.APP_ORIGIN+'/api/'+path,{method,headers:{Origin:env.APP_ORIGIN,'Content-Type':'application/json',Cookie:cookie},body:method==='GET'?undefined:JSON.stringify(body)}),'dictionary-test');
 return {status:response.status,body:await response.json(),response};
}
try{
 const login=await call('auth/login','POST',{email:env.ADMIN_EMAIL,password});assert.equal(login.status,200);const cookie=login.response.headers.get('Set-Cookie').split(';')[0];
 const list=()=>call('dictionaries','GET',undefined,cookie).then(r=>r.body);
 const save=dict=>call('admin/dictionaries','POST',dict,cookie);
 const initial=await list();assert.equal(initial.length,13);
 const vendor=initial.find(d=>d.field==='vendor');vendor.allowCustom=false;vendor.items=[{value:'',zh:'测试厂家',en:'Test vendor',enabled:true}];
 const saved=await save(vendor);assert.equal(saved.status,200,JSON.stringify(saved.body));const vendorId=saved.body.items[0].value;
 const created=await call('projects','POST',{name:'Dictionary round trip',type:'数据库',saName:'Test SA',vendor:vendorId,scenario:'Test use case',notes:'Technical notes',stage:3,planYear:2026,eiPlan:1.5,actuals:[{month:'2026-11',kind:'EI',amount:0.1}],milestones:{'POC 资源':'已完成'}},cookie);
 assert.equal(created.status,201,JSON.stringify(created.body));for(const [key,value]of Object.entries({saName:'Test SA',vendor:vendorId,notes:'Technical notes',eiPlan:1.5,stage:3}))assert.equal(created.body[key],value);
 assert.equal(created.body.milestones['POC 资源'],'已完成');assert.equal(created.body.actuals[0].amount,0.1);
 assert.equal((await call('projects','POST',{name:'Invalid option',vendor:'Not in dictionary'},cookie)).status,400);
 const stage=(await list()).find(d=>d.field==='stage');stage.items.find(i=>i.value==='3').zh='准备验证';assert.equal((await save(stage)).status,200);
 const report=await call('reports/preview','POST',{period:'2026-11'},cookie);assert(report.body.stats.poc>=1,'renamed stage keeps POC meaning');
 const renamed={...saved.body,items:[{...saved.body.items[0],zh:'测试厂家更新',en:'Updated vendor'}]};
 const parallel=await Promise.all([save(renamed),save({...renamed,items:[{...renamed.items[0],en:'Other name'}]})]);assert.deepEqual(parallel.map(r=>r.status).sort(),[200,409]);
 const latest=(await list()).find(d=>d.field==='vendor');latest.allowCustom=true;latest.items[0].enabled=false;assert.equal((await save(latest)).status,200);
 const patch=await call('projects/'+created.body.id,'PATCH',{_version:1,next:'Keep disabled existing choice'},cookie);assert.equal(patch.status,200);assert.equal(patch.body.vendor,vendorId);
 assert.equal((await call('projects','POST',{name:'Cannot reuse disabled',vendor:vendorId},cookie)).status,400);
 const bd='dictionary-bd@test.local';await call('admin/member','POST',{email:bd,roleId:'bd'},cookie);
 await transaction(app.pool,async c=>{await c.query('UPDATE members SET user_id=COALESCE(user_id,$1) WHERE email=$2',[randomUUID(),bd]);await c.query('INSERT INTO accounts(email,password_hash) VALUES($1,$2) ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash)',[bd,await hashPassword(password)]);await c.query('UPDATE account_password_state SET must_change_password=0 WHERE email=$1',[bd])});
 const bdLogin=await call('auth/login','POST',{email:bd,password});const bdCookie=bdLogin.response.headers.get('Set-Cookie').split(';')[0];
 assert.equal((await call('admin/dictionaries','POST',latest,bdCookie)).status,403);
 assert.equal((await call('projects','POST',{name:'BD initial finance',eiPlan:1.2,planYear:2026},bdCookie)).status,201);
 assert.equal((await call('projects','POST',{name:'Forbidden technical field',saName:'Other person'},bdCookie)).status,403);
 assert.equal((await call('projects','POST',{name:'Forbidden technical milestone',milestones:{'POC 资源':'已完成'}},bdCookie)).status,403);
 assert.equal((await save({...latest,_version:latest._version+1,items:[]})).status,400,'persisted choices cannot be deleted');
 console.log('PASS: persistent dictionaries, new project technical/finance fields, stable workflow semantics, disabled choice preservation, permission isolation and optimistic concurrency');
}finally{await app.pool.end()}
