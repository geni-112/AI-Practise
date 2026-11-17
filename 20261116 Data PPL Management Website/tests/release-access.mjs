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
let failAnalysis=false;
const mockModel=async(_url,options)=>{
 const req=JSON.parse(options.body);
 const translating=req.messages[0]?.content?.startsWith?.('Translate every supplied');
 const value=translating?Object.fromEntries(Object.keys(JSON.parse(req.messages[1].content)).map(key=>[key,'测试译文'])):req.messages.length===1?{code:probe.code}:failAnalysis?{}:fixture;
 return Response.json({choices:[{message:{content:JSON.stringify(value)},finish_reason:'stop'}]});
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
 const initialNav=await read('navigation',admin.cookie);
 const menuOrder=[...initialNav.order].reverse();
 const writes=await Promise.all([request('admin/navigation',admin.cookie,{order:menuOrder,_version:initialNav._version}),request('admin/navigation',admin.cookie,{order:menuOrder,_version:initialNav._version})]);
 assert.deepEqual(writes.map(response=>response.status).sort(),[200,409]);
 const ownMenu=(await read('workspace',owner)).navigation;
 assert.deepEqual(ownMenu.order,menuOrder.filter(id=>['practices','home','projects','poc','library'].includes(id)));
 assert.equal((await request('admin/navigation',owner,{order:menuOrder,_version:ownMenu._version})).status,403);
 const labels={home:{zh:'测试工作台',en:'QA overview'},maas:{en:'QA models'}};
 const renamed=await read('admin/navigation',admin.cookie,{order:menuOrder,labels,_version:1});
 assert.deepEqual(renamed,{order:menuOrder,labels,_version:2});
 assert.deepEqual((await read('workspace',owner)).navigation.labels,{home:labels.home});
 assert.equal((await request('admin/navigation',owner,{order:menuOrder,labels:{},_version:2})).status,403);
 assert.equal((await request('admin/navigation',admin.cookie,{order:menuOrder,labels:{},_version:1})).status,409);
 const orderOnly=await read('admin/navigation',admin.cookie,{order:menuOrder,_version:2});
 assert.deepEqual(orderOnly.labels,labels);
 const waiting=await login(pending);
 const normalProject=await read('projects',owner,{name:'Project without diagram',saId:sa,stage:4},201);
 assert.equal(normalProject.saName,sa);
 const diagram={requestKey:randomUUID(),language:'en',name:'architecture.png',mime:'image/png',base64:probe.image.toString('base64')};
 const submit={name:'Project with a technical diagram',saId:sa,stage:4,architectureDiagram:diagram};
 const bad=await request('projects',owner,{...submit,architectureDiagram:{...diagram,base64:'not an image'}});
 assert.equal(bad.status,400);
 const receipts=await Promise.all([request('projects',owner,submit),request('projects',owner,submit)]);
 assert.deepEqual(receipts.map(r=>r.status).sort(),[200,201]);
 const [first,second]=await Promise.all(receipts.map(r=>r.json()));
 assert.deepEqual(first,second);assert.deepEqual(Object.keys(first).sort(),['architectureSubmitted','id']);assert(first.architectureSubmitted);
 assert.equal((await request('projects',owner,{...submit,name:'Changed input'})).status,409);
 const workspace=await read('workspace',owner),project=workspace.projects.find(p=>p.id===first.id);
 assert.equal(workspace.projects.length,2);assert(!JSON.stringify(workspace).includes(diagram.name));assert(!('architectureDiagram' in project));
 const list='practices?archived=true&projectId='+first.id;
 const queued=await read(list,assigned);assert.equal(queued.total,1);assert.equal(queued.items[0].status,'queued');
 const id=queued.items[0].id,path='practices/'+id;
 assert.equal((await read(list,owner)).total,1);assert.equal((await read(list,unassigned)).total,0);
 assert.deepEqual(Buffer.from(await (await request(path+'/image',owner)).arrayBuffer()),probe.image);
 assert.equal(await app.practices.runNext(),false); // Configuration can be enabled after the project is submitted.
 const cfg=await read('practices/config',admin.cookie);
 await read('practices/config',admin.cookie,{_version:cfg._version,inputMode:'vision',endpoint:'https://api.modelarts-maas.com/v1',model:'synthetic',region:'test',apiKey:randomUUID(),dailyLimit:100,maxTokens:8192,enabled:true});
 await read('practices/test',admin.cookie,{});
 failAnalysis=true;assert.equal(await app.practices.runNext(),true);failAnalysis=false;
 const failure=await read(path,assigned);assert.equal(failure.status,'failed');assert.equal(failure.archived_at,null);
 assert((await read(path+'/failures',owner)).items.length);assert.equal((await read(path,owner)).canMaintain,false);
 assert.equal((await request(path+'/retry',owner,{_version:failure.version})).status,403);await read(path+'/retry',assigned,{_version:failure.version});
 assert(await app.practices.runNext());const record=await read(path,assigned);
 assert.equal(record.status,'succeeded');assert.equal(record.project_id,project.id);assert(record.projectSubmission&&record.archived_at&&record.result);
 for(let n=0;n<8;n++){if(!await app.practices.runNextTranslation())break}
 assert((await read(path+'?lang=zh',assigned)).result);
 assert.equal((await read('practices?projectId='+project.id,owner)).total,0);
 assert.equal((await read(list,assigned)).items[0].projectSubmission,true);
 assert.equal((await request(path+'/drawing?lang=en',owner,{version:0})).status,403);
 const reviewerRole=await read('admin/role',admin.cookie,{name:'QA reviewer',permissions:['practice.read','practice.analyze','practice.manage','project.read.all','audit.view']});
 const reviewerEmail='reviewer@example.invalid';await read('admin/member',admin.cookie,{email:reviewerEmail,roleId:reviewerRole.id});
 const reviewer=(await personalize(reviewerEmail)).cookie;
 const suffixes=['','?lang=zh','/image','/drawing?lang=en','/drawing/preview?lang=zh','/drawing?lang=en&download=1','/failures'];
 for(const suffix of suffixes){
  for(const cookie of [owner,assigned,admin.cookie])assert.equal((await request(path+suffix,cookie)).status,200,suffix);
  for(const cookie of [unassigned,reviewer])assert.equal((await request(path+suffix,cookie)).status,404,suffix);
 }
 assert.equal((await read(list,reviewer)).total,0);assert(!(await read('audit',reviewer)).some(row=>row.entity===id));
 assert.equal((await request(path+'/reference',admin.cookie,{_version:record.version,publish:true})).status,403);
 assert.equal((await request('practices/references/'+id,unassigned)).status,404);
 assert.equal((await read('practices/references',unassigned)).total,0);

 // Manually reviewed standalone cases still work. Linking one makes it private at once.
 const standalone=await read('practices',owner,{...diagram,requestKey:randomUUID(),title:'Standalone fixture',businessType:'大数据',targetRegion:'Test'},202);
 assert.equal((await request('practices/'+standalone.id+'/image',unassigned)).status,404);
 await app.practices.runNext();
 const single='practices/'+standalone.id,current=await read(single,owner);
 const safe={_version:current.version,publish:true,reviewed:true,title:'Reviewed pattern',summary:'Object storage and SQL',mappings:current.referenceCandidates};
 await read(single+'/reference',admin.cookie,safe);
 const published=await read('practices/references/'+standalone.id,unassigned);
 assert.equal(published.title,safe.title);assert.deepEqual(Object.keys(published).sort(),['id','title','summary','business_type','reviewed_at','mappings'].sort());
 await read(single+'/project',owner,{_version:(await read(single,owner)).version,projectId:normalProject.id});
 assert.equal((await read('practices/references',unassigned)).total,0);
 assert.equal((await request('practices/references/'+standalone.id,unassigned)).status,404);
 assert.equal((await request(single+'/image',reviewer)).status,404);

 const reassigned=await read('projects/'+project.id,owner,{_version:project._version,saId:other},200,'PATCH');
 assert.equal((await read(list,assigned)).total,0);assert.equal((await request(path+'/image',assigned)).status,404);
 assert.equal((await request(path+'/image',unassigned)).status,200);assert.equal((await request(path+'/image',owner)).status,200);
 // A designated BD without general Best practices access can open this project, while the original uploader loses access.
 const nextBD='next-bd@example.invalid',custom=await read('admin/role',admin.cookie,{name:'Project reader',permissions:['project.read.own']});
 await read('admin/member',admin.cookie,{email:nextBD,roleId:custom.id});const newOwner=(await personalize(nextBD)).cookie;
 await read('projects/'+project.id,admin.cookie,{_version:reassigned._version,bdId:nextBD},200,'PATCH');
 assert.equal((await request('practices',newOwner)).status,403);assert.equal((await read(list,newOwner)).total,1);
 assert.equal((await request(path+'/image',newOwner)).status,200);
 assert.equal((await request(single+'/image',newOwner)).status,404);
 assert.equal((await read(list,owner)).total,0);
 for(const suffix of suffixes)assert.equal((await request(path+suffix,owner)).status,404,suffix);
 assert.deepEqual(await read('projects',owner,submit),first);
 // A full analysis quota rolls back the new project, its history and its original image.
 await transaction(app.pool,async c=>{
  for(let n=0;n<10;n++)await c.query("INSERT INTO architecture_usage(id,owner_email,purpose) VALUES(?,?,'analysis')",[randomUUID(),bd]);
 });
 const count=async()=>transaction(app.pool,async c=>(await c.query("SELECT (SELECT COUNT(*) FROM records WHERE kind='project') AS projects,(SELECT COUNT(*) FROM project_diagram_submissions) AS images,(SELECT COUNT(*) FROM architecture_analyses) AS analyses,(SELECT COUNT(*) FROM project_report_states) AS history")).rows[0]);
 const before=await count();
 assert.equal((await request('projects',owner,{...submit,architectureDiagram:{...diagram,requestKey:randomUUID()}})).status,400);
 assert.deepEqual(await count(),before);
 const originalAdminHash=(await transaction(app.pool,c=>c.query('SELECT password_hash FROM accounts WHERE email=?',[env.ADMIN_EMAIL]))).rows[0].password_hash;
 await app.pool.end();env.INITIAL_ACCOUNT_PASSWORD=randomBytes(24).toString('hex');app=await start();
 assert.equal((await request('workspace',waiting)).status,401);await login(pending,firstPassword,401);
 const rotated=await login(pending,env.INITIAL_ACCOUNT_PASSWORD);
 assert.equal((await read('auth/status',rotated)).mustChangePassword,true);
 assert.equal((await request('workspace',admin.cookie)).status,200);
 const refreshed=(await transaction(app.pool,c=>c.query('SELECT password_hash FROM accounts WHERE email=?',[env.ADMIN_EMAIL]))).rows[0].password_hash;
 assert.equal(refreshed,originalAdminHash);
 assert.deepEqual((await read('workspace',admin.cookie)).navigation,{order:menuOrder,labels,_version:3});
 assert.equal((await read(list,unassigned)).total,1);assert.equal((await request(path+'/image',owner)).status,404);
 assert.deepEqual(Buffer.from(await (await request(path+'/image',newOwner)).arrayBuffer()),probe.image);
 console.log('PASS: atomic project upload, duplicate requests, worker retry, bilingual auto-archive, current BD/SA/admin-only access, reassignment and restart');
 console.log('PASS: RDS menu order, concurrent saves, role filtering and persistence after restart');
 console.log('PASS: MySQL migrations, account rotation, first sign-in, BD reassignment, private diagrams and drawings, redacted references and legacy review');
}finally{await app.practices.stop();await app.pool.end()}
