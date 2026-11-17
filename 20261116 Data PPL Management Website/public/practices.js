let practiceState={items:[],catalog:[],service:{ready:false},selected:null,tab:'understanding',page:1,total:0,archived:false,projectId:''},practiceTimer=null,practiceImage=null,practiceSelection=0;
const practiceStatus={queued:'等待分析',running:'正在分析',succeeded:'分析完成',failed:'分析失败'};
const practiceTerms={observed:'图中明确',inferred:'分析推测',unknown:'待确认',high:'高',medium:'中',low:'低',clear:'清晰',partial:'部分可读',unclear:'无法可靠识别',batch:'批处理',stream:'流处理',request:'请求响应',source:'数据源',ingestion:'数据接入',storage:'数据存储',processing:'计算处理',serving:'数据服务',governance:'治理与安全',operations:'运维',network:'网络'};
const pt=value=>i18n.t(practiceTerms[value]||value);
function openProjectPractices(id){
 practiceSelection++;practiceState.selected=null;practiceState.page=1;practiceState.archived=true;practiceState.projectId=id;
 closeModal();return go('practices');
}
function projectPracticeFilter(){
 const project=data.projects.find(p=>p.id===practiceState.projectId);
 return practiceState.projectId?`<div class="row"><span><span>关联项目</span> · ${content(project?.name||'')}</span>${has('practice.read')?`<button type="button" onclick="practiceState.projectId='';practiceState.page=1;render()">清除项目筛选</button>`:''}</div>`:'';
}
function practicesHTML(){return pageTitle(has('practice.analyze')&&has('practice.read')?'<button class="primary" onclick="newPractice()">＋ 上传架构图</button>':'')+`<div class="practice-tabs" role="tablist" aria-label="最佳实践视图"><button role="tab" aria-selected="${practiceState.tab==='understanding'}" onclick="switchPracticeTab('understanding')">架构解读</button><button role="tab" aria-selected="${practiceState.tab==='comparison'}" onclick="switchPracticeTab('comparison')">方案对比</button></div><div class="practice-library-link">${user.roleId==='admin'?'<a class="buttonlink" href="/settings/maas">架构分析设置</a>':''}${has('practice.read')?'<button type="button" onclick="openCaseLibrary()">参考案例库</button>':''}</div><div id="practiceService"></div><div class="practice-layout"><section class="panel practice-history"><div class="row"><h2>分析记录</h2><button onclick="loadPractices(renderToken)">刷新</button></div>${projectPracticeFilter()}<label class="practice-archive"><input type="checkbox" ${practiceState.archived?'checked':''} onchange="practiceState.archived=this.checked;practiceState.page=1;loadPractices(renderToken)">包含已归档</label><div id="practiceList" class="empty">正在加载分析记录…</div><div id="practicePages"></div></section><section id="practiceDetail" class="panel practice-detail"><div class="practice-empty"><span class="practice-mark">◇</span><h2>让架构图成为可讨论的方案</h2><p>上传架构图后，查看厂商、组件、数据流和关键问题，再逐项比较华为云服务建议。</p><div class="practice-steps"><span>01 · 读懂架构</span><span>02 · 匹配服务</span><span>03 · 验证迁移</span></div></div></section></div>`}
function practiceInLanguage(item,language=i18n.language){
 if(!item)return null;
 const primary=(item.sourceLanguage||item.language)===language,tr=item.translations?.[language];
 return {...item,language,sourceLanguage:item.sourceLanguage||item.language,
  result:primary?item.result:tr?.result??null,translation:primary?null:tr,
  drawingVersion:item.drawingVersions?.[language]??(primary?item.drawingVersion||0:0)};
}
function practiceLanguageSwitch(language){
 return '<div class="language-switch no-export" role="group" aria-label="'+i18n.t('报告与图纸语言')+'">'+
  ['zh','en'].map(lang=>'<button type="button" data-language="'+lang+'" aria-pressed="'+(lang===language)+'" class="'+(lang===language?'selected':'')+'">'+(lang==='zh'?'中文':'English')+'</button>').join('')+'</div>';
}
async function retryPracticeTranslation(){
 const item=practiceState.selected,language=i18n.language;
 try{await api('practices/'+item.id+'/translation','POST',{_version:item.version,language});await loadPractices(renderToken)}
 catch(e){error(e)}
}
function schedulePracticePoll(token){
 clearTimeout(practiceTimer);
 if(page!=='practices')return;
 const pending=Object.values(practiceState.selected?.translations||{}).filter(tr=>['queued','running'].includes(tr.status));
 const analyzing=practiceState.items.some(x=>['queued','running'].includes(x.status));
 if(!analyzing&&!pending.length)return;
 const delay=!analyzing&&pending.every(tr=>tr.errorCode==='DAILY_LIMIT')?60000:3500;
 practiceTimer=setTimeout(()=>{if(page==='practices'&&token===renderToken)loadPractices(token).catch(error)},delay);
}
async function loadPractices(token=renderToken){
 const result=await api(`practices?page=${practiceState.page}&archived=${practiceState.archived}${practiceState.projectId?'&projectId='+encodeURIComponent(practiceState.projectId):''}`);if(page!=='practices'||token!==renderToken)return;
 Object.assign(practiceState,result);
 $('#practiceService').innerHTML=result.service.ready?`<div class="practice-service"><span class="dot"></span><span>${result.service.inputMode==='ocr'?'云端 OCR + 文本 MaaS':'多模态 MaaS'}</span><small data-user-content>${esc(result.service.model)}${result.service.region?' · '+esc(result.service.region):''}</small></div>`:`<div class="notice"><span>管理员尚未完成架构分析服务配置</span>${user.roleId==='admin'?'<button onclick="maasSettingsForm()">配置 MaaS</button>':''}</div>`;
 $('#practiceList').className='';$('#practiceList').innerHTML=result.items.map(item=>`<button class="practice-item ${practiceState.selected?.id===item.id?'selected':''}" onclick="selectPractice('${item.id}')"><span data-user-content>${esc(item.title)}</span><small><span>${practiceStatus[item.status]}</span> · ${esc(item.created_at.slice(0,10))}${item.archived_at?' · <span>已归档</span>':''}</small><small data-user-content>${esc(item.owner_email)}</small></button>`).join('')||'<p class="empty">暂无架构分析</p>';
 $('#practicePages').innerHTML=`<div class="row"><button ${result.page<=1?'disabled':''} onclick="practiceState.page--;loadPractices(renderToken)">上一页</button><span>${result.page} / ${Math.max(1,Math.ceil(result.total/30))}</span><button ${result.page*30>=result.total?'disabled':''} onclick="practiceState.page++;loadPractices(renderToken)">下一页</button></div>`;
 if(practiceState.selected){const id=practiceState.selected.id,seq=practiceSelection;let selected;try{selected=await api('practices/'+id)}catch(e){if([403,404].includes(e.status)&&seq===practiceSelection){practiceState.selected=null;$('#practiceDetail').innerHTML='<p class="empty">当前没有可查看的分析</p>';return}throw e}if(page!=='practices'||token!==renderToken||seq!==practiceSelection||id!==practiceState.selected?.id)return;practiceState.selected=selected;renderPracticeDetail()}
 schedulePracticePoll(token);
}
async function selectPractice(id){try{const token=renderToken,seq=++practiceSelection,value=await api('practices/'+id);if(page!=='practices'||token!==renderToken||seq!==practiceSelection)return;practiceState.selected=value;renderPracticeDetail();schedulePracticePoll(token);document.querySelectorAll('.practice-item').forEach(e=>e.classList.toggle('selected',e.getAttribute('onclick')===`selectPractice('${id}')`));if(innerWidth<1000)$('#practiceDetail').scrollIntoView({behavior:'smooth',block:'start'})}catch(e){error(e)}}
function switchPracticeTab(tab){practiceState.tab=tab;document.querySelectorAll('.practice-tabs button').forEach((b,i)=>b.setAttribute('aria-selected',String(i===(tab==='understanding'?0:1))));renderPracticeDetail()}
const failureStages={translation:'双语翻译',"image":"原图读取","ocr":"云端 OCR 识别","references":"参考案例检索","model":"MaaS 模型调用","validation":"分析结果校验","worker":"后台任务执行"};
async function showPracticeFailures(){
 const item=practiceState.selected;
 if(!item)return;
 try{
  const {items}=await api('practices/'+item.id+'/failures');
  if(practiceState.selected?.id!==item.id)return;
  const field=(label,value)=>value==null?'':'<dt>'+esc(label)+'</dt><dd data-user-content>'+esc(value)+'</dd>';
  const entries=items.map(row=>{
   const facts=field('翻译目标语言',row.language&&row.language.toUpperCase())+field('模型',row.model)+field('任务耗时（秒）',row.elapsed_seconds)+field('MaaS 等待上限（秒）',row.timeout_seconds)
    +field('MaaS 耗时（秒）',row.model_elapsed_ms==null?null:Math.round(row.model_elapsed_ms/100)/10)
    +field('OCR 文字标签',row.ocr_labels)+field('OCR 候选连线',row.ocr_connections)
    +field('校验字段',row.validation_path)+field('MaaS HTTP 状态',row.http_status)+field('MaaS 请求 ID',row.provider_request_id);
   return '<article class="practice-failure"><div class="row"><strong>'+esc(failureStages[row.stage]||'后台任务执行')+'</strong><time data-user-content>'+esc(row.failed_at)+' UTC</time></div>'+
    '<p>'+esc(row.message)+'</p>'+(row.validationNote?'<p>'+esc(row.validationNote)+'</p>':'')+'<code data-user-content>'+esc(row.error_code)+'</code><dl>'+facts+'</dl></article>';
  }).join('');
  openForm('<h2>失败日志</h2><p data-user-content>'+esc(item.title)+'</p>'+(entries||'<p class="viewnote">此记录尚无失败日志。</p>')+actions(false),()=>{});
 }catch(e){error(e)}
}

