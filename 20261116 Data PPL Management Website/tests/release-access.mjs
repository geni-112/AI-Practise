import assert from 'node:assert/strict';
import {randomBytes,randomUUID} from 'node:crypto';
import {createApplication} from '../server/index.mjs';
import {transaction} from '../server/database.mjs';
import {visionProbe} from '../server/architecture-model.mjs';
import {fixture} from './architecture-fixture.mjs';
import {deleteMember} from '../server/members.mjs';

// Run only in a newly provisioned isolated test schema, with a user restricted to it.
const env={...process.env,APP_ORIGIN:'https://qa.example.invalid',ADMIN_EMAIL:'admin@example.invalid',INITIAL_ACCOUNT_PASSWORD_FILE:'',INITIAL_ACCOUNT_PASSWORD:randomBytes(24).toString('hex')};
assert.match(env.DB_NAME||'',/^ppl_qa_[a-f0-9]{12}$/);assert.equal(env.DB_USER,env.DB_NAME);
const firstPassword=env.INITIAL_ACCOUNT_PASSWORD,probe=visionProbe();
let failAnalysis=false,failContent=false,contentCalls=0;
const mockModel=async(_url,options)=>{
 const req=JSON.parse(options.body);
 const contentTranslation=req.messages[0]?.content?.startsWith?.('Translate each workspace entry');
 if(contentTranslation){
  contentCalls++;const entries=JSON.parse(req.messages[1].content);
  return Response.json({choices:[{message:{content:JSON.stringify(Object.fromEntries(Object.keys(entries).map(key=>[key,failContent?'不完整译文':'Translated workspace entry '+key])))},finish_reason:'stop'}]});
 }
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
async function personalize(email,displayName='Team member'){
 const old=await login(email);assert.equal((await request('workspace',old)).status,403);
 const password=randomBytes(20).toString('hex');
 await read('auth/password',old,{currentPassword:firstPassword,password,displayName});
 return {cookie:await login(email,password),password};
}
try{
 for(const asset of ['brand.svg','ui-icons.svg']){
  const res=await app.handle(new Request(env.APP_ORIGIN+'/'+asset),'release-qa');
  assert.equal(res.status,200);assert.match(res.headers.get('content-type'),/image\/svg\+xml/);
  assert.match(await res.text(),/<svg\b/);
 }
 const admin=await personalize(env.ADMIN_EMAIL),bd='bd@example.invalid',sa='sa@example.invalid',other='other@example.invalid',pending='pending@example.invalid';
 for(const [email,roleId] of [[bd,'bd'],[sa,'sa'],[other,'sa'],[pending,'viewer']])await read('admin/member',admin.cookie,{email,roleId});
 const owner=(await personalize(bd,'业务负责人')).cookie,assigned=(await personalize(sa,'架构师甲')).cookie,unassigned=(await personalize(other)).cookie;

 const ownProfile=await read('auth/profile',owner),oldRole=(await read('me',owner)).user.roleId;
 for(const displayName of ['', ' ', 'x'.repeat(81), 'two\nlines', 42])await read('auth/profile',owner,{displayName,_version:ownProfile._version},400);
 const profileWrites=await Promise.all([
  request('auth/profile',owner,{displayName:'业务负责人乙',_version:ownProfile._version,email:sa,roleId:'admin'}),
  request('auth/profile',owner,{displayName:'业务负责人乙',_version:ownProfile._version})
 ]);
 assert.deepEqual(profileWrites.map(r=>r.status).sort(),[200,409]);
 assert.equal((await read('me',owner)).user.roleId,oldRole);
 assert.equal((await read('auth/profile',assigned)).displayName,'架构师甲');
 assert.equal((await read('auth/profile',owner)).displayName,'业务负责人乙');
 const profileMember=(await read('admin',admin.cookie)).members.find(m=>m.email===bd);
 await read('admin/member',admin.cookie,{email:bd,roleId:'bd',displayName:'Stale administrator edit',_version:ownProfile._version},409);
 assert.equal(profileMember.display_name,'业务负责人乙');
 const stillWaiting=await login(pending);
 await read('auth/profile',stillWaiting,{displayName:'Bypass',_version:1},403);
 await read('auth/password',stillWaiting,{currentPassword:firstPassword,password:randomBytes(20).toString('hex'),displayName:' '},400);
 assert.equal((await read('auth/status',stillWaiting)).mustChangePassword,true);
 for(const p of ['/settings','/settings?section=ai','/settings/maas']){
  assert.equal((await app.handle(new Request(env.APP_ORIGIN+p,{headers:{cookie:admin.cookie}}))).status,200);
  assert.equal((await app.handle(new Request(env.APP_ORIGIN+p,{headers:{cookie:owner}}))).status,403);
  const visitor=await app.handle(new Request(env.APP_ORIGIN+p));
  assert.equal(visitor.status,303);assert.match(visitor.headers.get('Location'),/next=(settings|maas)/);
 }
 for(const route of ['practices/config','admin/dictionaries'])await read(route,owner,route==='admin/dictionaries'?{}:undefined,403);

 console.log('PASS: validated display names, atomic first-sign-in setup, profile conflicts, self-only updates and admin-only settings');

 const disposableRole=await read('admin/role',admin.cookie,{name:'Delete role QA',permissions:['resource.read']});
 assert.equal((await request('admin/role',owner,{id:disposableRole.id,_version:1},'DELETE')).status,403);
 for(const id of ['admin','bd','sa','viewer']){
  const entry=(await read('admin',admin.cookie)).roles.find(r=>r.id===id);
  await read('admin/role',admin.cookie,{id,_version:entry._version},400,'DELETE');
 }
 await read('admin/role',admin.cookie,{id:disposableRole.id,_version:0},409,'DELETE');
 const roleMember='role-delete-test@example.invalid';
 await read('admin/member',admin.cookie,{email:roleMember,roleId:disposableRole.id,enabled:false});
 assert.equal((await read('admin',admin.cookie)).roles.find(r=>r.id===disposableRole.id).memberCount,1);
 await read('admin/role',admin.cookie,{id:disposableRole.id,_version:1},400,'DELETE');
 await read('admin/member',admin.cookie,{email:roleMember,roleId:'sa',enabled:false,_version:1});
 await read('admin/role',admin.cookie,{id:disposableRole.id,_version:1},200,'DELETE');
 await read('admin/role',admin.cookie,{...disposableRole,name:'Stale editor',_version:1},404);
 assert((await read('audit',admin.cookie)).some(entry=>entry.action==='删除角色：'+disposableRole.name&&entry.entity===disposableRole.id));
 const secondAdminEmail='role-test-admin@example.invalid';
 await read('admin/member',admin.cookie,{email:secondAdminEmail,roleId:'admin'});
 const secondAdmin=(await personalize(secondAdminEmail)).cookie;
 const raceRole=await read('admin/role',admin.cookie,{name:'Concurrent role QA',permissions:[]});
 const memberVersion=(await read('admin',admin.cookie)).members.find(m=>m.email===roleMember).version;
 const roleRace=await Promise.all([
  request('admin/member',secondAdmin,{email:roleMember,roleId:raceRole.id,enabled:false,_version:memberVersion}),
  request('admin/role',admin.cookie,{id:raceRole.id,_version:1},'DELETE')
 ]);
 const statuses=roleRace.map(r=>r.status);
 assert(statuses.filter(s=>s===200).length===1&&statuses.every(s=>[200,400,404,409].includes(s)),statuses.join(','));
 const roleState=await read('admin',admin.cookie);
 const linked=roleState.members.find(m=>m.email===roleMember),remainingRole=roleState.roles.find(r=>r.id===raceRole.id);
 if(remainingRole){
  assert.equal(linked.role_id,raceRole.id);
  await read('admin/member',admin.cookie,{email:roleMember,roleId:'sa',enabled:false,_version:linked.version});
  await read('admin/role',admin.cookie,{id:raceRole.id,_version:remainingRole._version},200,'DELETE');
 }else assert.notEqual(linked.role_id,raceRole.id);
 const orphanCount=await transaction(app.pool,async c=>(await c.query("SELECT COUNT(*) AS n FROM members m LEFT JOIN records r ON r.id=m.role_id AND r.kind='role' WHERE r.id IS NULL")).rows[0].n);
 assert.equal(Number(orphanCount),0);
 console.log('PASS: MySQL role deletion, disabled-member references, concurrent assignments, stale editors and audit');

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
 assert.equal(normalProject.saName,'架构师甲');
 assert.equal(normalProject.bdName,'业务负责人乙');
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
 assert.equal(record.target_region,'');assert.equal(record.status,'succeeded');assert.equal(record.project_id,project.id);assert(record.projectSubmission&&record.archived_at&&record.result);
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


 const translateBody={language:'en',texts:['中文项目','启动数据库验证']};
 await read('content-translations','',translateBody,401);
 await read('content-translations',waiting,translateBody,403);
 await read('content-translations',owner,{language:'zh',texts:['项目']},400);
 await read('content-translations',owner,{language:'en',texts:['中'.repeat(1201)]},400);
 let contentResponse=await read('content-translations',owner,translateBody);
 assert(contentResponse.entries.every(entry=>entry.status==='queued'));
 const callsBefore=contentCalls;assert(await app.practices.runNextContentTranslation());
 contentResponse=await read('content-translations',owner,translateBody);
 assert(contentResponse.entries.every(entry=>entry.status==='ready'&&!/\p{Script=Han}/u.test(entry.translation)));
 await read('content-translations',owner,translateBody);assert.equal(contentCalls,callsBefore+1);
 const privateCache=await read('content-translations',unassigned,translateBody);
 assert(privateCache.entries.every(entry=>entry.status==='queued')); // Same text never reads another account's cache.
 assert(await app.practices.runNextContentTranslation());
 const updatedContent=await read('content-translations',owner,{language:'en',texts:['更新后的数据库验证']});
 assert.equal(updatedContent.entries[0].status,'queued');assert(await app.practices.runNextContentTranslation());
 failContent=true;
 const failureText={language:'en',texts:['失败后重试翻译']};await read('content-translations',owner,failureText);
 for(let attempt=0;attempt<3;attempt++){
  await app.practices.runNextContentTranslation();
  await transaction(app.pool,c=>c.query("UPDATE content_translations SET available_at=NOW() WHERE source_text=?",[failureText.texts[0]]));
 }
 assert.equal((await read('content-translations',owner,failureText)).entries[0].status,'failed');
 failContent=false;await read('content-translations',owner,{...failureText,retry:true});assert(await app.practices.runNextContentTranslation());
 assert.equal((await read('content-translations',owner,failureText)).entries[0].status,'ready');
 assert.equal((await read('workspace',owner)).projects.find(p=>p.id===project.id).name,submit.name);
 console.log('PASS: account-scoped English translation, source retention, caching, invalidation, failure retry and authentication');

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

 const additionalSA=(await read('me',unassigned)).user.id,firstSA=(await read('me',assigned)).user.id;
 let team=await read('projects/'+project.id,owner,{_version:project._version,saIds:[firstSA,additionalSA]},200,'PATCH');
 assert.deepEqual(team.saIds,[firstSA,additionalSA]);
 for(const cookie of [assigned,unassigned]){
  assert((await read('workspace',cookie)).projects.some(p=>p.id===project.id));
  for(const suffix of suffixes)assert.equal((await request(path+suffix,cookie)).status,200,suffix);
  assert.equal((await read(path,cookie)).canMaintain,true);
 }
 for(const suffix of suffixes)assert.equal((await request(path+suffix,reviewer)).status,404,suffix);
 await read('projects/'+project.id,assigned,{_version:team._version,saIds:[firstSA]},403,'PATCH');
 await read('projects/'+project.id,owner,{_version:team._version,saIds:[firstSA,firstSA]},400,'PATCH');
 await read('projects/'+project.id,owner,{_version:team._version,saId:other},409,'PATCH');
 team=await read('projects/'+project.id,unassigned,{_version:team._version,notes:'Second SA technical update'},200,'PATCH');
 const reassigned=await read('projects/'+project.id,owner,{_version:team._version,saIds:[additionalSA]},200,'PATCH');
 console.log('PASS: multiple SA project and original-image access, technical edits, unrelated-role isolation and removal');
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

 const deletionRole=await read('admin/role',admin.cookie,{name:'Member deletion QA',permissions:[...new Set([
  ...(await read('admin',admin.cookie)).roles.find(r=>r.id==='bd').permissions,
  'report.view','report.export','report.generate','report.archive','practice.read','practice.analyze'
 ])]});
 const removedEmail='member-deletion@example.invalid';
 await read('admin/member',admin.cookie,{email:removedEmail,roleId:deletionRole.id,displayName:'Removal QA'});
 const removedLogin=await personalize(removedEmail,'Removal QA');
 const removedDevice=await login(removedEmail,removedLogin.password);
 const removedUser=(await read('me',removedLogin.cookie)).user;
 const assignedProject=await read('projects',removedLogin.cookie,{name:'Member deletion project',stage:3},201);
 const sharedProject=await read('projects',admin.cookie,{name:'Legacy member assignment',bdId:removedUser.id,saId:removedUser.id},201);
 const retainedTeam=await read('projects',admin.cookie,{name:'Retain other SA after member deletion',saIds:[removedUser.id,sa]},201);
 await read('content-translations',removedLogin.cookie,{language:'en',texts:['待删除成员的翻译缓存']});
 await transaction(app.pool,async c=>{
  const row=(await c.query("SELECT payload FROM records WHERE id=?",[sharedProject.id])).rows[0];
  const legacy=JSON.parse(row.payload);legacy.bdId=removedEmail;legacy.saId=removedEmail;delete legacy.saIds;delete legacy.saAccounts;
  await c.query('UPDATE records SET payload=? WHERE id=?',[JSON.stringify(legacy),sharedProject.id]);
 });
 const month=new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Santiago'}).format(new Date()).slice(0,7);
 const ownSnapshot=await read('reports',removedLogin.cookie,{period:month,type:'全部',repo:'全部'},201);
 const originalSnapshot=(await read('reports',removedLogin.cookie)).find(r=>r.id===ownSnapshot.id);
 const duplicateKey=randomUUID();
 const movedAnalysis=await read('practices',removedLogin.cookie,{...diagram,requestKey:duplicateKey,title:'Member deletion image',businessType:'大数据',targetRegion:'Test'},202);
 await read('practices',admin.cookie,{...diagram,requestKey:duplicateKey,title:'Same key from another owner',businessType:'大数据',targetRegion:'Test'},202);
 await transaction(app.pool,c=>c.query("UPDATE architecture_analyses SET status='running',lease_until=TIMESTAMPADD(MINUTE,10,NOW()) WHERE id=?",[movedAnalysis.id]));
 const runningVersion=(await read('practices/'+movedAnalysis.id,admin.cookie)).version;
 const previewPath='admin/member-deletion?email='+encodeURIComponent(removedEmail);
 await read(previewPath,owner,undefined,403);
 await read('admin/member-deletion?email='+encodeURIComponent(env.ADMIN_EMAIL),secondAdmin,undefined,400);
 await read('admin/member-deletion?email='+encodeURIComponent(secondAdminEmail),secondAdmin,undefined,400);
 const memberPreview=await read(previewPath,admin.cookie);
 assert.equal(memberPreview.projectCount,3);assert.equal(memberPreview.analysisCount,1);assert.equal(memberPreview.reportCount,1);
 const deletionInput={email:removedEmail,userId:memberPreview.userId,_version:memberPreview._version};
 await read('admin/member',owner,deletionInput,403,'DELETE');
 await read('admin/member',admin.cookie,{...deletionInput,userId:randomUUID()},409,'DELETE');
 await read('admin/member',admin.cookie,{...deletionInput,_version:memberPreview._version-1},409,'DELETE');
 const adminUser=(await read('me',admin.cookie)).user;
 await assert.rejects(transaction(app.pool,client=>deleteMember({
  query:(sql,values)=>{
   if(sql.startsWith('DELETE FROM members'))throw Error('injected member-delete failure');
   return client.query(sql,values);
  }
 },adminUser,deletionInput,env.ADMIN_EMAIL)),/injected member-delete failure/);
 assert.equal((await request('workspace',removedLogin.cookie)).status,200);
 assert.equal((await read('workspace',admin.cookie)).projects.find(p=>p.id===assignedProject.id).bdId,removedUser.id);
 assert.equal((await read('practices/'+movedAnalysis.id,removedLogin.cookie)).owner_email,removedEmail);
 await read('admin/member',admin.cookie,deletionInput,200,'DELETE');
 for(const cookie of [removedLogin.cookie,removedDevice])await read('workspace',cookie,undefined,401);
 await login(removedEmail,removedLogin.password,401);
 await read('admin/member',admin.cookie,deletionInput,404,'DELETE');
 await read('admin/member',admin.cookie,{email:removedEmail,roleId:deletionRole.id,_version:memberPreview._version},404);
 const afterRemoval=await read('workspace',admin.cookie);
 for(const id of [assignedProject.id,sharedProject.id]){
  const p=afterRemoval.projects.find(p=>p.id===id);assert.equal(p.bdId,'');assert.equal(p.saId??'','');
  assert.equal(p.bdName,'');assert.equal(p.saName??'','');
 }
 const keptTeam=afterRemoval.projects.find(p=>p.id===retainedTeam.id);
 assert.deepEqual(keptTeam.saIds,[firstSA]);assert((await read('workspace',assigned)).projects.some(p=>p.id===retainedTeam.id));
 const cacheCount=await transaction(app.pool,async c=>(await c.query('SELECT COUNT(*) n FROM content_translations WHERE owner_id=?',[removedUser.id])).rows[0].n);assert.equal(Number(cacheCount),0);
 const retained=await read('practices/'+movedAnalysis.id,admin.cookie);
 assert.equal(retained.owner_email,env.ADMIN_EMAIL);assert.equal(retained.version,runningVersion);
 assert.deepEqual(Buffer.from(await (await request('practices/'+movedAnalysis.id+'/image',admin.cookie)).arrayBuffer()),probe.image);
 const retainedSnapshot=(await read('reports',admin.cookie)).find(r=>r.id===ownSnapshot.id);
 assert.deepEqual(retainedSnapshot.projects,originalSnapshot.projects);assert.deepEqual(retainedSnapshot.stats,originalSnapshot.stats);
 assert((await read('audit',admin.cookie)).some(entry=>entry.action==='删除成员：Removal QA'&&entry.entity===removedEmail));
 const remainingCredentials=await transaction(app.pool,async c=>(await c.query('SELECT (SELECT COUNT(*) FROM members WHERE email=?) AS members,(SELECT COUNT(*) FROM accounts WHERE email=?) AS accounts,(SELECT COUNT(*) FROM sessions WHERE email=?) AS sessions',[removedEmail,removedEmail,removedEmail])).rows[0]);
 assert.deepEqual(Object.values(remainingCredentials).map(Number),[0,0,0]);
 await transaction(app.pool,c=>c.query("UPDATE architecture_analyses SET status='queued',lease_until=NULL WHERE id=?",[movedAnalysis.id]));
 failAnalysis=false;
 await app.practices.runNext();await app.practices.runNext();
 assert.equal((await read('practices/'+movedAnalysis.id,admin.cookie)).status,'succeeded');
 await read('admin/member',admin.cookie,{email:removedEmail,roleId:deletionRole.id,displayName:'New identity'});
 const recreated=await personalize(removedEmail,'New identity');
 assert.notEqual((await read('me',recreated.cookie)).user.id,removedUser.id);
 assert.equal((await read('workspace',recreated.cookie)).projects.length,0);
 assert.equal((await read('practices',recreated.cookie)).items.length,0);
 assert(!(await read('reports',recreated.cookie)).some(r=>r.id===ownSnapshot.id));
 const newPreview=await read(previewPath,admin.cookie);
 await read('admin/member',admin.cookie,{email:removedEmail,userId:newPreview.userId,_version:newPreview._version},200,'DELETE');
 await read('admin/role',admin.cookie,{id:deletionRole.id,_version:1},200,'DELETE');
 console.log('PASS: member deletion, preview counts, transactional rollback, session revocation, legacy project assignments, private data handover and safe email reuse');

 const originalAdminHash=(await transaction(app.pool,c=>c.query('SELECT password_hash FROM accounts WHERE email=?',[env.ADMIN_EMAIL]))).rows[0].password_hash;
 await app.pool.end();env.INITIAL_ACCOUNT_PASSWORD=randomBytes(24).toString('hex');app=await start();
 assert.equal((await request('workspace',waiting)).status,401);await login(pending,firstPassword,401);
 const rotated=await login(pending,env.INITIAL_ACCOUNT_PASSWORD);
 assert.equal((await read('auth/status',rotated)).mustChangePassword,true);
 assert.equal((await request('workspace',admin.cookie)).status,200);
 const refreshed=(await transaction(app.pool,c=>c.query('SELECT password_hash FROM accounts WHERE email=?',[env.ADMIN_EMAIL]))).rows[0].password_hash;
 assert.equal(refreshed,originalAdminHash);
 assert.equal((await read('auth/profile',owner)).displayName,'业务负责人乙');
 assert.deepEqual((await read('workspace',admin.cookie)).navigation,{order:menuOrder,labels,_version:3});
 assert.equal((await read(list,unassigned)).total,1);assert.equal((await request(path+'/image',owner)).status,404);
 assert.deepEqual(Buffer.from(await (await request(path+'/image',newOwner)).arrayBuffer()),probe.image);
 console.log('PASS: atomic project upload, duplicate requests, worker retry, bilingual auto-archive, current BD/SA/admin-only access, reassignment and restart');
 console.log('PASS: RDS menu order, concurrent saves, role filtering and persistence after restart');
 console.log('PASS: MySQL migrations, account rotation, first sign-in, BD reassignment, private diagrams and drawings, redacted references and legacy review');
}finally{await app.practices.stop();await app.pool.end()}
