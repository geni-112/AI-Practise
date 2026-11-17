import {DatabaseSync} from 'node:sqlite';import fs from 'node:fs';import assert from 'node:assert/strict';
const root=(await import('node:url')).fileURLToPath(new URL('..',import.meta.url));const code=fs.readFileSync(root+'/dist/server/index.mjs','utf8');const mod=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));const db=new DatabaseSync(':memory:');db.exec(fs.readFileSync(root+'/drizzle/0000_workspace.sql','utf8'));db.exec('ALTER TABLE members ADD COLUMN version INTEGER NOT NULL DEFAULT 1');
class Statement{constructor(sql,params=[]){this.sql=sql;this.params=params}bind(...p){return new Statement(this.sql,p)}async first(){return db.prepare(this.sql).get(...this.params)||null}async all(){return {results:db.prepare(this.sql).all(...this.params)}}async run(){const r=db.prepare(this.sql).run(...this.params);return{meta:{changes:r.changes}}}}
const DB={prepare:sql=>new Statement(sql),async batch(stmts){db.exec('BEGIN');try{const r=[];for(const s of stmts)r.push(await s.run());db.exec('COMMIT');return r}catch(e){db.exec('ROLLBACK');throw e}}};
async function call(email,path,method='GET',body,id=email){const headers={};if(email){headers['oai-authenticated-user-id']=id;headers['oai-authenticated-user-email']=email}if(method!=='GET'){headers.Origin='https://test.local';headers['Content-Type']='application/json'}const res=await mod.default.fetch(new Request('https://test.local/api/'+path,{method,headers,body:method==='GET'?undefined:JSON.stringify(body)}),{DB,ADMIN_EMAIL:'owner@example.invalid'});return{status:res.status,body:await res.json()}}
const owner='owner@example.invalid';await mod.initialize(DB,{ADMIN_EMAIL:owner,IMPORT_LEGACY_DATA:true});assert.equal((await call(null,'workspace')).status,401);let me=await call(owner,'me');assert.equal(me.body.user.roleId,'admin');let ws=(await call(owner,'workspace')).body;assert.equal(ws.projects.length,0);assert.equal(ws.resources.length,0);const fixture=JSON.parse(fs.readFileSync(root+'/tests/fixtures.json','utf8'));for(const [kind,list]of [['project',fixture.projects],['resource',fixture.resources]])for(const item of list)await DB.prepare('INSERT INTO records(id,kind,payload) VALUES(?,?,?)').bind(item.id,kind,JSON.stringify(item)).run();ws=(await call(owner,'workspace')).body;for(const[email,roleId]of [['bd@test.com','bd'],['sa@test.com','sa'],['view@test.com','viewer']])assert.equal((await call(owner,'admin/member','POST',{email,roleId})).status,200);
const p=ws.projects[0],other=ws.projects[1];assert.equal((await call(owner,'projects/'+p.id,'PATCH',{_version:p._version,bdId:'bd@test.com',saId:'sa@test.com'})).status,200);assert.equal((await call('bd@test.com','workspace')).body.projects.length,1);assert.equal((await call('bd@test.com','projects/'+other.id,'PATCH',{_version:1,next:'hijack'})).status,403);assert.equal((await call('view@test.com','workspace')).body.projects.length,0);assert.equal((await call('view@test.com','admin')).status,403);assert.equal((await call('view@test.com','projects','POST',{name:'bad'})).status,403);let sp=(await call('sa@test.com','workspace')).body.projects[0];assert(!('eiPlan'in sp));assert.equal((await call('sa@test.com','projects/'+p.id,'PATCH',{_version:sp._version,eiPlan:10})).status,403);assert.equal((await call('sa@test.com','projects/'+p.id,'PATCH',{_version:sp._version,next:'unauthorized'})).status,403);assert.equal((await call('sa@test.com','projects/'+p.id,'PATCH',{_version:sp._version,notes:'POC update',update:'验证范围确认'})).status,200);assert.equal((await call('bd@test.com','projects/'+p.id,'PATCH',{_version:sp._version,next:'stale'})).status,409);
let bp=(await call('bd@test.com','workspace')).body.projects[0];assert.equal((await call('bd@test.com','projects/'+p.id,'PATCH',{_version:bp._version,milestones:{'POC 资源':'已完成'}})).status,403);assert.equal((await call('bd@test.com','projects/'+p.id,'PATCH',{_version:bp._version,next:'Arrange workshop'})).status,200);const live=await call(owner,'reports/preview','POST',{period:'2025-06'});assert.equal(live.status,200);assert.equal(live.body.stats.monthlyActual,null);assert.equal(live.body.stats.projects,2);const viewer=await call('view@test.com','reports/preview','POST',{period:'2025-06'});assert.equal(viewer.body.projects.length,0);assert.equal((await call('view@test.com','reports','POST',{period:'2025-06'})).status,403);let archive=await call(owner,'reports','POST',{period:'2025-06',summary:'Reviewed report'});assert.equal(archive.status,201);let current=(await call('bd@test.com','workspace')).body.projects[0];assert.equal((await call('bd@test.com','projects/'+p.id,'PATCH',{_version:current._version,next:'Changed after archive'})).status,200);assert.equal((await call(owner,'reports')).body[0].summary,'Reviewed report');assert.equal((await call('view@test.com','reports')).body[0].stats.annualPlan,null);assert.equal((await call('view@test.com','reports/'+archive.body.id+'/export')).status,200);
const role=await call(owner,'admin/role','POST',{name:'技术观察员',permissions:['project.read.own','resource.read']});assert.equal(role.status,200);await call(owner,'admin/member','POST',{email:'custom@test.com',roleId:role.body.id});assert.equal((await call('custom@test.com','me')).body.user.roleName,'技术观察员');assert.equal((await call('custom@test.com','reports')).status,403);assert.equal((await call('custom@test.com','admin/role','POST',{name:'attack',permissions:['role.manage']})).status,403);assert.equal((await call('bd@test.com','me','GET',undefined,'another-id')).status,403);await call(owner,'admin/member','POST',{email:'bd@test.com',roleId:'bd',enabled:false,_version:1});assert.equal((await call('bd@test.com','workspace')).status,403);
console.log('PASS: empty initial workspace; synthetic fixtures; owner binding; default and custom roles; own-project scope; field-level RBAC; finance redaction; stale update conflict; milestone protection; view/export; immutable snapshots; member disable; identity mismatch');

