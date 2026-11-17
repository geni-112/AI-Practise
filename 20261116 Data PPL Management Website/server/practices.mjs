import {createContentTranslations} from './content-translations.mjs';
import {projectSAIds,owns} from '../dist/server/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomBytes,randomUUID,createHash,createCipheriv,createDecipheriv} from 'node:crypto';
import {transaction} from './database.mjs';
import {authError} from './auth.mjs';
import {SERVICE_CATALOG} from './architecture-catalog.mjs';
import {normalizeEndpoint,validateImage,analysisMessages,callModel,parseModelJSON,validateAnalysis,visionProbe,DEFAULT_ANALYSIS_MINUTES} from './architecture-model.mjs';

import {recognizeDiagram,textProbe,verifyFlowDirections,OCR_TIMEOUT_MS} from './architecture-ocr.mjs';
import {caseDetails,mappingCandidates,readPracticeInput,referenceLibrary,publicCase,relevantCases,saveReference} from './architecture-memory.mjs';
import {drawingRoute,drawingVersions} from './architecture-drawing.mjs';
import {otherLanguage,resultLanguage,translationsFor,queueTranslation,runNextTranslation} from './architecture-languages.mjs';

const json=(v,status=200)=>new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json; charset=utf-8'}});
const uuid=v=>typeof v==='string'&&/^[a-f0-9-]{36}$/.test(v);
const need=(user,p)=>{if(!user?.permissions.includes(p))throw authError(403,'当前角色没有此操作权限')};
const admin=user=>{if(user?.roleId!=='admin')throw authError(403,'仅管理员可配置 MaaS')};
const text=(v,max,required=false)=>{if(typeof v!=='string'||v.length>max||(required&&!v.trim()))throw authError(400,'最佳实践字段格式无效');return v.trim()};
// Unlinked analyses are private to their creator. Project-linked originals follow
// the current project assignment on every request, including image and drawing downloads.
const analysisJoin = ' FROM architecture_analyses a LEFT JOIN members owner ON owner.email=a.owner_email LEFT JOIN architecture_project_links l ON l.analysis_id=a.id LEFT JOIN records p ON p.id=l.project_id AND p.kind=\'project\' ';
const saArray="CASE WHEN JSON_TYPE(JSON_EXTRACT(p.payload,'$.saIds'))='ARRAY' THEN JSON_EXTRACT(p.payload,'$.saIds') ELSE JSON_ARRAY(JSON_UNQUOTE(JSON_EXTRACT(p.payload,'$.saId'))) END";
const assignedProjectMember="(JSON_UNQUOTE(JSON_EXTRACT(p.payload,'$.bdId')) IN (?,?) OR JSON_CONTAINS("+saArray+",JSON_QUOTE(?)) OR JSON_CONTAINS("+saArray+",JSON_QUOTE(?)))";
function originalAccess(user) {
  if(user.roleId==='admin')return {sql:'1=1',args:[]};
  const canRead=user.permissions.includes('practice.read'),manager=user.permissions.includes('practice.manage');
  const privateOwner=canRead&&!manager;
  const unlinked=!canRead?'0=1':manager?'l.analysis_id IS NULL':'(l.analysis_id IS NULL AND a.owner_email=?)';
  return {sql:'('+unlinked+' OR (l.analysis_id IS NOT NULL AND '+assignedProjectMember+'))',
    args:[...(privateOwner?[user.email]:[]),user.id,user.email,user.id,user.email]};
}
async function validatePracticeProject(client,user,id) {
  if (id==null || id==='') return null;
  if (typeof id!=='string' || id.length>190) throw authError(400,'关联项目无效');
  const record=(await client.query("SELECT payload FROM records WHERE id=? AND kind='project' FOR UPDATE",[id])).rows[0];
  const project=record&&JSON.parse(record.payload);
  const collaborator=project&&owns(user,project);
  const allowed=user.roleId==='admin' || collaborator&&user.permissions.some(p=>p==='project.read.own'||p==='project.read.all');
  if (!project || project.archivedAt || !allowed) throw authError(403,'请选择你负责的有效项目');
  return id;
}
const messages={
 TRANSLATION_INVALID:'模型未返回完整译文，可重试翻译。',
 OCR_NO_TEXT:'未识别到可读文字，请上传更清晰或带组件名称的架构图',OCR_UNAVAILABLE:'云端 OCR 服务暂不可用，请稍后重试',OCR_BUSY:'云端 OCR 服务正忙，请稍后重试',OCR_TIMEOUT:'文字识别超时，请裁剪或缩小图片后重试',TEXT_TEST_FAILED:'文本模型未通过连接测试，请确认模型名称和调用地址',
 INVALID_ENDPOINT:'请填写华为云 MaaS 的 HTTPS Chat Completions 地址',INVALID_IMAGE:'请上传清晰的 PNG、JPEG 或 WebP 图片，大小不超过 2MB',
 MAAS_AUTH:'MaaS 密钥无效或没有此模型的调用权限',MAAS_RATE_LIMIT:'MaaS 调用限流或额度不足，请稍后重试',MAAS_TIMEOUT:'已达到平台设置的 MaaS 分析时限，未收到完整结果。',MAAS_UPSTREAM_TIMEOUT:'MaaS 网关返回超时，请稍后重试。',MAAS_CONNECTION_TIMEOUT:'等待 MaaS 网络连接或响应超时，请稍后重试。',MAAS_STREAM_INTERRUPTED:'MaaS 响应在完成前断开，请稍后重试。',MAAS_MODEL:'模型调用参数不兼容，请检查模型名称和输入模式',MAAS_UNAVAILABLE:'暂时无法连接 MaaS，请检查服务配置后重试',
 INVALID_MODEL_RESPONSE:'模型未返回完整的结构化分析，请重试或更换模型',MODEL_OUTPUT_TRUNCATED:'模型输出被截断，请管理员提高输出上限后重试',VISION_NOT_SUPPORTED:'图片识别测试未通过，请选择支持图片理解的模型',SERVICE_NOT_CONFIGURED:'管理员尚未完成架构分析服务配置',ANALYSIS_INTERRUPTED:'分析任务中断，请手动重试',ANALYSIS_INTERNAL_ERROR:'平台处理架构图时出现错误，请查看失败阶段后重试。',ACCESS_REVOKED:'发起人的账号或分析权限已变更',DAILY_LIMIT:'今日分析次数已达上限，请明天再试或联系管理员'
};
export const practiceError=code=>Object.assign(authError(400,messages[code]||messages.MAAS_UNAVAILABLE),{modelCode:code});
async function audit(c,user,action,entity){await c.query('INSERT INTO audit(id,actor,action,entity,at) VALUES($1,$2,$3,$4,$5)',[randomUUID(),user.email,action,entity,new Date().toISOString()])}
const validationNotes = {"invalid_json":"模型回答不是完整的 JSON 对象。","missing":"模型没有返回此必填字段。","type":"模型返回的字段类型与要求不符。","array_limit":"此列表的项目数超过上限。","text_limit":"此字段的文字超过长度上限。","enum":"此字段的取值不在允许范围内。","identifier":"节点或组件标识格式有误。","catalog":"建议服务不在平台的华为云服务目录中。","duplicate":"架构中出现了重复的节点标识。","reference":"此处引用的节点或组件不存在。"};
async function recordFailure(client, id, {stage, timeoutSeconds=null, modelMs=null, evidence=null, httpStatus=null, requestId=null, validationPath=null, validationIssue=null}) {
 await client.query(`INSERT INTO architecture_failures
  (analysis_id,failure_version,started_at,failed_at,stage,error_code,model,timeout_seconds,model_elapsed_ms,ocr_labels,ocr_connections,http_status,provider_request_id)
  SELECT id,version,started_at,updated_at,?,error_code,model,?,?,?,?,?,?
  FROM architecture_analyses WHERE id=? AND status='failed'`,
  [stage,timeoutSeconds,modelMs,evidence?.labels.length ?? null,evidence?.connections.length ?? null,httpStatus,requestId,id]);
 if(validationPath && Object.hasOwn(validationNotes,validationIssue)) {
  await client.query(`INSERT INTO architecture_failure_fields(analysis_id,failure_version,field_path,issue)
   SELECT id,version,?,? FROM architecture_analyses WHERE id=? AND status='failed'`,[validationPath,validationIssue,id]);
 }
}