function practiceTable(headings,rows){return `<div class="practice-table"><table><thead><tr>${headings.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(row=>`<tr>${row.map(x=>`<td>${x}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headings.length}">暂无可确认信息</td></tr>`}</tbody></table></div>`}
function practiceList(items,render=content){return items.length?'<ul class="practice-points">'+items.map(x=>'<li>'+render(x)+'</li>').join('')+'</ul>':'<p class="subtitle">暂无可确认信息</p>'}
function serviceLink(id){const item=practiceState.catalog.find(s=>s.id===id);return item?`<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer" data-user-content>${esc(item.name)} ↗</a>`:content(id)}
function renderPracticeDetail(){
 const item=practiceInLanguage(practiceState.selected),box=$('#practiceDetail');if(!item||!box)return;
 const labels=practiceCitations.index(item.ocrEvidence),narrative=value=>practiceNarrative(value,labels,item.language);
 const r=item.result,canEdit=item.canMaintain===true;
 let html=`<div class="row"><div><h2 data-user-content>${esc(item.title)}</h2></div><span class="pill"><span>${practiceStatus[item.status]}</span>${item.archived_at?' · <span>已归档</span>':''}</span></div><p class="subtitle">${content(item.target_region)} · ${content(item.owner_email)} · ${content(item.language==='en'?'English':'中文')}</p><div class="practice-detail-actions">${practiceLanguageSwitch(item.language)}<button type="button" onclick="showPracticeFailures()">失败日志</button>${r?'<button onclick="exportPractice()">导出分析报告</button>':''}${canEdit&&item.status==='failed'&&!item.archived_at?'<button onclick="practiceAction(\'retry\')">重新分析</button>':''}${canEdit&&!['queued','running'].includes(item.status)?`<button onclick="practiceAction('${item.archived_at?'restore':'archive'}')">${item.archived_at?'恢复记录':'归档记录'}</button>`:''}</div>`;
 const assigned=data.projects.find(p=>p.id===item.project_id);
 html+='<div class="practice-tools"><span>'+i18n.t(item.project_id?'仅项目 BD、SA 和平台管理员可见':'仅上传者和管理员')+'</span>'+(assigned?' · '+content(assigned.name):'')+(canEdit&&!item.projectSubmission&&(!item.project_id||user.roleId==='admin')&&!item.archived_at&&!['queued','running'].includes(item.status)?'<button class="no-export" type="button" onclick="editPracticeProject()">修改原图可见范围</button>':'')+'</div>';
 if(!r&&item.status==='succeeded'){
  const tr=item.translation,failed=tr?.status==='failed';
  html+='<div class="practice-pending" role="status"><h3>'+(failed?'此语言版本生成失败':'正在准备此语言版本')+'</h3>'+
   '<p>'+esc(tr?.errorMessage||'云端正在翻译这份分析，完成后此页会自动更新。')+'</p>'+
   (failed&&canEdit&&(!item.archived_at||item.projectSubmission)?'<button type="button" onclick="retryPracticeTranslation()">重试翻译</button>':'')+'</div>';
  box.innerHTML=html;i18n.apply(box);return;
 }
 if(!r){html+=`<div class="practice-pending"><h3>${item.status==='failed'?'分析未完成':'正在读取架构并整理方案'}</h3><p>${item.status==='failed'?esc(item.errorMessage):'可以离开此页面，分析会在后台继续，结果自动保存。'}</p></div><img class="practice-original" src="/api/practices/${item.id}/image" alt="上传的架构图">`;box.innerHTML=html;return}
 html+=`<div class="notice"><span>AI 生成的分析建议，请结合客户信息复核。华为云服务的区域可用性、版本兼容性、规格与费用需要另行确认。</span></div>`;
 if(practiceState.tab==='understanding'){
  html+=`<div class="practice-summary"><h3>架构结论</h3><p>${narrative(r.summary)}</p><span class="pill">${pt(r.readability)}</span></div><details class="practice-source" open><summary>原始架构图</summary>${evidenceImage(item)}</details>`;
  html+=practiceEvidence(item);
  if(item.context_text)html+=`<details><summary>补充背景（原文）</summary><p>${content(item.context_text)}</p></details>`;
  html+='<h3>厂商与产品识别</h3>'+practiceTable(['厂商','产品','识别依据','可信程度'],r.vendors.map(v=>[narrative(v.name),narrative(v.products.join(' · ')),narrative(v.evidence)+`<small>${pt(v.basis)}</small>`,pt(v.confidence)]));
  html+='<h3>组件职责</h3>'+practiceTable(['组件','厂商 / 产品','架构层','作用与依据'],r.components.map(c=>[narrative(c.name)+`<small data-user-content>${esc(c.id)}</small>`,narrative(c.vendor+' / '+c.product),pt(c.layer),narrative(c.role)+`<small>${narrative(c.evidence)} · ${pt(c.basis)}</small>`]));
  const component=id=>r.components.find(c=>c.id===id)?.name||id;
  html+='<h3>数据流</h3>'+practiceTable(['流向','数据内容','处理方式','依据'],r.flows.map(f=>[narrative(component(f.from)+(f.directionConfirmed===false?' · ':' → ')+component(f.to))+(f.directionConfirmed===false?'<small>方向待确认</small>':''),narrative(f.data),pt(f.mode),narrative(f.evidence)+`<small>${pt(f.basis)}</small>`]));
  html+='<h3>风险与验证</h3>'+practiceTable(['问题','影响程度','分析','验证方式'],r.risks.map(x=>[narrative(x.title),pt(x.severity),narrative(x.detail),narrative(x.validation)]));
  html+='<h3>识别局限</h3>'+practiceList(r.limitations,narrative)+'<h3>需要向客户确认</h3>'+practiceList(r.questions,narrative);
 }else{
  html+=`<div class="practice-summary"><h3>华为云方案建议</h3><p>${narrative(r.target.summary)}</p></div><div class="practice-comparison-images"><div><h3>原始架构</h3>${evidenceImage(item)}</div><div><h3>建议架构 · 待验证</h3>${drawingPanel(item,canEdit)}</div></div>`;
  html+='<h3>服务映射与改造点</h3>'+practiceTable(['原有组件','华为云候选服务','匹配理由','改造与验证'],r.mappings.map(m=>[narrative(r.components.find(c=>c.id===m.componentId)?.name||m.componentId),m.serviceIds.map(serviceLink).join('<br>'),narrative(m.reason),narrative(m.changes)+`<small>${narrative(m.validation)}</small>`]));
  html+='<h3>'+(item.drawingVersion?'初始建议的数据流':'建议架构的数据流')+'</h3>'+practiceTable(['流向','数据内容'],r.target.flows.map(f=>[narrative(f.from+' → '+f.to),narrative(f.data)]));
  html+='<h3>方案逐项对比</h3>'+practiceTable(['维度','原架构','推荐方案','取舍与验证'],r.comparison.map(c=>[narrative(c.dimension),narrative(c.original),narrative(c.recommended),narrative(c.tradeoff)+`<small>${narrative(c.validation)}</small>`]));
  html+='<h3>迁移与验证顺序</h3><ol class="practice-migration">'+r.migration.map(m=>`<li><h4>${narrative(m.step)}</h4><p>${narrative(m.actions)}</p><p class="subtitle"><span>验收与回退条件</span>：${narrative(m.acceptance)}</p></li>`).join('')+'</ol><h3>待确认事项</h3>'+practiceList(r.questions,narrative);
 }
 html+=referenceSummary(item,canEdit,narrative);
 html+=`<p class="practice-provenance"><span>模型</span>：${content(item.model)} · <span>完成时间</span>：${content(item.updated_at)} UTC${item.usage?.total_tokens!=null?' · Tokens: '+esc(item.usage.total_tokens):''}</p>`;box.innerHTML=html;attachPracticeCitations(box,labels,item);i18n.apply(box);
}
function practiceProjectPicker(current) {
 const options=data.projects.filter(p=>!p.archivedAt&&(user.roleId==='admin'||own(p)));
 return '<label>关联项目</label><select name="projectId" onchange="updateReferenceChoice(this.value)">'+(current?'':'<option value="">仅上传者和管理员</option>')+options.map(p=>'<option data-user-content value="'+esc(p.id)+'" '+(p.id===current?'selected':'')+'>'+esc(p.name)+'</option>').join('')+'</select><p class="viewnote">关联后，仅项目当前指派的 BD、SA 和平台管理员可以查看原图和分析。</p>';
}
function editPracticeProject() {
 const item=practiceState.selected;
 openForm('<h2>修改原图可见范围</h2>'+practiceProjectPicker(item.project_id)+actions(),async fd=>{
  await api('practices/'+item.id+'/project','POST',{_version:item.version,projectId:fd.get('projectId')||null});
  closeModal();await loadPractices(renderToken);
 });
}
function updateReferenceChoice(projectId){
 const choice=$('#referenceChoice');if(!choice)return;
 choice.hidden=!!projectId;
 const box=choice.querySelector('input');box.disabled=!!projectId;if(projectId)box.checked=false;
}
function newPractice(){
 if(!practiceState.service.ready){toast('管理员尚未完成架构分析服务配置');if(user.roleId==='admin')maasSettingsForm();return}
 practiceImage=null;const requestKey=crypto.randomUUID(),inputMode=practiceState.service.inputMode;
 openForm(`<h2>上传架构图</h2><p class="viewnote">${inputMode==='vision'?'图片与补充背景将发送至管理员配置的华为云 MaaS 进行分析。请确认你有权分享这些资料。':'平台在华为云 ECS 上识别原图，再将提取的文字、位置、候选连线及补充背景发送给文本 MaaS。'}</p>${practiceProjectPicker('')}<label>分析标题 *</label><input name="title" required maxlength="200" placeholder="例如：某客户数据平台现网架构"><div class="formgrid"><div><label>业务类别</label><select name="businessType"><option>大数据</option><option>数据库</option><option>综合架构</option></select></div><div><label>目标部署区域 *</label><input name="targetRegion" required maxlength="120" value="la-south-2 (Santiago)"></div></div><p class="viewnote">中文和英文版报告及目标架构图都会保存，优先生成当前界面的语言。</p><label>架构图 *</label><input name="image" type="file" accept="image/png,image/jpeg,image/webp" required onchange="previewPracticeImage(this)"><p class="viewnote">支持 PNG、JPEG、WebP，最大 2MB；请保证组件名称和箭头清晰。</p><div id="practiceUploadPreview"></div><label>补充背景</label><textarea name="context" maxlength="8000" rows="4" placeholder="业务目标、数据规模、延迟要求、已知产品版本，以及你关注的问题"></textarea><label class="case-choice" id="referenceChoice"><input type="checkbox" name="referenceRequested"><span>列为参考案例候选，复核后供团队使用</span></label><div class="formactions"><button type="button" onclick="closeModal()">取消</button><button class="primary">上传并分析</button></div>`,async fd=>{
  const file=fd.get('image');const image=await readPracticeImage(file);
  const item=await api('practices','POST',{requestKey,inputMode,projectId:fd.get('projectId')||null,referenceRequested:fd.has('referenceRequested'),title:fd.get('title'),businessType:fd.get('businessType'),targetRegion:fd.get('targetRegion'),language:i18n.language,context:fd.get('context'),...image});
  closeModal();practiceSelection++;practiceState.selected=item.id?item:null;practiceState.page=1;practiceState.projectId='';practiceState.archived=false;await go('practices');toast('架构图已提交，分析结果会自动保存');
 });
}
async function readPracticeImage(file){if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type)||!file.size||file.size>2097152)throw new Error('请上传清晰的 PNG、JPEG 或 WebP 图片，大小不超过 2MB');const base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('文件读取失败'));reader.readAsDataURL(file)});return {name:file.name,mime:file.type,base64}}
async function previewPracticeImage(input){try{const value=await readPracticeImage(input.files[0]);$('#practiceUploadPreview').innerHTML=`<img class="practice-original" alt="架构图预览" src="data:${value.mime};base64,${value.base64}">`}catch(e){input.value='';$('#practiceUploadPreview').innerHTML='';error(e)}}
async function practiceAction(action){try{const p=practiceState.selected;if(action==='retry'&&!confirm(i18n.t('重新分析会再次调用 MaaS，是否继续？')))return;practiceState.selected=await api(`practices/${p.id}/${action}`,'POST',{_version:p.version});await loadPractices(renderToken);renderPracticeDetail()}catch(e){error(e)}}
async function exportPractice(){
 try{
  const item=practiceInLanguage(practiceState.selected),language=item.language,oldTab=practiceState.tab;if(!item.result)throw new Error(i18n.t('此语言版本尚未就绪'));practiceState.tab='understanding';renderPracticeDetail();const first=$('#practiceDetail').innerHTML;practiceState.tab='comparison';renderPracticeDetail();const second=$('#practiceDetail').innerHTML;practiceState.tab=oldTab;renderPracticeDetail();
  const inline=async(src)=>{const response=await fetch(src);if(!response.ok)throw new Error('文件读取失败');const blob=await response.blob();return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('文件读取失败'));reader.readAsDataURL(blob)})};
  const image=await inline('/api/practices/'+item.id+'/image');
  const target=item.result.target.nodes.length?await inline(practiceDrawingURL(item,'preview')):null;
  const holder=document.createElement('div');holder.innerHTML=`<h1>${language==='en'?'Architecture review':'架构解读'}</h1>${first}<hr><h1>${language==='en'?'Solution comparison':'方案对比'}</h1>${second}`;holder.querySelectorAll('.practice-detail-actions,.no-export').forEach(e=>e.remove());holder.querySelectorAll('button').forEach(b=>b.replaceWith(...b.childNodes));holder.querySelectorAll('img').forEach(e=>e.src=e.classList.contains('target-preview')?target:image);holder.querySelectorAll('a').forEach(a=>{if(a.getAttribute('href')?.startsWith('/'))a.replaceWith(...a.childNodes)});holder.querySelectorAll('details').forEach(d=>{d.open=!d.matches('.practice-citations,.practice-ocr-evidence')});
  const html=`<!doctype html><html lang="${language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'"><title>${esc(item.title)}</title><style>.diagram-image{position:relative;display:block;width:100%;margin:8px 0}
.diagram-image img.practice-original{display:block;width:100%;height:auto;max-height:none;max-width:100%;padding:0;margin:0;border:0;border-radius:0}
.diagram-highlight{position:absolute;pointer-events:none;scroll-margin-block:18vh}
.diagram-highlight:target{outline:3px solid #174c85;outline-offset:2px;background:rgba(120,181,249,.25);box-shadow:0 0 0 5px white}
.diagram-link{display:inline-block;margin:.2rem .4rem;color:#325f8e;text-decoration:underline}
.lead-details>summary{cursor:pointer;font-weight:600;padding:.65rem 0}
body{font:16px/1.65 Arial,'Microsoft YaHei',sans-serif;color:#25374b;max-width:1200px;margin:40px auto;padding:20px}h2{font-size:26px}h3{margin-top:30px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #dbe2ea;padding:12px;vertical-align:top;text-align:left}th{background:#edf3f8}small{display:block;color:#56697e}img{max-width:100%;max-height:600px;object-fit:contain}svg{width:100%}.notice{background:#f3f6fa;padding:16px}.practice-comparison-images{display:grid;grid-template-columns:1fr 1fr;gap:20px}a{color:#365e8a}.practice-provenance{color:#62748a}.practice-citations{margin:.45rem 0 0;font:normal 15px/1.5 Arial,'Microsoft YaHei',sans-serif;color:#344b60}.practice-citations>summary{display:list-item;cursor:pointer;color:#375c7a;font-weight:500}.practice-citations>summary:focus-visible{outline:2px solid #497397;outline-offset:3px}.practice-citations>ul{background:#f0f5f9;border-radius:6px;padding:.5rem .75rem;list-style:none;margin:.4rem 0 0}.practice-citations>ul>li{margin:0;padding:.35rem 0;overflow-wrap:anywhere}.practice-citations li+li{border-top:1px solid #dce5ed}.practice-citations li small{display:block;color:#506479;font-size:.9em}@media print{body{margin:0}tr,img,svg{break-inside:avoid}}</style><body>${holder.innerHTML}</body></html>`;
  const link=document.createElement('a'),url=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));link.href=url;link.download='architecture-review-'+item.id+'-'+language+'.html';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('架构分析报告已导出');
 }catch(e){error(e)}
}
function maasSettingsHTML(){return `<div class="panel sectiongap"><div class="row"><div><h2>架构图 AI 设置</h2><p class="subtitle">使用纯文本模型时，平台先在华为云 ECS 上识别架构图。多模态模型可以直接读取原图。</p></div><button onclick="maasSettingsForm()">配置 MaaS</button></div><p class="viewnote">API Key 仅保存在服务端，不会回显给浏览器。可设置每日调用上限。</p></div>`}
async function maasSettingsForm(){
 try{const cfg=await api('practices/config');
 openForm(`<h2>华为云 MaaS 配置</h2><p class="viewnote">请从 MaaS 控制台复制调用地址和模型名称。</p><label for="maasInputMode">识别模式</label><select id="maasInputMode" name="inputMode" aria-describedby="maasModeHelp"><option value="ocr" ${cfg.inputMode==='ocr'?'selected':''}>云端 OCR + 文本 MaaS</option><option value="vision" ${cfg.inputMode==='vision'?'selected':''}>多模态 MaaS</option></select><p id="maasModeHelp" class="viewnote">使用纯文本模型时，平台先在华为云 ECS 上识别架构图。多模态模型可以直接读取原图。</p><label>Endpoint *</label><input name="endpoint" type="url" required value="${esc(cfg.endpoint)}" placeholder="https://api.modelarts-maas.com/v1/chat/completions"><label>模型名称 *</label><input name="model" required maxlength="200" value="${esc(cfg.model)}"><label>服务所在区域</label><input name="region" maxlength="120" value="${esc(cfg.region)}"><label>API Key</label><input name="apiKey" type="password" autocomplete="new-password" maxlength="4096" ${cfg.apiKeySet?'':'required'} placeholder="${cfg.apiKeySet?'已保存，留空保持原密钥':'填写 MaaS API Key'}"><div class="formgrid"><div><label>每日调用上限</label><input name="dailyLimit" type="number" min="1" max="500" required value="${cfg.dailyLimit}"></div><div><label>模型输出上限（Tokens）</label><input name="maxTokens" type="number" min="2048" max="32768" required value="${cfg.maxTokens}"></div></div><label for="maasAnalysisTimeout">MaaS 分析时限（分钟）</label><input id="maasAnalysisTimeout" aria-describedby="maasTimeoutHelp" name="analysisTimeoutMinutes" type="number" min="1" max="30" step="1" required value="${cfg.analysisTimeoutMinutes??10}"><p id="maasTimeoutHelp" class="viewnote">每次正式分析可等待 1 至 30 分钟。</p><label>服务开关</label><select name="enabled"><option value="true" ${cfg.enabled?'selected':''}>启用</option><option value="false" ${!cfg.enabled&&cfg.apiKeySet?'selected':''}>停用</option></select><p class="viewnote">文本模式使用中英文样图检查云端 OCR，并单独测试文本模型。多模态模式使用随机数字图。测试计入每日上限。</p><div id="maasTestResult">${cfg.tested?'<p>服务连接测试已通过</p>':''}</div><div class="formactions"><button type="button" onclick="closeModal()">取消</button><button class="primary">保存并测试</button></div>`,async fd=>{
  const saved=await api('practices/config','POST',{_version:cfg._version,inputMode:fd.get('inputMode'),endpoint:fd.get('endpoint'),model:fd.get('model'),region:fd.get('region'),apiKey:fd.get('apiKey'),dailyLimit:Number(fd.get('dailyLimit')),maxTokens:Number(fd.get('maxTokens')),analysisTimeoutMinutes:Number(fd.get('analysisTimeoutMinutes')),enabled:fd.get('enabled')==='true'});
  cfg._version=saved._version;$('#form [name=apiKey]').value='';$('#form [name=apiKey]').required=false;
  if(saved.enabled){$('#maasTestResult').innerHTML='<p>正在测试架构分析服务…</p>';try{await api('practices/test','POST',{});toast('架构分析服务已就绪，可上传架构图')}finally{const latest=await api('practices/config');cfg._version=latest._version;$('#maasTestResult').innerHTML=latest.tested?'<p>服务连接测试已通过</p>':'<p>服务连接测试未通过，请检查配置</p>'}}
  else toast('MaaS 服务已停用');closeModal();if(page==='practices')await loadPractices(renderToken);
 });
 }catch(e){error(e)}
}
document.addEventListener('languagechange',()=>{if(page==='practices'){renderPracticeDetail();schedulePracticePoll(renderToken)}});
