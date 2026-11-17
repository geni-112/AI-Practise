import assert from 'node:assert/strict';
import {randomBytes,randomUUID} from 'node:crypto';
import {createApplication} from '../server/index.mjs';
import {transaction} from '../server/database.mjs';
import {visionProbe} from '../server/architecture-model.mjs';
import {fixture} from './architecture-fixture.mjs';

// Run only in a newly provisioned isolated test schema, with a user restricted to it.
const env={...process.env,APP_ORIGIN:'https://qa.example.invalid',ADMIN_EMAIL:'admin@example.invalid',INITIAL_ACCOUNT_PASSWORD_FILE:'',INITIAL_ACCOUNT_PASSWORD:randomBytes(24).toString('hex')};
assert.match(env.DB_NAME||'',/^ppl_qa_[a-f0-9]{12}$/);assert.equal(env.DB_USER,env.DB_NAME);
const firstPassword=env.INITIAL_ACCOUNT_PASSWORD,probe=visionProbe();
const mockModel=async(_url,options)=>{
 const req=JSON.parse(options.body);
 return Response.json({choices:[{message:{content:JSON.stringify(req.messages.length===1?{code:probe.code}:fixture)},finish_reason:'stop'}]});
};
const start=()=>createApplication({env,maasFetch:mockModel,visionProbe:()=>probe});
let app=await start();
async function request(path,cookie='',body,method=body===undefined?'GET':'POST'){
 return app.handle(new Request(env.APP_ORIGIN+'/api/'+path,{method,headers:{Origin:env.APP_ORIGIN,'Content-Type':'application/json',cookie},body:body===undefined?undefined:JSON.stringify(body)}),'release-qa');
}
async function read(path,cookie,body,status=200,method){
 const res=await request(path,cookie,body,method);assert.equal(res.status,status,path+' status '+res.status);
 return res.json();
}
async function login(email,password=firstPassword,status=200){
 const res=await request('auth/login','',{email,password});assert.equal(res.status,status);
 return res.headers.get('set-cookie')?.split(';')[0]||'';
}
async function personalize(email){
 const old=await login(email);assert.equal((await request('workspace',old)).status,403);
 const password=randomBytes(20).toString('hex');
 await read('auth/password',old,{currentPassword:firstPassword,password});
 return {cookie:await login(email,password),password};
}
try{
 const admin=await personalize(env.ADMIN_EMAIL),bd='bd@example.invalid',sa='sa@example.invalid',other='other@example.invalid',pending='pending@example.invalid';
 for(const [email,roleId] of [[bd,'bd'],[sa,'sa'],[other,'sa'],[pending,'viewer']])await read('admin/member',admin.cookie,{email,roleId});
 const owner=(await personalize(bd)).cookie,assigned=(await personalize(sa)).cookie,unassigned=(await personalize(other)).cookie;
 const waiting=await login(pending);
 const project=await read('projects',owner,{name:'Fictional project',saId:sa,stage:4},201);
 assert.equal(project.saName,sa);
 const cfg=await read('practices/config',admin.cookie);
 await read('practices/config',admin.cookie,{_version:cfg._version,inputMode:'vision',endpoint:'https://api.modelarts-maas.com/v1',model:'synthetic',region:'test',apiKey:randomUUID(),dailyLimit:100,maxTokens:8192,enabled:true});
 await read('practices/test',admin.cookie,{});
 const body={requestKey:randomUUID(),title:'Private fixture customer title',businessType:'大数据',targetRegion:'Test',language:'en',context:'Private fixture context',name:'fixture.png',mime:'image/png',base64:probe.image.toString('base64')};
 const item=await read('practices',owner,{...body,projectId:project.id},202);
 assert.equal(await app.practices.runNext(),true);
 const path='practices/'+item.id,record=await read(path,assigned);
 assert.equal(record.status,'succeeded');assert.equal(record.project_id,project.id);
 for(const suffix of ['','/image','/drawing?lang=en','/drawing/preview?lang=en','/failures']){
  assert.equal((await request(path+suffix,assigned)).status,200);
  assert.equal((await request(path+suffix,unassigned)).status,404);
 }
 assert.equal((await read('practices',assigned)).total,1);assert.equal((await read('practices',unassigned)).total,0);
 const safe={_version:record.version,publish:true,reviewed:true,title:'Reviewed lakehouse pattern',summary:'Object storage and SQL',mappings:record.referenceCandidates};
 assert.equal((await request(path+'/reference',owner,safe)).status,403);
 await read(path+'/reference',admin.cookie,safe);
 const ref=await read('practices/references/'+item.id,unassigned);
 assert.equal(ref.title,safe.title);assert.deepEqual(Object.keys(ref).sort(),['id','title','summary','business_type','reviewed_at','mappings'].sort());
 assert(!JSON.stringify(await read('practices/references',unassigned)).includes(body.title));
 assert.equal((await read('practices/references?q=Private',unassigned)).total,0);
 assert.equal((await read('practices/references?q=lakehouse',unassigned)).total,1);
 await read('projects/'+project.id,owner,{_version:project._version,saId:other},200,'PATCH');
 assert.equal((await read('practices',assigned)).total,0);assert.equal((await request(path+'/image',assigned)).status,404);
 assert.equal((await request(path+'/image',unassigned)).status,200);
 const own=await read('practices',owner,{...body,requestKey:randomUUID()},202);
 assert.equal((await request('practices/'+own.id+'/image',unassigned)).status,404);
 assert.equal((await request('practices/'+own.id+'/image',owner)).status,200);
 await app.practices.runNext();
 const current=await read('practices/'+own.id,owner);
 await read('practices/'+own.id+'/project',owner,{_version:current.version,projectId:project.id});
 assert.equal((await request('practices/'+own.id+'/image',unassigned)).status,200);
 // A previously reviewed case needs an explicit public title and a redaction review.
 await transaction(app.pool,c=>c.query('DELETE FROM architecture_case_publications WHERE analysis_id=?',[item.id]));
 assert.equal((await read('practices/references',unassigned)).total,0);
 assert.equal((await request('practices/references/'+item.id,unassigned)).status,404);
 const originalAdminHash=(await transaction(app.pool,c=>c.query('SELECT password_hash FROM accounts WHERE email=?',[env.ADMIN_EMAIL]))).rows[0].password_hash;
 await app.pool.end();env.INITIAL_ACCOUNT_PASSWORD=randomBytes(24).toString('hex');app=await start();
 assert.equal((await request('workspace',waiting)).status,401);await login(pending,firstPassword,401);
 const rotated=await login(pending,env.INITIAL_ACCOUNT_PASSWORD);
 assert.equal((await read('auth/status',rotated)).mustChangePassword,true);
 assert.equal((await request('workspace',admin.cookie)).status,200);
 const refreshed=(await transaction(app.pool,c=>c.query('SELECT password_hash FROM accounts WHERE email=?',[env.ADMIN_EMAIL]))).rows[0].password_hash;
 assert.equal(refreshed,originalAdminHash);
 console.log('PASS: MySQL migrations, account rotation, first sign-in, BD reassignment, private diagrams and drawings, redacted references and legacy review');
}finally{await app.practices.stop();await app.pool.end()}