async function failureLogs(client, id) {
 const {rows}=await client.query(`SELECT failed_at,stage,error_code,model,timeout_seconds,model_elapsed_ms,
  TIMESTAMPDIFF(SECOND,started_at,failed_at) AS elapsed_seconds,ocr_labels,ocr_connections,http_status,provider_request_id,
  f.field_path AS validation_path,f.issue AS validation_issue
  FROM architecture_failures a LEFT JOIN architecture_failure_fields f USING(analysis_id,failure_version)
  WHERE a.analysis_id=? ORDER BY a.failure_version DESC`,[id]);
 const translationErrors=(await client.query(`SELECT failed_at,'translation' AS stage,language,error_code,model,timeout_seconds,http_status,provider_request_id,
  TIMESTAMPDIFF(SECOND,started_at,failed_at) AS elapsed_seconds FROM architecture_translation_errors WHERE analysis_id=? ORDER BY id DESC`,[id])).rows;
 return [...rows,...translationErrors].sort((a,b)=>String(b.failed_at).localeCompare(String(a.failed_at))).map(row=>({...row,validationNote:validationNotes[row.validation_issue]||null,message:messages[row.error_code] || messages.MAAS_UNAVAILABLE}));
}

export async function initializePracticeRoles(c){
 const lock=(await c.query("SELECT payload FROM records WHERE id='setup-v2' FOR UPDATE")).rows[0];if(!lock)return;
 if((await c.query("SELECT id FROM records WHERE id='best-practices-v1'")).rows[0])return;
 for(const roleId of ['admin','bd','sa']){
  const r=(await c.query('SELECT payload FROM records WHERE id=$1 FOR UPDATE',[roleId])).rows[0];if(!r)continue;const role=JSON.parse(r.payload);
  role.permissions=[...new Set([...role.permissions,'practice.read','practice.analyze',...(roleId==='admin'?['practice.manage']:[])])];
  await c.query('UPDATE records SET payload=$1,version=version+1 WHERE id=$2',[JSON.stringify(role),roleId]);
 }
 await c.query("INSERT INTO records(id,kind,payload) VALUES('best-practices-v1','meta','{}')");
}
export async function createPracticeService({pool,files,env,editorOrigin,fetchImpl=fetch,probeFactory=visionProbe}){
 const keyDir=env.MAAS_KEY_DIR||path.join(path.dirname(env.UPLOAD_DIR||'.data/uploads'),'private');
 await fs.mkdir(keyDir,{recursive:true,mode:0o700});const keyFile=path.join(keyDir,'maas.key');
 try{const f=await fs.open(keyFile,'wx',0o600);try{await f.writeFile(randomBytes(32));await f.sync()}finally{await f.close()}}catch(e){if(e.code!=='EEXIST')throw e}
 const key=await fs.readFile(keyFile);if(key.length!==32)throw new Error('Invalid MaaS encryption key');
 const encrypt=value=>{const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv);const encrypted=Buffer.concat([cipher.update(value,'utf8'),cipher.final()]);return [iv,cipher.getAuthTag(),encrypted].map(b=>b.toString('base64')).join('.')};
 const decrypt=value=>{try{const[iv,tag,data]=value.split('.').map(x=>Buffer.from(x,'base64')),cipher=createDecipheriv('aes-256-gcm',key,iv);cipher.setAuthTag(tag);return Buffer.concat([cipher.update(data),cipher.final()]).toString('utf8')}catch{throw practiceError('MAAS_AUTH')}};
 async function config(c,lock=false){const row=(await c.query("SELECT payload,version FROM integration_settings WHERE id='maas'"+(lock?' FOR UPDATE':''))).rows[0];if(row){const value=JSON.parse(row.payload);return {analysisTimeoutMinutes:DEFAULT_ANALYSIS_MINUTES,...value,inputMode:value.inputMode||(value.tested?'vision':'ocr'),_version:row.version}}return {inputMode:'ocr',endpoint:'',model:'',region:'',enabled:false,tested:false,maxTokens:8192,dailyLimit:30,analysisTimeoutMinutes:DEFAULT_ANALYSIS_MINUTES,_version:0}}
 const ready=c=>!!(c.enabled&&c.tested&&c.secret&&c.endpoint&&c.model);
 const safe=c=>{const {secret,...rest}=c;return {...rest,apiKeySet:!!secret,ready:ready(c)}};
 async function save(c,value,version){const body={...value};delete body._version;
  if(version===0)await c.query("INSERT INTO integration_settings(id,payload) VALUES('maas',$1)",[JSON.stringify(body)]);
  else if((await c.query("UPDATE integration_settings SET payload=$1,version=version+1 WHERE id='maas' AND version=$2",[JSON.stringify(body),version])).rowCount!==1)throw authError(409,'MaaS 配置已更新，请重新打开');
  return {...body,_version:version+1};
 }
 async function budget(c,cfg,user,purpose,analysisId=null){
  const counts=(await c.query("SELECT COUNT(*) AS total,SUM(owner_email=$1) AS own FROM architecture_usage WHERE created_at>=CURRENT_DATE()",[user.email])).rows[0];
  if(Number(counts.total)>=cfg.dailyLimit||Number(counts.own)>=Math.min(cfg.dailyLimit,10))throw practiceError('DAILY_LIMIT');
  await c.query('INSERT INTO architecture_usage(id,owner_email,analysis_id,purpose) VALUES($1,$2,$3,$4)',[randomUUID(),user.email,analysisId,purpose]);
 }
 const projectUpload=row=>row.image_key?.startsWith('project-diagram/')===true;
 const view=row=>({...row,projectSubmission:projectUpload(row),result:row.result_json?JSON.parse(row.result_json):null,usage:row.usage_json?JSON.parse(row.usage_json):null,result_json:undefined,usage_json:undefined,image_key:undefined,errorMessage:row.error_code?messages[row.error_code]||messages.MAAS_UNAVAILABLE:null});
 async function accessible(c,id,user,lock=false){
  const access=originalAccess(user);
  const row=(await c.query("SELECT a.*,owner.display_name AS ownerDisplayName,l.project_id,p.payload AS assigned_project"+analysisJoin+'WHERE a.id=? AND '+access.sql+(lock?' FOR UPDATE':''),[id,...access.args])).rows[0];
  if(!row)return null;
  const {assigned_project,...item}=row;
  const technicalOwner=assigned_project&&projectSAIds(JSON.parse(assigned_project)).some(id=>[user.id,user.email].includes(id));
  const ownsManual=!projectUpload(row)&&row.owner_email===user.email;
  item.canMaintain=user.permissions.includes('practice.analyze')&&(user.roleId==='admin'||technicalOwner||ownsManual||(!row.project_id&&user.permissions.includes('practice.manage')));
  return item;
 }
 async function get(c,id,user,lock=false){
  const row=uuid(id)&&await accessible(c,id,user,lock);
  if(!row)throw authError(404,'架构分析不存在');
  return row;
 }
 async function submissionResponse(c,id,user,status=200){
  const row=await accessible(c,id,user);
  return json(row?view(row):{submitted:true},status);
 }
 async function originalImage(c,row){
  if(!projectUpload(row))return files.get(row.image_key);
  const original=(await c.query('SELECT original_image FROM project_diagram_submissions WHERE analysis_id=?',[row.id])).rows[0];
  return original?{body:original.original_image}:null;
 }
 async function enqueue(c,user,cfg,input,bytes,projectId,requestDigest=null){
  const count=(await c.query("SELECT COUNT(*) AS n FROM architecture_analyses WHERE status IN ('queued','running') AND archived_at IS NULL")).rows[0];
  if(Number(count.n)>=10)throw authError(429,'分析队列已满，请稍后提交');
  const id=randomUUID(),key=requestDigest?'project-diagram/'+id:'resources/'+randomUUID();
  await budget(c,cfg,user,'analysis',id);
  if(!requestDigest)await files.put(key,bytes);
  try{
   await c.query("INSERT INTO architecture_analyses(id,owner_email,request_key,title,business_type,context_text,target_region,language,image_key,image_name,image_mime,image_size,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'queued')",
    [id,user.email,input.requestKey,input.title,input.businessType,input.context,input.targetRegion,input.language,key,input.name,input.mime,bytes.length]);
   await c.query('INSERT INTO architecture_inputs(analysis_id,input_mode,image_digest,reference_requested) VALUES(?,?,?,?)',[id,cfg.inputMode,createHash('sha256').update(bytes).digest('hex'),!projectId&&input.referenceRequested?1:0]);
   if(projectId)await c.query('INSERT INTO architecture_project_links(analysis_id,project_id) VALUES(?,?)',[id,projectId]);
   if(requestDigest)await c.query('INSERT INTO project_diagram_submissions(analysis_id,request_digest,original_image) VALUES(?,?,?)',[id,requestDigest,bytes]);
   await audit(c,user,'提交架构图分析',id);
  }catch(error){if(!requestDigest)await files.delete(key);throw error}
  return id;
 }
 async function createProjectWithDiagram(c,user,body,createProject){
  need(user,'project.create');
  const {architectureDiagram:diagram,...fields}=body;
  if(!diagram||!uuid(diagram.requestKey)||!['zh','en'].includes(diagram.language))throw authError(400,'项目架构图提交信息无效');
  const name=text(diagram.name,200,true);
  try{
   const bytes=validateImage(diagram.base64,diagram.mime);
   const canonical=JSON.stringify([fields,name,diagram.mime,diagram.language],(_key,value)=>{
    if(!value||typeof value!=='object'||Array.isArray(value))return value;
    return Object.fromEntries(Object.keys(value).sort().map(key=>[key,value[key]]));
   });
   const digest=createHash('sha256').update(canonical).update(bytes).digest('hex');
   // Serialize retries from the same creator before the project or its history is written.
   await c.query('SELECT email FROM members WHERE email=? FOR UPDATE',[user.email]);
   const old=(await c.query(`SELECT l.project_id,s.request_digest FROM architecture_analyses a
    LEFT JOIN architecture_project_links l ON l.analysis_id=a.id LEFT JOIN project_diagram_submissions s ON s.analysis_id=a.id
    WHERE a.owner_email=? AND a.request_key=?`,[user.email,diagram.requestKey])).rows[0];
   if(old){
    if(old.request_digest!==digest||!old.project_id)throw authError(409,'此提交已保存，输入内容与上次不同');
    return json({id:old.project_id,architectureSubmitted:true});
   }
   const created=await createProject(fields);
   if(!created.ok)return created;
   const project=await created.json(),cfg=await config(c,true);
   const input={requestKey:diagram.requestKey,title:project.name,businessType:['大数据','数据库'].includes(project.type)?project.type:'综合架构',
    targetRegion:'',language:diagram.language,context:'',name,mime:diagram.mime};
   await enqueue(c,user,cfg,input,bytes,project.id,digest);
   return json({id:project.id,architectureSubmitted:true},201);
  }catch(error){if(error.modelCode)throw practiceError(error.modelCode);throw error}
 }
 const contentTranslations=createContentTranslations({pool,config,ready,translate:(cfg,messages)=>callModel({...cfg,apiKey:decrypt(cfg.secret)},messages,{fetchImpl,stream:true})});
 async function route(c,request,user){
  const translated=await contentTranslations.route(c,request,user);if(translated)return translated;
  const url=new URL(request.url),p=url.pathname;
  if(p==='/api/audit'&&request.method==='GET'&&user?.roleId!=='admin'){
   need(user,'audit.view');
   const entries=await c.query("SELECT e.* FROM audit e LEFT JOIN architecture_project_links l ON l.analysis_id=e.entity LEFT JOIN records p ON p.id=l.project_id AND p.kind='project' WHERE l.analysis_id IS NULL OR "+assignedProjectMember+" ORDER BY e.at DESC LIMIT 100",[user.id,user.email,user.id,user.email]);
   return json(entries.rows);
  }
  if(!p.startsWith('/api/practices'))return null;
  if(!user)throw authError(401,'请先登录');
  try{
   if(p==='/api/practices/config'){
    admin(user);if(request.method==='GET')return json(safe(await config(c)));
    if(request.method!=='POST')return json({error:'请使用 POST'},405);
    const b=await request.json(),old=await config(c,true);if(b._version!==old._version)throw authError(409,'MaaS 配置已更新，请重新打开');
    const endpoint=normalizeEndpoint(b.endpoint),model=text(b.model,200,true),region=text(b.region||'',120),apiKey=text(b.apiKey||'',4096);
    if(/[\r\n\x00-\x1f]/.test(apiKey)||(!apiKey&&!old.secret))throw authError(400,'请填写 MaaS API Key');
    if(!Number.isInteger(b.maxTokens)||b.maxTokens<2048||b.maxTokens>32768||!Number.isInteger(b.dailyLimit)||b.dailyLimit<1||b.dailyLimit>500||typeof b.enabled!=='boolean')throw authError(400,'MaaS 调用上限无效');
    const analysisTimeoutMinutes=b.analysisTimeoutMinutes===undefined?old.analysisTimeoutMinutes:b.analysisTimeoutMinutes;
    if(!Number.isInteger(analysisTimeoutMinutes)||analysisTimeoutMinutes<1||analysisTimeoutMinutes>30)throw authError(400,'MaaS 分析时限必须为 1 至 30 分钟的整数');
    const inputMode=b.inputMode??old.inputMode;
    if(!['ocr','vision'].includes(inputMode))throw authError(400,'请选择识别模式');
    const changed=inputMode!==old.inputMode||endpoint!==old.endpoint||model!==old.model||!!apiKey;
    const value={endpoint,model,region,inputMode,enabled:b.enabled,secret:apiKey?encrypt(apiKey):old.secret,maxTokens:b.maxTokens,dailyLimit:b.dailyLimit,analysisTimeoutMinutes,tested:changed?false:old.tested,testedAt:changed?null:old.testedAt,testError:changed?null:old.testError};
    const saved=await save(c,value,old._version);await audit(c,user,'配置架构分析 MaaS','maas');return json(safe(saved));
   }
   if(p==='/api/practices/test'&&request.method==='POST'){
    admin(user);const cfg=await config(c,true);if(!cfg.secret||!cfg.endpoint||!cfg.model)throw practiceError('SERVICE_NOT_CONFIGURED');await budget(c,cfg,user,'connection-test');
    // The HTTP boundary executes this only after releasing its SQL transaction.
    return {afterCommit:async()=>{
     let code=null;
     try{const probe=cfg.inputMode==='ocr'?await textProbe(env):probeFactory(),r=await callModel({...cfg,apiKey:decrypt(cfg.secret)},probe.messages,{fetchImpl,maxTokens:2048,timeoutMs:60000});if(parseModelJSON(r.content).code!==probe.code)code=cfg.inputMode==='ocr'?'TEXT_TEST_FAILED':'VISION_NOT_SUPPORTED'}catch(e){code=e.modelCode||'MAAS_UNAVAILABLE'}
     const saved=await transaction(pool,async db=>{const current=await config(db,true);if(current._version!==cfg._version)throw authError(409,'MaaS 配置已更新，请重新打开');const next=await save(db,{...current,tested:!code,testError:code,testedAt:new Date().toISOString()},current._version);await audit(db,user,'测试架构分析服务','maas');return next});
     return json({...safe(saved),message:code?messages[code]:'架构分析服务已就绪，可上传架构图',...(code?{error:messages[code]}:{})},code?400:200);
    }};
   }
   const recordRoute=p.match(/^\/api\/practices\/([a-f0-9-]{36})(?:\/(image|retry|archive|restore|project|reference|failures|translation|drawing(?:\/preview)?))?$/);
   const projectList=p==='/api/practices'&&request.method==='GET'&&url.searchParams.get('projectId');
   if(user.roleId!=='admin'&&!projectList&&!recordRoute)need(user,'practice.read');
   const published=p.match(/^\/api\/practices\/references\/([a-f0-9-]{36})$/);
   if(published && request.method==='GET')return json(await publicCase(c,published[1]));
   if(p==='/api/practices/references'&&request.method==='GET')return json(await referenceLibrary(c,url));
   if(p==='/api/practices'&&request.method==='GET'){
    const cfg=await config(c),archived=url.searchParams.get('archived')==='true',page=Math.max(1,Math.min(10000,Number(url.searchParams.get('page'))||1));
    const access=originalAccess(user),projectId=url.searchParams.get('projectId');
    const condition=analysisJoin+'WHERE '+access.sql+(archived?'':' AND a.archived_at IS NULL')+(projectId?' AND l.project_id=?':'');
    const args=projectId?[...access.args,projectId]:access.args,total=Number((await c.query('SELECT COUNT(*) AS n'+condition,args)).rows[0].n);
    const list=(await c.query('SELECT a.id,a.title,a.business_type,a.owner_email,owner.display_name AS ownerDisplayName,a.language,a.target_region,a.status,a.error_code,a.model,a.created_at,a.updated_at,a.archived_at,a.version,a.image_key,l.project_id'+condition+' ORDER BY a.created_at DESC,a.id LIMIT 30 OFFSET '+((Math.floor(page)-1)*30),args)).rows;
    return json({items:list.map(view),total,page:Math.floor(page),service:{ready:ready(cfg),inputMode:cfg.inputMode,model:cfg.model,region:cfg.region},catalog:SERVICE_CATALOG});
   }
   if(p==='/api/practices'&&request.method==='POST'){
    need(user,'practice.analyze');const b=await request.json();if(!uuid(b.requestKey))throw authError(400,'最佳实践字段格式无效');
    const duplicate=(await c.query('SELECT id FROM architecture_analyses WHERE owner_email=$1 AND request_key=$2',[user.email,b.requestKey])).rows[0];if(duplicate)return submissionResponse(c,duplicate.id,user);
    const projectId=await validatePracticeProject(c,user,b.projectId);
    const cfg=await config(c,true);if(!ready(cfg))throw practiceError('SERVICE_NOT_CONFIGURED');
    if(b.inputMode!=null&&b.inputMode!==cfg.inputMode)throw authError(409,'识别模式已改变，请重新打开上传窗口');
    if(b.referenceRequested!=null&&typeof b.referenceRequested!=='boolean')throw authError(400,'参考案例内容无效');
    const title=text(b.title,200,true),context=text(b.context||'',8000),targetRegion='',name=text(b.name,200,true);
    if(!['大数据','数据库','综合架构'].includes(b.businessType)||!['zh','en'].includes(b.language))throw authError(400,'最佳实践字段格式无效');
    const bytes=validateImage(b.base64,b.mime);
    const id=await enqueue(c,user,cfg,{...b,title,context,targetRegion,name},bytes,projectId);
    return submissionResponse(c,id,user,202);
   }
   const match=recordRoute;
   if(!match)return json({error:'接口不存在'},404);const [,id,operation]=match,row=await get(c,id,user,request.method==='POST');
   if(!operation&&request.method==='GET'){
    const item=view(row),language=resultLanguage(url.searchParams.get('lang'),row.language);
    const translations=await translationsFor(c,id),versions=await drawingVersions(c,id);
    for(const tr of Object.values(translations))tr.errorMessage=tr.errorCode?messages[tr.errorCode]||messages.TRANSLATION_INVALID:null;
    const target=translations[language];
    return json({...item,...await caseDetails(c,row),sourceLanguage:row.language,language,translations,drawingVersions:versions,
     result:language===row.language?item.result:target?.result??null,drawingVersion:versions[language],
     referenceCandidates:item.result?mappingCandidates(item.result):[],catalog:SERVICE_CATALOG});
   }
   if(operation==='failures'){
    if(request.method!=='GET')return json({error:'请使用 GET'},405);
    return json({items:await failureLogs(c,id)});
   }
   if(operation==='drawing'||operation==='drawing/preview'){
    const response=await drawingRoute(c,request,user,row,operation,url,editorOrigin);
    if(request.method==='POST')await audit(c,user,'保存华为云目标架构图',id);
    return response;
   }
   if(operation==='image'&&request.method==='GET'){
    const image=await originalImage(c,row);if(!image)throw authError(404,'文件不存在');
    return new Response(image.body,{headers:{'Content-Type':row.image_mime,'Content-Disposition':'inline','X-Content-Type-Options':'nosniff'}});
   }
   if(request.method!=='POST')return json({error:'请使用 POST'},405);
   if(!row.canMaintain)throw authError(403,'当前账号仅可查看此分析');
   const b=await request.json();if(b._version!==row.version)throw authError(409,'架构分析已更新，请刷新');
   if(operation==='translation'){
    const language=resultLanguage(b.language,otherLanguage(row.language));
    if(row.status!=='succeeded'||(row.archived_at&&!projectUpload(row))||language===row.language)throw authError(409,'此语言版本无法重试');
    const updated=await c.query("UPDATE architecture_translations SET status='queued',available_at=NOW(),failures=0,error_code=NULL WHERE analysis_id=? AND language=? AND status='failed'",[id,language]);
    if(!updated.rowCount)throw authError(409,'此语言版本无法重试');
    await audit(c,user,'重试架构分析翻译',id);
   }else if(operation==='project'){
    if(row.archived_at||['queued','running'].includes(row.status))throw authError(409,'请等待分析结束并恢复归档记录');
    if(row.project_id&&(projectUpload(row)||user.roleId!=='admin'||!b.projectId))throw authError(403,'项目架构图须保留项目关联');
    const projectId=await validatePracticeProject(c,user,b.projectId);
    if(!projectId && row.owner_email!==user.email && !user.permissions.includes('practice.manage'))throw authError(403,'当前角色没有此操作权限');
    if((await c.query('UPDATE architecture_analyses SET version=version+1 WHERE id=? AND version=?',[id,row.version])).rowCount!==1)throw authError(409,'架构分析已更新，请刷新');
    if(projectId)await c.query('INSERT INTO architecture_project_links(analysis_id,project_id) VALUES(?,?) ON DUPLICATE KEY UPDATE project_id=VALUES(project_id)',[id,projectId]);
    else await c.query('DELETE FROM architecture_project_links WHERE analysis_id=?',[id]);
    await audit(c,user,'更新架构图项目权限',id);
   }else if(operation==='reference'){
    await saveReference(c,user,row,b,files);await audit(c,user,b.publish?'收录参考案例':'撤下参考案例',id);
   }else if(operation==='retry'){
    if(row.archived_at||row.status!=='failed')throw authError(409,'仅失败且未归档的分析可以重试');const cfg=await config(c,true);if(!ready(cfg))throw practiceError('SERVICE_NOT_CONFIGURED');
    await budget(c,cfg,user,'retry',id);
    const updated=await c.query("UPDATE architecture_analyses SET status='queued',error_code=NULL,started_at=NULL,lease_until=NULL,updated_at=now(),version=version+1 WHERE id=$1 AND version=$2",[id,row.version]);if(updated.rowCount!==1)throw authError(409,'架构分析已更新，请刷新');await audit(c,user,'重试架构图分析',id);
   }else if(['archive','restore'].includes(operation)){
    if(['queued','running'].includes(row.status))throw authError(409,'请等待分析结束后归档');
    const updated=await c.query('UPDATE architecture_analyses SET archived_at=$1,updated_at=now(),version=version+1 WHERE id=$2 AND version=$3',[operation==='archive'?new Date().toISOString().slice(0,19).replace('T',' '):null,id,row.version]);if(updated.rowCount!==1)throw authError(409,'架构分析已更新，请刷新');await audit(c,user,operation==='archive'?'归档架构分析':'恢复架构分析',id);
   }else return json({error:'接口不存在'},404);
   return submissionResponse(c,id,user);
  }catch(e){if(e.modelCode)throw practiceError(e.modelCode);throw e}
 }
 let timer=null,active=null,stopped=true;
 async function runNext(){
  const job=await transaction(pool,async c=>{
   const expired=(await c.query("SELECT id FROM architecture_analyses WHERE status='running' AND lease_until<now() FOR UPDATE")).rows;
   for(const row of expired){
    await c.query("UPDATE architecture_analyses SET status='failed',error_code='ANALYSIS_INTERRUPTED',lease_until=NULL,version=version+1,updated_at=now() WHERE id=?",[row.id]);
    await recordFailure(c,row.id,{stage:'worker'});
   }
   const cfg=await config(c,true);if(!ready(cfg))return null;
   // One application worker, with a DB lock to keep deployment overlaps safe.
   if((await c.query("SELECT id FROM architecture_analyses WHERE status='running' AND lease_until>=now() LIMIT 1")).rows.length)return null;
   const row=(await c.query("SELECT * FROM architecture_analyses WHERE status='queued' AND archived_at IS NULL ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED")).rows[0];if(!row)return null;
   const owner=(await c.query('SELECT m.enabled,r.payload FROM members m JOIN records r ON r.id=m.role_id WHERE m.email=$1',[row.owner_email])).rows[0];
   if(!projectUpload(row)&&(!owner?.enabled||!JSON.parse(owner.payload).permissions.includes('practice.analyze'))){await c.query("UPDATE architecture_analyses SET status='failed',error_code='ACCESS_REVOKED',updated_at=now(),version=version+1 WHERE id=$1",[row.id]);await recordFailure(c,row.id,{stage:'worker'});return null}
   const leaseSeconds=cfg.analysisTimeoutMinutes*60+Math.ceil(OCR_TIMEOUT_MS/1000)+60;
   await c.query("UPDATE architecture_analyses SET status='running',started_at=now(),lease_until=TIMESTAMPADD(SECOND,?,now()),model=?,version=version+1,updated_at=now() WHERE id=?",[leaseSeconds,cfg.model,row.id]);
   const input=await readPracticeInput(c,row.id);
   const inputMode=projectUpload(row)?cfg.inputMode:input.inputMode==='ocr'||cfg.inputMode==='ocr'?'ocr':'vision';
   await c.query('INSERT INTO architecture_inputs(analysis_id,input_mode) VALUES(?,?) ON DUPLICATE KEY UPDATE input_mode=VALUES(input_mode)',[row.id,inputMode]);
   return {...row,cfg,inputMode,runVersion:row.version+1};
  });
  if(!job)return false;
  let result=null,usage=null,code=null,evidence=null,sources=[];
  let stage='image',modelStart=null,modelMs=null,failure=null;
  try{
   const stored=await transaction(pool,c=>originalImage(c,job));
   if(!stored)throw practiceError('INVALID_IMAGE');
   const bytes=Buffer.from(await new Response(stored.body).arrayBuffer());
   if(job.inputMode==='ocr'){
    stage='ocr';
    evidence=await recognizeDiagram(bytes,env);
    if(!evidence.labels.some(l=>l.text.trim().length>=2))throw practiceError('OCR_NO_TEXT');
   }
   stage='references';
   const digest=createHash('sha256').update(bytes).digest('hex');
   const cases=await transaction(pool,c=>relevantCases(c,job,evidence,digest));
   const messages=analysisMessages(job,bytes,{evidence,cases});
   stage='model';modelStart=performance.now();
   const response=await callModel({...job.cfg,apiKey:decrypt(job.cfg.secret)},messages,{fetchImpl,stream:true});
   modelMs=Math.round(performance.now()-modelStart);usage=response.usage;
   stage='validation';
   const raw=parseModelJSON(response.content);
   result=validateAnalysis(raw);
   if(evidence)verifyFlowDirections(result,evidence);
   sources=cases.map(({id,alias,terms})=>({id,alias,terms,used:Array.isArray(raw.usedReferences)&&raw.usedReferences.includes(alias)}));
  }catch(e){
   code=e.modelCode || (stage==='model'?'MAAS_UNAVAILABLE':'ANALYSIS_INTERNAL_ERROR');
   if(modelStart!==null && modelMs===null)modelMs=Math.round(performance.now()-modelStart);
   failure={stage,timeoutSeconds:job.cfg.analysisTimeoutMinutes*60,modelMs,evidence,httpStatus:e.httpStatus,requestId:e.requestId,validationPath:e.validationPath,validationIssue:e.validationIssue};
  }
  await transaction(pool,async c=>{
   const updated=await c.query('UPDATE architecture_analyses SET status=$1,result_json=$2,usage_json=$3,error_code=$4,archived_at=CASE WHEN $8 THEN NOW() ELSE archived_at END,lease_until=NULL,updated_at=now(),version=version+1 WHERE id=$5 AND version=$6 AND status=$7',[code?'failed':'succeeded',!code&&result?JSON.stringify(result):null,usage?JSON.stringify(usage):null,code,job.id,job.runVersion,'running',!code&&projectUpload(job)?1:0]);
   if(updated.rowCount){
    await c.query('UPDATE architecture_inputs SET evidence_json=?,sources_json=? WHERE analysis_id=?',[evidence?JSON.stringify(evidence):null,JSON.stringify(sources),job.id]);
    if(failure)await recordFailure(c,job.id,failure);
    else{
     await queueTranslation(c,job.id,job.language);
     if(projectUpload(job))await audit(c,{email:job.owner_email},'自动归档项目架构图',job.id);
    }
    await audit(c,{email:job.owner_email},code?'架构分析失败':'完成架构图分析',job.id);
   }
  });return true;
 }
 const nextTranslation=()=>runNextTranslation({pool,config,ready,budget,
  translate:(cfg,messages)=>callModel({...cfg,apiKey:decrypt(cfg.secret)},messages,{fetchImpl,stream:true})});
 async function tick(){if(stopped||active)return;active=(async()=>{if(!await runNext())await nextTranslation()})();try{await active}catch{console.error(JSON.stringify({level:'error',code:'PRACTICE_WORKER_FAILED'}))}finally{active=null;if(!stopped)timer=setTimeout(tick,2000).unref()}}
 return {route,createProjectWithDiagram,runNext,runNextTranslation:nextTranslation,runNextContentTranslation:contentTranslations.runNext,start(){if(!stopped)return;contentTranslations.start();stopped=false;timer=setTimeout(tick,500).unref()},async stop(){stopped=true;clearTimeout(timer);await Promise.all([active,contentTranslations.stop()])}};
}
