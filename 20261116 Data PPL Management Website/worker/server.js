
export const PERMISSIONS={
 'practice.read':'查看最佳实践','practice.analyze':'提交架构分析','practice.manage':'管理独立分析和参考案例',
 'project.read.all':'查看全部项目','project.read.own':'查看负责项目','project.create':'创建项目','project.biz.all':'维护全部项目商务信息','project.biz.own':'维护负责项目商务信息','project.tech.all':'维护全部项目技术信息','project.tech.own':'维护负责项目技术信息','project.assign':'分配 BD / SA 负责人','project.assign.sa.own':'为本人负责的项目指派 SA','project.archive':'归档与恢复项目','finance.read':'查看收入与预测','finance.write.all':'维护全部项目收入','finance.write.own':'维护负责项目收入','resource.read':'查看资料库','resource.write':'维护资料库','resource.archive':'归档与恢复资料','report.view':'查看报表','report.export':'导出报表','report.generate':'生成报表草稿','report.archive':'保存月报快照','member.manage':'管理成员','role.manage':'管理角色与权限','audit.view':'查看操作记录'};
export const DEFAULT_ROLES=[{id:'admin',name:'管理员',permissions:Object.keys(PERMISSIONS),builtin:true},{id:'viewer',name:'报表查看者',permissions:['report.view','report.export'],builtin:true},{id:'bd',name:'BD',permissions:['project.read.own','project.create','project.biz.own','project.assign.sa.own','finance.read','finance.write.own','resource.read'],builtin:true},{id:'sa',name:'SA',permissions:['project.read.own','project.tech.own','resource.read','resource.write'],builtin:true}];
const biz=['name','customer','type','cloud','region','repo','industry','priority','strategic','confidence','delivery','business','bdName','next','due','status','risk','stage'];
const tech=['vendor','scenario','notes','saName','milestones'];
const finance=['planYear','eiPlan','servicePlan','eiSpace','totalSpace','actuals'];
const financeNames=new Set(finance);
const j=(d,status=200)=>new Response(JSON.stringify(d),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','Vary':'Cookie','X-Content-Type-Options':'nosniff'}});
const fail=(status,msg)=>{throw Object.assign(new Error(msg),{status})};
const now=()=>new Date().toISOString();
export function has(u,p){return !!u?.permissions?.includes(p)}
export function projectSAIds(p){return [...new Set((Array.isArray(p.saIds)?p.saIds:p.saId?[p.saId]:[]).filter(id=>typeof id==='string'&&id))]}
export function owns(u,p){return [p.bdId,...projectSAIds(p)].some(id=>id&&(id===u.id||id===u.email))}
export function canRead(u,p){return has(u,'project.read.all')||(has(u,'project.read.own')&&owns(u,p))}
export function canWrite(u,p,part){return has(u,`${part}.all`)||(has(u,`${part}.own`)&&owns(u,p))}
export function redact(u,p){const r=structuredClone(p);if(!has(u,'finance.read'))for(const k of financeNames)delete r[k];return r}
async function all(db,kind){const r=await db.prepare('SELECT id,payload,version FROM records WHERE kind=?').bind(kind).all();return r.results.map(x=>({...JSON.parse(x.payload),id:x.id,_version:x.version}))}
async function get(db,id,kind){const r=await db.prepare('SELECT payload,version FROM records WHERE id=? AND kind=?').bind(id,kind).first();return r?{...JSON.parse(r.payload),id,_version:r.version}:null}
async function insert(db,kind,obj){await db.prepare('INSERT INTO records(id,kind,payload) VALUES(?,?,?)').bind(obj.id,kind,JSON.stringify(obj)).run()}
async function change(db,kind,obj,version){const result=await db.prepare('UPDATE records SET payload=?,version=version+1 WHERE id=? AND kind=? AND version=?').bind(JSON.stringify(obj),obj.id,kind,version).run();if(result.meta.changes!==1)fail(409,'内容已被其他人更新，请刷新后重试')}
async function audit(db,u,action,entity){await db.prepare('INSERT INTO audit(id,actor,action,entity,at) VALUES(?,?,?,?,?)').bind(crypto.randomUUID(),u.email,action,entity,now()).run()}
export async function initialize(db,env={}){const existing=await db.prepare("SELECT id FROM records WHERE id='setup-v2'").first();if(existing)return;const statements=DEFAULT_ROLES.map(r=>db.prepare('INSERT OR IGNORE INTO records(id,kind,payload) VALUES(?,?,?)').bind(r.id,'role',JSON.stringify(r)));await db.batch(statements);await db.prepare('INSERT OR IGNORE INTO members(email,user_id,role_id,enabled) VALUES(?,NULL,?,1)').bind(env.ADMIN_EMAIL,'admin').run();await db.prepare('INSERT OR IGNORE INTO records(id,kind,payload) VALUES(?,?,?)').bind('setup-v2','meta',JSON.stringify({file:'工作空间项目台账',sheet:'项目',rows:0,latestKnownDate:null})).run()}
const navigationSettingId='workspace-navigation-v1';
function navigationView(order,labels,version) {
 const visible=Object.fromEntries(order.filter(id=>labels?.[id]).map(id=>[id,labels[id]]));
 return {order,...(Object.keys(visible).length?{labels:visible}:{}),_version:version};
}
async function workspaceNavigation(db,user) {
 const saved=await get(db,navigationSettingId,'meta');
 const order=orderedWorkspaceMenus(saved?.order).filter(menu=>user.roleId==='admin'||canSeeWorkspaceMenu(user,menu)).map(menu=>menu.id);
 return navigationView(order,saved?.labels,saved?._version||0);
}
function normalizeNavigationLabels(input) {
 const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
 if(!object(input))fail(400,'栏目名称格式无效');
 const labels={};
 for(const [id,pair] of Object.entries(input)){
  if(!workspaceMenuIds.includes(id)||!object(pair))fail(400,'栏目名称格式无效');
  const menu=workspaceMenus.find(item=>item.id===id),names={};
  for(const [lang,value] of Object.entries(pair)){
   if(!['zh','en'].includes(lang)||typeof value!=='string')fail(400,'栏目名称格式无效');
   const name=value.trim();
   if(name.length>48||/[\u0000-\u001f\u007f]/u.test(value))fail(400,'栏目名称最多 48 个字符，须为单行文字');
   if(name&&name!==(lang==='en'?menu.en:menu.label))names[lang]=name;
  }
  if(Object.keys(names).length)labels[id]=names;
 }
 return labels;
}
async function saveWorkspaceNavigation(db,user,body) {
 if(user.roleId!=='admin')fail(403,'仅管理员可编辑导航');
 const {order,_version}=body||{};
 if(!Array.isArray(order)||order.length!==workspaceMenuIds.length||new Set(order).size!==order.length||order.some(id=>!workspaceMenuIds.includes(id)))fail(400,'导航顺序须包含每个菜单一次');
 if(!Number.isSafeInteger(_version)||_version<0)fail(400,'导航版本无效');
 // Order-only clients keep the names from the same revision. The write checks that revision.
 const labels=Object.hasOwn(body,'labels')?normalizeNavigationLabels(body.labels):(await get(db,navigationSettingId,'meta'))?.labels;
 const entry={id:navigationSettingId,order,...(labels&&Object.keys(labels).length?{labels}:{})};
 if(_version===0){
  const inserted=await db.prepare('INSERT OR IGNORE INTO records(id,kind,payload) VALUES(?,?,?)').bind(entry.id,'meta',JSON.stringify(entry)).run();
  if(inserted.meta.changes!==1)fail(409,'导航已被其他管理员更新');
 }else await change(db,'meta',entry,_version);
 await audit(db,user,Object.hasOwn(body,'labels')?'编辑工作台导航':'调整工作台导航顺序',entry.id);
 return navigationView(order,labels,_version+1);
}
export async function initializeAssignmentPermission(db) {
 if(await get(db,'assign-sa-v1','meta'))return;
 for(const id of ['bd','admin']){
  const role=await get(db,id,'role');
  if(!role || role.permissions.includes('project.assign.sa.own') || id==='bd'&&!role.permissions.includes('project.biz.own'))continue;
  role.permissions.push('project.assign.sa.own');await change(db,'role',role,role._version);
 }
 await insert(db,'meta',{id:'assign-sa-v1'});
}
function canAssignOwnSA(user,project){
 return has(user,'project.assign.sa.own') && !!project.bdId && [user.id,user.email].includes(project.bdId);
}
export async function memberDeletionImpact(db,member){
 const matches=value=>!!value&&(value===member.user_id||value===member.email);
 const projects=(await all(db,'project')).filter(project=>matches(project.bdId)||projectSAIds(project).some(matches));
 const reports=(await all(db,'report')).filter(report=>report.scopeOwner===member.email);
 return {projectCount:projects.length,reportCount:reports.length};
}
export async function detachMemberRecords(db,actor,member,adminEmail){
 const matches=value=>!!value&&(value===member.user_id||value===member.email);
 let projectCount=0,reportCount=0;
 for(const project of await all(db,'project')){
  const bd=matches(project.bdId),sas=projectSAIds(project),remaining=sas.filter(id=>!matches(id));
  if(!bd&&sas.length===remaining.length)continue;
  if(bd)for(const suffix of ['Id','Name','AccountName','AccountEmail'])project['bd'+suffix]='';
  if(remaining.length!==sas.length){
   project.saIds=remaining;project.saId=remaining[0]||'';
   project.saAccounts=(project.saAccounts||[]).filter(account=>remaining.includes(account.id));
   project.saName=project.saAccounts.map(account=>account.displayName).filter(Boolean).join(' / ');
   project.saAccountName=project.saName;project.saAccountEmail=project.saAccounts.map(account=>account.email).join(', ');
  }
  project.updatedAt=now();
  project.logs??=[];
  project.logs.push({at:project.updatedAt,text:'成员已删除，已移除对应项目指派',by:actor.email,byDisplayName:actor.displayName||'',system:true});
  await change(db,'project',project,project._version);
  await rememberProject(db,project,project._version+1);
  projectCount++;
 }
 for(const report of await all(db,'report')){
  const owned=report.scopeOwner===member.email;
  const missingName=report.publishedBy===member.email&&!report.publishedByName&&member.display_name;
  if(!owned&&!missingName)continue;
  if(owned){report.scopeOwner=adminEmail;reportCount++}
  if(missingName)report.publishedByName=member.display_name;
  await change(db,'report',report,report._version);
 }
 return {projectCount,reportCount};
}
async function assignmentMembers(db,user){
 if(has(user,'project.assign'))return (await db.prepare('SELECT email,user_id,role_id,enabled,version,display_name FROM members').all()).results;
 if(!has(user,'project.assign.sa.own'))return [];
 return (await db.prepare("SELECT email,user_id,role_id,enabled,display_name FROM members WHERE enabled=1 AND role_id='sa' ORDER BY email").all()).results;
}
async function memberNames(db) {
 const rows=(await db.prepare('SELECT email,user_id,display_name FROM members').all()).results;
 const names=new Map();
 for(const member of rows)for(const id of [member.email,member.user_id])if(id&&member.display_name)names.set(id,member.display_name);
 return names;
}
function withMemberNames(project,names) {
 const named={...project};
 for(const key of ['bd','sa']){
  const saved=project[key+'Name']||'';
  named[key+'DisplayName']=key==='bd'&&project.bdNameManual?saved:names.get(project[key+'Id'])||(!saved.includes('@')?saved:'');
 }
 const saNames=projectSAIds(project).map(id=>names.get(id)||project.saAccounts?.find(account=>account.id===id)?.displayName||'').filter(Boolean);
 named.saIds=projectSAIds(project);if(saNames.length)named.saDisplayName=saNames.join(' / ');
 named.logs=(project.logs||[]).map(log=>({...log,byDisplayName:names.get(log.by)||log.byDisplayName||''}));
 return named;
}
function setManualBDName(project,value){
 if(typeof value!=='string'||value.trim().length>120||/[\r\n\u0000-\u001f]/u.test(value))fail(400,'BD 姓名须为不超过 120 个字符的单行文字');
 project.bdName=value.trim();project.bdNameManual=true;
}
async function assignBD(db,project,previous,displayName) {
 if(previous&&project.bdId===previous.bdId)return;
 if(!project.bdId){project.bdAccountEmail='';project.bdAccountName='';project.bdName=displayName||'';return;}
 if(typeof project.bdId!=='string'||project.bdId.length>190)fail(400,'BD 账号无效');
 const member=await db.prepare('SELECT email,user_id,display_name,enabled FROM members WHERE email=? OR user_id=?').bind(project.bdId,project.bdId).first();
 if(!member?.enabled)fail(400,'请选择已启用的 BD 账号');
 project.bdId=member.user_id||member.email;
 project.bdAccountEmail=member.email;project.bdAccountName=member.display_name||'';
 project.bdName=displayName||member.display_name||'';
}
async function assignSA(db,user,project,value,previous,displayName) {
 if(!Array.isArray(value)){
  if(typeof value!=='string'||value.length>190)fail(400,'SA 账号无效');
  if(previous&&projectSAIds(previous).length>1){
   if(value===previous.saId)return;
   fail(409,'项目已配置多个 SA，请刷新后重新选择');
  }
  value=value?[value]:[];
 }
 if(value.length>20||value.some(id=>typeof id!=='string'||!id||id.length>190)||new Set(value).size!==value.length)fail(400,'请选择最多 20 个不同的 SA 账号');
 if(previous&&JSON.stringify(value)===JSON.stringify(projectSAIds(previous)))return;
 if(!has(user,'project.assign')&&!canAssignOwnSA(user,previous||project))fail(403,'只能为本人负责的项目指派 SA');
 const accounts=[];
 for(const id of value){
  const member=await db.prepare('SELECT email,user_id,role_id,enabled,display_name FROM members WHERE email=? OR user_id=?').bind(id,id).first();
  if(!member?.enabled||!has(user,'project.assign')&&member.role_id!=='sa')fail(400,'请选择已启用的 SA 账号');
  const account={id:member.user_id||member.email,email:member.email,displayName:member.display_name||''};
  if(accounts.some(existing=>existing.id===account.id))fail(400,'请选择不同的 SA 账号');
  accounts.push(account);
 }
 project.saIds=accounts.map(account=>account.id);project.saId=project.saIds[0]||'';
 project.saAccounts=accounts;project.saAccountEmail=accounts.map(account=>account.email).join(', ');
 project.saAccountName=accounts.map(account=>account.displayName).filter(Boolean).join(' / ');
 project.saName=project.saAccountName||displayName||'';
}
function saInput(body){
 if(Object.hasOwn(body,'saIds')&&Object.hasOwn(body,'saId'))fail(400,'请使用一个 SA 账号列表');
 return Object.hasOwn(body,'saIds')?body.saIds:body.saId;
}
async function identity(req,db){const id=req.headers.get('oai-authenticated-user-id'),email=(req.headers.get('oai-authenticated-user-email')||'').toLowerCase();if(!id||!email)fail(401,'请先登录');const member=await db.prepare('SELECT * FROM members WHERE email=?').bind(email).first();if(!member||!member.enabled)fail(403,'账号尚未获授权，请联系管理员');if(member.user_id&&member.user_id!==id)fail(403,'账号身份不匹配');if(!member.user_id){await db.prepare('UPDATE members SET user_id=? WHERE email=? AND user_id IS NULL').bind(id,email).run();const check=await db.prepare('SELECT user_id FROM members WHERE email=?').bind(email).first();if(check.user_id!==id)fail(403,'身份绑定失败')}const role=await get(db,member.role_id,'role');if(!role)fail(403,'角色不存在');return{id,email,displayName:member.display_name||'',profileVersion:member.version,roleId:role.id,roleName:role.name,permissions:role.permissions}}
function requireP(u,p){if(!has(u,p))fail(403,'当前角色没有此操作权限')}
function validateProject(p){for(const k of [...biz,...tech].filter(k=>!['stage','risk','milestones'].includes(k)))if(p[k]!==undefined&&p[k]!==null&&(typeof p[k]!=='string'||p[k].length>(k==='notes'?50000:2000)))fail(400,'项目字段格式无效：'+k);if(p.status&&!['正常','挂起','丢单'].includes(p.status))fail(400,'推进状态无效');if(p.risk!==undefined&&typeof p.risk!=='boolean')fail(400,'阻塞标记无效');if(p.planYear!=null&&(!Number.isInteger(p.planYear)||p.planYear<2000||p.planYear>2100))fail(400,'计划年份无效');if(p.due&&(!/^\d{4}-\d{2}-\d{2}$/.test(p.due)||!Number.isFinite(Date.parse(p.due+'T00:00:00Z'))||new Date(p.due+'T00:00:00Z').toISOString().slice(0,10)!==p.due))fail(400,'行动日期无效');if(typeof p.name!=='string'||!p.name.trim()||p.name.length>200)fail(400,'请填写有效项目名称');if(!Number.isInteger(p.stage)||p.stage<0||p.stage>8)fail(400,'项目阶段无效');for(const k of ['eiPlan','servicePlan','eiSpace','totalSpace'])if(p[k]!==null&&p[k]!==undefined&&(!Number.isFinite(p[k])||p[k]<0))fail(400,'金额必须为非负数');if(p.actuals){if(!Array.isArray(p.actuals)||p.actuals.length>500)fail(400,'收入明细无效');for(const a of p.actuals)if(!a||!/^\d{4}-(0[1-9]|1[0-2])$/.test(a.month)||!Number.isFinite(a.amount)||a.amount<0||!['EI','专业服务'].includes(a.kind))fail(400,'收入日期、类型或金额无效')}}
function validateMilestones(u,p,value,allowCreateBusiness=false){
 if(!value||typeof value!=='object'||Array.isArray(value))fail(400,'里程碑字段无效');
 const businessKeys=['高层对标','合同签订'];
 for(const [key,status]of Object.entries(value)){
  if(!['高层对标','技术交流','方案设计','POC 资源','POC 验收','合同签订'].includes(key)||!['未开展','进行中','已完成','不适用'].includes(status))fail(400,'里程碑字段无效');
  const business=businessKeys.includes(key);
  if((p.milestones?.[key]||'未开展')!==status&&!(business&&allowCreateBusiness)&&!canWrite(u,p,business?'project.biz':'project.tech'))fail(403,'无权修改该里程碑');
 }
}
function validateResource(b){for(const k of ['title','tag','body','url'])if(b[k]!==undefined&&(typeof b[k]!=='string'||b[k].length>(k==='body'?50000:k==='url'?2048:200)))fail(400,'资料字段无效');if(b.url){let url;try{url=new URL(b.url)}catch{fail(400,'来源链接无效')}if(url.protocol!=='https:'||url.username||url.password)fail(400,'来源链接须为 HTTPS');}}
function reportProjects(u,ps){return has(u,'project.read.all')?ps:has(u,'project.read.own')?ps.filter(p=>canRead(u,p)):ps;}
function reportForUser(u,r){if(!r?.stats||has(u,'finance.read'))return r;const result=structuredClone(r);for(const key of ['monthlyActual','ytdActual','yoy','annualPlan','planCoverage','revenueCoverage'])result.stats[key]=null;result.projects=result.projects.map(p=>{const v=redact(u,p);v.notes='';v.weekly='';delete v.ytdActual;delete v.priorYtdActual;return v;});result.groups=result.groups.map(g=>({...g,ytdActual:null,priorYtdActual:null,yoy:null}));result.contact='';result.updates=[];result.summaryGenerated=true;result.summary='本期可见项目 '+result.stats.projects+' 个，新增 '+result.stats.newProjects+' 个；收入数据及自定义总述需收入查看权限。';result.support=[];result.warnings=[...result.warnings,'当前角色未获得收入查看权限。'];result.financeHidden=true;return result;}
function updateMonth(value){
 if(typeof value!=='string'||!/^\d{4}-\d\d-\d\d/.test(value))return '';
 if(value.length===10)return value.slice(0,7);
 const date=new Date(value);return Number.isNaN(date.valueOf())?'':santiagoDate(date).slice(0,7);
}
function projectStamp(p){return p.updatedAt||p.pipelineDate||''}
export function buildReport(projects,period,type='全部',repo='全部',source={file:'工作空间项目台账',sheet:'项目与进展'}){const end=period+'-31',year=Number(period.slice(0,4));const scope=projects.filter(p=>!p.archivedAt&&(type==='全部'||p.type===type)&&(repo==='全部'||p.repo===repo));const selected=scope.filter(p=>!p.pipelineDate||p.pipelineDate<=end);const periodEligible=selected.filter(p=>projectStamp(p)&&projectStamp(p)<=end);const future=selected.length-periodEligible.length;const groups=Object.create(null);for(const p of selected){const g=groups[p.repo||'未填写']??={repo:p.repo||'未填写',repoMissing:!p.repo,count:0,poc:0,signed:0,blocked:0};g.count++;if(isActivePoc(p))g.poc++;if(p.stage>=6&&p.status!=='丢单')g.signed++;if(needsProjectAttention(p))g.blocked++}const actuals=selected.flatMap(p=>(p.actuals||[]).map(a=>({...a,projectId:p.id})));const monthly=actuals.filter(a=>a.month===period);const ytd=actuals.filter(a=>a.month.startsWith(String(year))&&a.month<=period);const prior=actuals.filter(a=>a.month.startsWith(String(year-1))&&a.month<=String(year-1)+period.slice(4));const planProjects=selected.filter(p=>p.planYear===year&&(p.eiPlan!=null||p.servicePlan!=null));const fresh=selected.flatMap(p=>(p.logs||[]).filter(l=>updateMonth(l.at)===period).map(l=>({...l,project:p.name})));const knownDates=selected.map(projectStamp).filter(Boolean).sort();const lastKnown=knownDates.at(-1)||null;const stats={projects:selected.length,customers:new Set(selected.map(p=>p.customer||p.name)).size,newProjects:selected.filter(p=>p.pipelineDate?.startsWith(period)).length,poc:selected.filter(isActivePoc).length,signed:selected.filter(p=>p.stage>=6&&p.status!=='丢单').length,blocked:selected.filter(needsProjectAttention).length,monthlyActual:monthly.length?monthly.reduce((n,a)=>n+a.amount,0):null,ytdActual:ytd.length?ytd.reduce((n,a)=>n+a.amount,0):null,yoy:ytd.length&&prior.length&&prior.reduce((n,a)=>n+a.amount,0)!==0?ytd.reduce((n,a)=>n+a.amount,0)/prior.reduce((n,a)=>n+a.amount,0)-1:null,annualPlan:planProjects.length?planProjects.reduce((n,p)=>n+(p.eiPlan||0)+(p.servicePlan||0),0):null,planCoverage:planProjects.length,revenueCoverage:new Set(ytd.map(a=>a.projectId)).size,updates:fresh.length};const warnings=['年度计划与实际收入分别记录；空值不视作零。'];if(lastKnown?.slice(0,7)<period)warnings.push('本期没有足够的新进展，最近已知更新为 '+lastKnown+'；以下为历史存量信息。');if(!monthly.length)warnings.push('本月无已记录实际收入，收入完成额暂不可计算。');if(future)warnings.push('部分项目记录晚于所选月份或缺少日期，不能据此还原该月进展。');const snapshot={id:crypto.randomUUID(),period,type,repo,generatedAt:now(),source,stats,groups:Object.values(groups),warnings,lastKnown,updates:fresh,projects:selected.map(p=>({id:p.id,name:p.name,repo:p.repo,type:p.type,vendor:p.vendor,scenario:p.scenario,stage:p.stage,originalStage:p.originalStage,status:p.status,notes:p.notes,weekly:p.weekly,next:p.next,due:p.due,updatedAt:p.updatedAt,eiPlan:p.planYear===year?p.eiPlan:null,servicePlan:p.planYear===year?p.servicePlan:null,bdName:p.bdName,saName:p.saName,milestones:p.milestones})),support:[],summaryGenerated:true,summary:`${period} ${type==='全部'?'数据业务':type}专项：台账共 ${stats.projects} 个机会点、${stats.customers} 个客户，本月新增入管道 ${stats.newProjects} 个。进行中的 POC 准备/验证项目 ${stats.poc} 个，挂起或有阻塞 ${stats.blocked} 个。本月记录 ${stats.updates} 条更新。${stats.monthlyActual===null?'本月实际收入缺少记录，待补齐。':'本月已记录实际收入 '+stats.monthlyActual.toFixed(3)+' M USD（部分覆盖，非财务核定总额）。'}`};return enrichReportRevenue(snapshot,selected)}
export default {async fetch(req,env){try{const url=new URL(req.url),path=url.pathname;if(!path.startsWith('/api/')){const file=path==='/'?'index.html':path.slice(1);if(!Object.hasOwn(ASSETS,file))return new Response('Not found',{status:404});return new Response(ASSETS[file],{headers:{'Content-Type':file.endsWith('.css')?'text/css; charset=utf-8':file.endsWith('.js')?'text/javascript; charset=utf-8':file.endsWith('.svg')?'image/svg+xml':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; object-src 'none'"}})}if(!env.DB)fail(503,'数据库连接未就绪');if(path==='/api/health'&&req.method==='GET'){try{await env.DB.prepare('SELECT id FROM records LIMIT 1').first();await env.DB.prepare('SELECT email FROM members LIMIT 1').first();await env.DB.prepare('SELECT id FROM audit LIMIT 1').first();return j({database:'ready',files:env.BUCKET?'ready':'unavailable'})}catch(e){console.error('Storage health failed',e.message);return j({database:'migration_required',files:env.BUCKET?'ready':'unavailable'},503)}}if(req.method!=='GET'){if(req.headers.get('Origin')!==url.origin)fail(403,'请求来源无效');if(Number(req.headers.get('Content-Length')||0)>3100000)fail(413,'提交内容过大');if(!req.headers.get('Content-Type')?.startsWith('application/json'))fail(415,'仅支持 JSON 请求')}if(!req.headers.get('oai-authenticated-user-id'))fail(401,'请先登录');const db=env.DB,u=await identity(req,db);if(path==='/api/dictionaries'&&req.method==='GET')return j(await dictionaries(db));if(path==='/api/admin/dictionaries'&&req.method==='POST')return j(await saveDictionary(db,u,await req.json()));if(path==='/api/me'&&req.method==='GET')return j({user:u,permissions:PERMISSIONS,source:(await get(db,'setup-v2','meta'))});
 if(path==='/api/source/download'&&req.method==='GET'){if(u.roleId!=='admin')fail(403,'仅管理员可下载源码');const bytes=Uint8Array.from(atob(SOURCE_ARCHIVE),c=>c.charCodeAt(0));await audit(db,u,'下载网站源码','source-export');return new Response(bytes,{headers:{'Content-Type':'application/zip','Content-Disposition':'attachment; filename="data-navigator-source.zip"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}})}
 const archiveMatch=path.match(/^\/api\/(projects|resources)\/([^/]+)\/(archive|restore)$/);
 if(archiveMatch&&req.method==='POST'){const [,collection,id,operation]=archiveMatch,kind=collection==='projects'?'project':'resource';requireP(u,kind+'.archive');const item=await get(db,id,kind);if(!item)fail(404,'记录不存在');if(kind==='project'&&!canRead(u,item))fail(403,'无权访问项目');const b=await req.json();if(b._version!==item._version)fail(409,'记录已更新，请刷新');item.archivedAt=operation==='archive'?now():null;item.updatedAt=now();await change(db,kind,item,b._version);if(kind==='project')await rememberProject(db,item,b._version+1);await audit(db,u,(operation==='archive'?'归档':'恢复')+(kind==='project'?'项目':'资料'),id);return j({ok:true});}
 if(path==='/api/navigation'&&req.method==='GET')return j(await workspaceNavigation(db,u));
 if(path==='/api/admin/navigation'&&req.method==='POST')return j(await saveWorkspaceNavigation(db,u,await req.json()));
 if(path==='/api/workspace'&&req.method==='GET'){const ps=await all(db,'project'),names=await memberNames(db);return j({navigation:await workspaceNavigation(db,u),dictionaries:await dictionaries(db),projects:ps.filter(p=>canRead(u,p)).map(p=>redact(u,withMemberNames(p,names))),resources:has(u,'resource.read')?await all(db,'resource'):[],members:await assignmentMembers(db,u),roles:has(u,'role.manage')?await all(db,'role'):[]})}
 if(path==='/api/projects'&&req.method==='POST'){requireP(u,'project.create');const body=await req.json(),p={id:crypto.randomUUID(),name:body.name,customer:body.customer||body.name,type:body.type||'大数据',stage:0,bdId:u.id,saId:'',bdName:u.displayName||'',notes:'',pipelineDate:santiagoDate(),updatedAt:now(),repo:body.repo||'',actuals:[],logs:[],milestones:{},source:'网站新增',risk:false,status:'正常'};for(const k of biz)if(Object.hasOwn(body,k))p[k]=body[k];if(Object.hasOwn(body,'bdId')&&!has(u,'project.assign'))fail(403,'无权修改字段：bdId');if(has(u,'project.assign'))p.bdId=body.bdId||u.id;
 for(const [keys,permission]of [[tech.filter(k=>k!=='milestones'),'project.tech'],[finance,'finance.write']])for(const key of keys)if(Object.hasOwn(body,key)){if(!canWrite(u,p,permission))fail(403,'无权修改字段：'+key);p[key]=body[key]}
 if(Object.hasOwn(body,'milestones')){validateMilestones(u,p,body.milestones,true);p.milestones=body.milestones}
 await assignBD(db,p,null,body.bdName);
 if(!Object.hasOwn(body,'bdId')&&Object.hasOwn(body,'bdName'))setManualBDName(p,body.bdName);
 if(Object.hasOwn(body,'saId')||Object.hasOwn(body,'saIds'))await assignSA(db,u,p,saInput(body),null,p.saName);
 validateProject(p);validateProjectDictionaries(await dictionaries(db),p,undefined,await memberNames(db));await insert(db,'project',p);await rememberProject(db,p,1);await audit(db,u,'创建项目',p.id);return j(redact(u,{...p,_version:1}),201)}
 if(path.startsWith('/api/projects/')&&req.method==='PATCH'){const id=decodeURIComponent(path.split('/')[3]),p=await get(db,id,'project');if(!p)fail(404,'项目不存在');if(p.archivedAt)fail(409,'请先恢复项目再编辑');if(!canRead(u,p))fail(403,'没有项目访问权限');const body=await req.json(),previous=structuredClone(p);if(body._version!==p._version)fail(409,'请刷新获取最新项目版本');const allowed=new Set();if(canWrite(u,p,'project.biz'))biz.forEach(x=>allowed.add(x));if(canWrite(u,p,'project.tech'))tech.forEach(x=>allowed.add(x));if(canWrite(u,p,'finance.write'))finance.forEach(x=>allowed.add(x));if(has(u,'project.assign'))allowed.add('bdId');if(has(u,'project.assign')||canAssignOwnSA(u,p)){allowed.add('saId');allowed.add('saIds')}if(canWrite(u,p,'project.biz')||canWrite(u,p,'project.tech'))allowed.add('milestones');if(Object.hasOwn(body,'milestones'))validateMilestones(u,p,body.milestones);let changes=0;for(const[k,v]of Object.entries(body)){if(k==='_version'||k==='update')continue;if(!allowed.has(k))fail(403,'无权修改字段：'+k);p[k]=k==='milestones'?{...p.milestones,...v}:v;changes++}if(!changes&&!(body.update&&allowed.size))fail(403,'没有编辑权限');const automaticUpdate=!body.update&&changes>0;if(automaticUpdate){body.update='项目更新：'+Object.keys(body).filter(k=>k!=='_version').join('、')}if(body.update){if(typeof body.update!=='string'||body.update.length>10000)fail(400,'进展记录无效');p.logs??=[];p.logs.push({at:now(),text:body.update,by:u.email,byDisplayName:u.displayName||'',system:automaticUpdate})}if(Object.hasOwn(body,'bdId')){delete p.bdNameManual;await assignBD(db,p,previous,body.bdName&&body.bdName!==previous.bdName?body.bdName:'')}else if(Object.hasOwn(body,'bdName'))setManualBDName(p,body.bdName);if(Object.hasOwn(body,'saId')||Object.hasOwn(body,'saIds'))await assignSA(db,u,p,saInput(body),previous,body.saName&&body.saName!==previous.saName?body.saName:'');validateProject(p);validateProjectDictionaries(await dictionaries(db),p,previous,await memberNames(db));p.updatedAt=now();await change(db,'project',p,body._version);await rememberProject(db,p,body._version+1);await audit(db,u,'更新项目',id);return j(redact(u,{...p,_version:body._version+1}))}

 if(path==='/api/files'&&req.method==='POST'){requireP(u,'resource.write');if(!env.BUCKET)fail(503,'文件存储未就绪');const b=await req.json();validateDictionaryValue(await dictionaries(db),'type',b.type);if(typeof b.name!=='string'||b.name.length>200||! /\.(pdf|pptx?|docx?|xlsx?|txt|md)$/i.test(b.name))fail(400,'文件类型不受支持');if(typeof b.base64!=='string'||b.base64.length>2800000)fail(400,'文件不能超过 2MB');let bytes;try{bytes=Uint8Array.from(atob(b.base64),c=>c.charCodeAt(0))}catch{fail(400,'文件编码无效')}if(bytes.length>2097152)fail(400,'文件不能超过 2MB');const id=crypto.randomUUID(),key='resources/'+id;await env.BUCKET.put(key,bytes,{httpMetadata:{contentType:'application/octet-stream'}});const r={id,title:b.name,type:b.type,tag:'',body:'',fileKey:key,fileName:b.name,size:bytes.length,updatedAt:now()};try{await insert(db,'resource',r)}catch(e){await env.BUCKET.delete(key);throw e}await audit(db,u,'上传资料文件',id);return j({...r,_version:1},201)}
 if(path.startsWith('/api/files/')&&req.method==='GET'){requireP(u,'resource.read');const id=path.split('/')[3],r=await get(db,id,'resource');if(!r?.fileKey||r.archivedAt)fail(404,'文件不存在');const file=await env.BUCKET?.get(r.fileKey);if(!file)fail(404,'文件不存在');return new Response(file.body,{headers:{'Content-Type':'application/octet-stream','Content-Disposition':"attachment; filename*=UTF-8''"+encodeURIComponent(r.fileName),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}})}
 if(path==='/api/resources'&&req.method==='POST'){requireP(u,'resource.write');const b=await req.json();validateResource(b);validateDictionaryValue(await dictionaries(db),'type',b.type);if(typeof b.title!=='string'||!b.title.trim()||b.title.length>200)fail(400,'资料标题无效');if(b.url&&!/^https:\/\//.test(b.url))fail(400,'来源链接需为 HTTPS');const r={id:crypto.randomUUID(),title:b.title,type:b.type,body:b.body||'',url:b.url||'',tag:b.tag||'',updatedAt:now()};await insert(db,'resource',r);await audit(db,u,'新增资料',r.id);return j({...r,_version:1},201)}
 if(path.startsWith('/api/resources/')&&req.method==='PATCH'){requireP(u,'resource.write');const id=path.split('/')[3],old=await get(db,id,'resource');if(!old)fail(404,'资料不存在');if(old.archivedAt)fail(409,'请先恢复资料再编辑');const b=await req.json();validateResource(b);if(Object.hasOwn(b,'type'))validateDictionaryValue(await dictionaries(db),'type',b.type,old.type,true);if(b._version!==old._version)fail(409,'资料已更新，请刷新');if(b.url&&!/^https:\/\//.test(b.url))fail(400,'来源链接需为 HTTPS');const r={...old,title:String(b.title||old.title).slice(0,200),type:b.type||old.type,body:b.body||'',url:b.url||'',tag:b.tag||'',updatedAt:now()};await change(db,'resource',r,b._version);r._version=b._version+1;await audit(db,u,'更新资料',id);return j(reportForUser(u,r))}
 if(path==='/api/reports/template'&&req.method==='POST')return await reportTemplateResponse(db,u,await req.json());
 if(path==='/api/reports'&&req.method==='GET'){
  requireP(u,'report.view');
  const snapshots=(await all(db,'report')).filter(r=>reportAudience(u,r)).sort((a,b)=>b.generatedAt.localeCompare(a.generatedAt));
  const result=[],names=await memberNames(db);for(const r of snapshots)result.push(await visibleReport(db,u,{...r,publishedByName:r.publishedByName||names.get(r.publishedBy)||'',basis:'snapshot'}));
  return j(result);
 }
 if(path==='/api/reports/preview'&&req.method==='POST'){
  requireP(u,'report.view');return j(await visibleReport(db,u,await reportForPeriod(db,u,await req.json())));
 }
 if(path==='/api/reports'&&req.method==='POST'){
  requireP(u,'report.archive');requireP(u,'report.generate');requireP(u,'finance.read');
  if(!has(u,'project.read.all')&&!has(u,'project.read.own'))fail(403,'没有项目访问权限');
  if(env.STANDALONE)await db.prepare("SELECT id FROM records WHERE id='setup-v2' FOR UPDATE").first();
  const b=await req.json(),r=await reportForPeriod(db,u,b);
  if(r.basis==='snapshot')fail(409,'该范围已有归档快照，请查看已发布版本');
  reportTemplateEdits(b,r);r.dictionarySnapshot=await dictionaries(db);r.publishedBy=u.email;r.publishedByName=u.displayName||'';
  if(!has(u,'project.read.all'))r.scopeOwner=u.email;
  await insert(db,'report',r);await audit(db,u,'归档月报',r.id);
  return j(await visibleReport(db,u,{...r,_version:1,basis:'snapshot'}),201);
 }
 if(path.startsWith('/api/reports/')&&path.endsWith('/export')&&req.method==='GET'){
  requireP(u,'report.view');requireP(u,'report.export');const id=path.split('/')[3];
  const report=id==='current'?await reportForPeriod(db,u,Object.fromEntries(url.searchParams)):await get(db,id,'report');
  if(!report)fail(404,'报表不存在');
  return j(await visibleReport(db,u,id==='current'?report:{...report,basis:'snapshot'}));
 }
 if(path==='/api/admin'&&req.method==='GET'){
  if(!has(u,'member.manage')&&!has(u,'role.manage'))fail(403,'无权限');
  const counts=(await db.prepare('SELECT role_id,COUNT(*) AS total FROM members GROUP BY role_id').all()).results;
  const usage=new Map(counts.map(row=>[row.role_id,Number(row.total)]));
  return j({members:has(u,'member.manage')?(await db.prepare('SELECT email,user_id,role_id,enabled,version,display_name FROM members').all()).results:[],
   roles:(await all(db,'role')).map(role=>({...role,memberCount:usage.get(role.id)||0})),permissions:PERMISSIONS});
 }
 if(path==='/api/admin/member'&&req.method==='POST'){
  requireP(u,'member.manage');
  const b=await req.json(),email=String(b.email||'').trim().toLowerCase();
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>190)fail(400,'邮箱无效');
  if(email===env.ADMIN_EMAIL)fail(400,'初始管理员权限不可更改');
  if(env.STANDALONE)await db.prepare("SELECT id FROM records WHERE id=? AND kind='role' FOR UPDATE").bind(b.roleId).first();
  const role=await get(db,b.roleId,'role');
  if(!role)fail(400,'角色不存在');
  const member=await db.prepare('SELECT * FROM members WHERE email=?').bind(email).first();
  if(!member&&Object.hasOwn(b,'_version'))fail(404,'成员已删除，请刷新列表');
  if(member){
   const currentRole=await get(db,member.role_id,'role');
   if(currentRole?.permissions.some(p=>!has(u,p)))fail(403,'不能管理超出自身权限的成员');
   if(b._version!==member.version)fail(409,'成员已更新，请刷新');
  }
  if(role.permissions.some(p=>!has(u,p)))fail(403,'不能分配超出自身权限的角色');
  const displayName=Object.hasOwn(b,'displayName')?normalizeDisplayName(b.displayName):member?.display_name||'';
  if(member){
   const changed=await db.prepare('UPDATE members SET role_id=?,enabled=?,display_name=?,version=version+1 WHERE email=? AND version=?')
    .bind(b.roleId,b.enabled===false?0:1,displayName,email,b._version).run();
   if(changed.meta.changes!==1)fail(409,'成员已更新，请刷新');
  }else{
   const created=await db.prepare('INSERT OR IGNORE INTO members(email,user_id,role_id,enabled,display_name) VALUES(?,NULL,?,?,?)')
    .bind(email,b.roleId,b.enabled===false?0:1,displayName).run();
   if(created.meta.changes!==1)fail(409,'成员已更新，请刷新');
  }
  await audit(db,u,'更新成员资料与权限',email);return j({ok:true});
 }
 if(path==='/api/admin/role'&&req.method==='DELETE'){
  requireP(u,'role.manage');
  const body=await req.json();
  if(typeof body.id!=='string'||!body.id||body.id.length>190)fail(400,'角色不存在');
  if(env.STANDALONE)await db.prepare("SELECT id FROM records WHERE id=? AND kind='role' FOR UPDATE").bind(body.id).first();
  const role=await get(db,body.id,'role');
  if(!role)fail(404,'角色不存在，请刷新列表');
  if(role.builtin||DEFAULT_ROLES.some(item=>item.id===role.id))fail(400,'预置角色不可删除');
  if(role.permissions.some(permission=>!has(u,permission)))fail(403,'不能删除超出自身权限的角色');
  if(body._version!==role._version)fail(409,'角色已更新，请重新打开后确认');
  const assigned=await db.prepare('SELECT email FROM members WHERE role_id=? LIMIT 1').bind(role.id).first();
  if(assigned)fail(400,'该角色仍有成员使用，请先将成员分配到其他角色');
  const removed=await db.prepare("DELETE FROM records WHERE id=? AND kind='role' AND version=? AND NOT EXISTS(SELECT 1 FROM members WHERE role_id=?)")
   .bind(role.id,body._version,role.id).run();
  if(removed.meta.changes!==1)fail(409,'角色已更新，请重新打开后确认');
  await audit(db,u,'删除角色：'+role.name,role.id);
  return j({ok:true});
 }
 if(path==='/api/admin/role'&&req.method==='POST'){
  requireP(u,'role.manage');
  const b=await req.json(),id=b.id||crypto.randomUUID();
  if(typeof id!=='string'||id.length>190)fail(400,'角色不存在');
  if(env.STANDALONE&&b.id)await db.prepare("SELECT id FROM records WHERE id=? AND kind='role' FOR UPDATE").bind(id).first();
  const previous=await get(db,id,'role');
  if(b.id&&!previous)fail(404,'角色不存在，请刷新列表');
  if(previous&&previous.permissions.some(p=>!has(u,p)))fail(403,'不能修改超出自身权限的角色');
  if(id==='admin')fail(400,'内置管理员权限不可修改');
  if(typeof b.name!=='string'||!b.name.trim()||b.name.length>40)fail(400,'角色名称无效');
  if(!Array.isArray(b.permissions)||b.permissions.some(p=>!Object.hasOwn(PERMISSIONS,p)||!has(u,p)))fail(403,'权限选项无效或超出自身权限');
  const role={id,name:b.name,permissions:[...new Set(b.permissions)],builtin:previous?.builtin||false};
  if(previous)await change(db,'role',role,b._version);else await insert(db,'role',role);
  await audit(db,u,previous?'修改角色':'新增角色',id);
  return j(reportForUser(u,role));
 }
 if(path==='/api/audit'&&req.method==='GET'){requireP(u,'audit.view');return j((await db.prepare('SELECT a.*,m.display_name AS actorDisplayName FROM audit a LEFT JOIN members m ON m.email=a.actor ORDER BY a.at DESC LIMIT 100').all()).results)}
 return j({error:'接口不存在'},404);
 }catch(e){if(!e.status)throw e;return j({error:e.status?e.message:'服务暂时不可用，请稍后重试'},e.status||500)}}};