assert.equal((await call('view@test.com','source/download')).status,403);
const sourceResponse=await mod.default.fetch(new Request('https://test.local/api/source/download',{headers:{'oai-authenticated-user-id':owner,'oai-authenticated-user-email':owner}}),{DB,ADMIN_EMAIL:'owner@example.invalid'});assert.equal(sourceResponse.status,200);assert.equal(sourceResponse.headers.get('Content-Type'),'application/zip');const zipBytes=new Uint8Array(await sourceResponse.arrayBuffer());assert.equal(zipBytes[0],80);assert.equal(zipBytes[1],75);console.log('PASS: source download restricted to administrators, valid ZIP signature');

const bdEmail='workflow-bd@example.invalid',saEmail='workflow-sa@example.invalid',otherBD='second-bd@example.invalid';
for(const [email,roleId] of [[bdEmail,'bd'],[saEmail,'sa'],[otherBD,'bd']])await call(owner,'admin/member','POST',{email,roleId});
const available=(await call(bdEmail,'workspace')).body.members;
assert(available.some(m=>m.email===saEmail));assert(available.every(m=>m.enabled&&m.role_id==='sa'));
const ownProject=await call(bdEmail,'projects','POST',{name:'Alpha-Workstream',stage:4,saId:saEmail});
assert.equal(ownProject.status,201);assert.equal(ownProject.body.saName,saEmail);
assert((await call(saEmail,'workspace')).body.projects.some(p=>p.id===ownProject.body.id));
assert.equal((await call(otherBD,'projects/'+ownProject.body.id,'PATCH',{_version:1,saId:''})).status,403);
assert.equal((await call(bdEmail,'projects/'+ownProject.body.id,'PATCH',{_version:1,saId:otherBD})).status,400);
assert.equal((await call(bdEmail,'projects/'+ownProject.body.id,'PATCH',{_version:1,bdId:otherBD})).status,403);
const active=ownProject.body;
const cases=[active,{...active,id:'lost',status:'丢单',risk:true},{...active,id:'hold',status:'挂起'},{...active,id:'archived',archivedAt:'2024-11-01'}];
const poc=mod.buildReport(cases,'2099-10');assert.equal(poc.stats.poc,1);assert.equal(poc.groups[0].poc,1);assert.equal(poc.stats.blocked,1);

const fill=(id,kind,obj)=>db.prepare('INSERT INTO records(id,kind,payload) VALUES(?,?,?)').run(id,kind,JSON.stringify(obj));
fill('report-history-v1','meta',{month:'2024-10'});
const timed={...active,name:'October opportunity',repo:'Monthly fixture',pipelineDate:'2024-10-01',updatedAt:'2024-10-25',stage:4,actuals:[{month:'2024-10',kind:'EI',amount:1}]};
db.prepare('UPDATE project_report_states SET payload=?,effective_month=? WHERE project_id=?').run(JSON.stringify(timed),'2024-10',active.id);
db.prepare('UPDATE records SET payload=? WHERE id=?').run(JSON.stringify(timed),active.id);
assert.equal((await call(bdEmail,'projects/'+active.id,'PATCH',{_version:1,stage:6,next:'November-only instruction'})).status,200);
db.prepare("UPDATE project_report_states SET effective_month='2024-11' WHERE project_id=? AND project_version=2").run(active.id);
const filters={period:'2024-10',type:'全部',repo:'Monthly fixture'};
const october=await call(owner,'reports/preview','POST',filters);
assert.equal(october.body.basis,'monthEnd');assert.equal(october.body.stats.poc,1);assert.equal(october.body.stats.signed,0);
assert.equal((await call(owner,'reports/preview','POST',{...filters,period:'2024-11'})).body.stats.signed,1);
const old=await call(owner,'reports/preview','POST',{...filters,period:'2024-09'});assert.equal(old.body.basis,'ledger');
const forecast=await call(owner,'reports/template','POST',{...filters,period:'2024-09',format:'html',language:'en'});assert(forecast.body.html.includes('Recalculated from the current ledger'));
const frozen=(await call(owner,'reports','POST',{...filters,summary:'Board-only custom summary'})).body;
assert.equal((await call(owner,'reports/preview','POST',filters)).body.id,frozen.id);
assert.equal((await call(owner,'reports/preview','POST',filters)).body.basis,'snapshot');
const reader=(await call(owner,'admin/role','POST',{name:'Limited report author',permissions:['project.read.own','report.view','report.generate','report.export','finance.read']})).body;
await call(owner,'admin/member','POST',{email:otherBD,roleId:reader.id,_version:1});
const restricted=(await call(otherBD,'reports/'+frozen.id+'/export')).body;
assert.equal(restricted.stats.projects,0);assert.equal(restricted.groups.length,0);
for(const marker of ['October opportunity','Board-only custom summary','November-only instruction','reportInputs'])assert(!JSON.stringify(restricted).includes(marker));
const overview=(await call('view@test.com','reports/'+frozen.id+'/export')).body;assert.deepEqual(overview.projects,[]);assert(!JSON.stringify(overview).includes('October opportunity'));
console.log('PASS: BD assignment boundaries, active POC counts, month-end states, historical fallback, fixed snapshots and role-scoped report exports');

const initialNav=(await call(owner,'navigation')).body;
const defaultMenu=['practices','home','projects','poc','library','reports','admin','maas','audit'];
assert.deepEqual(initialNav,{order:defaultMenu,_version:0});
const reversed=[...defaultMenu].reverse();
for(const order of [null,defaultMenu.slice(1),[...defaultMenu.slice(1),'future'],[...defaultMenu.slice(1),'home']]){
 assert.equal((await call(owner,'admin/navigation','POST',{order,_version:0})).status,400);
}
assert.equal((await call(owner,'admin/navigation','POST',{order:reversed})).status,400);
assert.equal((await call(bdEmail,'admin/navigation','POST',{order:reversed,_version:0})).status,403);
const savedMenu=await call(owner,'admin/navigation','POST',{order:reversed,_version:0});
assert.deepEqual(savedMenu.body,{order:reversed,_version:1});
assert.equal((await call(owner,'admin/navigation','POST',{order:defaultMenu,_version:0})).status,409);
assert.deepEqual((await call(owner,'workspace')).body.navigation,savedMenu.body);
assert.deepEqual((await call('view@test.com','workspace')).body.navigation.order,['reports']);
assert.deepEqual((await call(bdEmail,'navigation')).body.order,['library','poc','projects','home']);
const changedNav=await call(owner,'admin/navigation','POST',{order:defaultMenu,_version:1});assert.equal(changedNav.body._version,2);
assert.equal((await call(owner,'admin/navigation','POST',{order:reversed,_version:1})).status,409);
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM audit WHERE entity='workspace-navigation-v1'").get().n,2);
const labels={home:{zh:'项目看板',en:'Team <overview>'},maas:{zh:'模型配置'}};
const saveLabels=(labels,_version,order=defaultMenu)=>call(owner,'admin/navigation','POST',{order,labels,_version});
for(const invalid of [null,[],{hidden:{zh:'x'}},{home:[]},{home:{fr:'x'}},{home:{en:4}},{home:{zh:'x'.repeat(49)}},{home:{en:'two\nlines'}}]){
 assert.equal((await saveLabels(invalid,2)).status,400);
}
assert.equal((await call(bdEmail,'admin/navigation','POST',{order:defaultMenu,labels,_version:2})).status,403);
const rename=await saveLabels({...labels,home:{...labels.home,zh:' 项目看板 '},reports:{zh:'报表中心',en:''}},2);
assert.deepEqual(rename.body,{order:defaultMenu,labels,_version:3});
assert.deepEqual((await call(owner,'workspace')).body.navigation,rename.body);
assert.deepEqual((await call(bdEmail,'navigation')).body.labels,{home:labels.home});
assert.equal((await call('view@test.com','workspace')).body.navigation.labels,undefined);
assert.equal((await saveLabels({},2)).status,409);
const legacyWrite=await call(owner,'admin/navigation','POST',{order:reversed,_version:3});
assert.deepEqual(legacyWrite.body,{order:reversed,labels,_version:4});
const resetNames=await saveLabels({home:{zh:'',en:'Overview'}},4,reversed);
assert.deepEqual(resetNames.body,{order:reversed,_version:5});
// Older saved orders can contain a retired entry and omit a newly added entry.
db.prepare('UPDATE records SET payload=? WHERE id=?').run(JSON.stringify({order:['reports','retired','home','reports']}),'workspace-navigation-v1');
assert.deepEqual((await call(owner,'navigation')).body.order,['reports','home',...defaultMenu.filter(id=>!['reports','home'].includes(id))]);
console.log('PASS: workspace navigation order, role-scoped reads, admin-only writes, bilingual names, locale resets, order-only clients, conflicts, audit, and menu evolution');
