function maasLandingHTML(){
  const role=roleLabel({id:user.roleId,name:user.roleName});
  const details=user.roleId==='admin'?maasSettingsHTML():
    '<section class="panel"><h2>需要平台管理员配置</h2><p>请将此页面链接发给平台管理员。管理员可以填写模型调用地址、模型名称和 API Key。</p></section>';
  return title('架构分析设置','管理最佳实践使用的华为云 MaaS 服务。')+
    '<p class="viewnote"><span>当前角色</span> · '+role+'</p>'+details;
}

function practiceDrawingURL(item,action){
  const base='/api/practices/'+item.id+'/drawing',params=new URLSearchParams({lang:item.language});
  if(action==='preview'){params.set('v',item.drawingVersion);return base+'/preview?'+params}
  if(action==='download')params.set('download','1');
  return base+'?'+params;
}
function drawingPanel(item,canEdit) {
  if(!item.result.target.nodes.length)return '<p class="empty">暂无可确认信息</p>';
  const preview=practiceDrawingURL(item,'preview');
  return `<a href="${esc(preview)}" target="_blank" rel="noopener"><img class="target-preview" src="${esc(preview)}" alt="华为云目标架构图"></a>
    <p class="viewnote">${item.drawingVersion?'<span>团队编辑版</span> · v'+item.drawingVersion:'<span>基于服务映射生成</span>'}</p>
    <div class="practice-tools no-export"><a class="buttonlink" href="${esc(practiceDrawingURL(item,'download'))}" download>下载 .drawio</a>
    ${canEdit&&!item.archived_at?'<button type="button" onclick="openDrawingEditor()">用 draw.io 编辑</button>':''}</div><p class="viewnote no-export">在线编辑会在浏览器中的 draw.io 编辑器打开当前目标图。下载的文件可离线编辑。</p>`;
}

function practiceNarrative(value,labels,language) {
  const {text,ids}=practiceCitations.format(value,labels,language);
  if(!ids.length)return content(value);
  return '<span data-user-content data-diagram-labels="'+esc(ids.join(' '))+'">'+esc(text)+'</span>';
}

function evidencePosition(label) {
  if(!/^L[1-9]\d{0,2}$/.test(label?.id)||!Array.isArray(label.box)||label.box.length!==4||!label.box.every(Number.isFinite))return null;
  const [x,y,w,h]=label.box;
  if(x<0||y<0||x>=1000||y>=1000||w<=0||h<=0)return null;
  return [x/10,y/10,Math.min(w,1000-x)/10,Math.min(h,1000-y)/10];
}
function evidenceTarget(item,label) {return 'mark-'+practiceState.tab+'-'+item.id+'-'+label.id}
function evidenceLink(item,label) {
  if(!evidencePosition(label))return '';
  return '<a class="diagram-link" href="#'+esc(evidenceTarget(item,label))+'">'+i18n.t('在原图中定位')+'</a>';
}
function evidenceImage(item) {
  const markers=(item.ocrEvidence?.labels||[]).map(label=>{
    const position=evidencePosition(label);if(!position)return '';
    const [x,y,w,h]=position;
    return '<span class="diagram-highlight" tabindex="-1" role="img" aria-label="'+esc(label.text)+'" id="'+esc(evidenceTarget(item,label))+'" style="left:'+x+'%;top:'+y+'%;width:'+w+'%;height:'+h+'%"></span>';
  }).join('');
  return '<div class="diagram-image"><img class="practice-original" src="/api/practices/'+esc(item.id)+'/image" alt="'+i18n.t('上传的架构图')+'">'+markers+'</div><a class="no-export" href="/api/practices/'+esc(item.id)+'/image" target="_blank" rel="noopener">'+i18n.t('打开完整原图')+'</a>';
}
document.addEventListener('click',event=>{
  const link=event.target.closest?.('a.diagram-link');if(!link)return;
  const mark=document.getElementById(link.hash.slice(1)),details=mark?.closest('details');
  if(details)details.open=true;
});
function attachPracticeCitations(root,labels,item) {
  const byContainer=new Map();
  for(const span of root.querySelectorAll('[data-diagram-labels]')){
    const container=span.closest('td,li,.practice-summary,.practice-reference');
    if(!container)continue;
    if(!byContainer.has(container))byContainer.set(container,new Set());
    const ids=byContainer.get(container);
    span.dataset.diagramLabels.split(' ').forEach(id=>ids.add(id));
    span.removeAttribute('data-diagram-labels');
  }
  for(const [container,ids] of byContainer){
    const rows=[...ids].map(id=>{
      const label=labels.get(id);
      const name=label?.text?content(label.text):'<span>未找到对应的原图文字</span>';
      const confidence=label?.confidence==null?'':' · <span>识别置信度</span> '+content(label.confidence+' / 100');
      return '<li><strong>'+name+'</strong>'+evidenceLink(item,label)+'<small><span>识别编号</span> '+content(id)+confidence+'</small></li>';
    });
    container.insertAdjacentHTML('beforeend','<details class="practice-citations"><summary><span>查看原图标注</span> ('+ids.size+')</summary><ul>'+rows.join('')+'</ul></details>');
  }
}

function practiceEvidence(item) {
  if(!item.ocrEvidence)return '';
  const e=item.ocrEvidence,labels=new Map(e.labels.map(l=>[l.id,l.text]));
  const connections=e.connections.map(c=>{
    const first=labels.get(c.direction==='b-to-a'?c.b:c.a),second=labels.get(c.direction==='b-to-a'?c.a:c.b);
    return [content(first+(c.direction==='unknown'?' · ':' → ')+second),i18n.t(c.direction==='unknown'?'方向待确认':'检测到箭头')];
  });
  return '<details class="practice-source practice-ocr-evidence"><summary>OCR 识别依据</summary>'+
    '<p class="viewnote">点击标注可在原图中查看对应区域。</p>'+
    practiceTable(['图中文字','位置','识别置信度','识别编号'],e.labels.map(l=>[content(l.text),evidencePosition(l)?evidenceLink(item,l):i18n.t('暂无定位'),content(l.confidence+' / 100'),content(l.id)]))+
    (connections.length?practiceTable(['图中连线','方向'],connections):'<p class="subtitle">未识别到可确认的直线连接</p>')+
    (e.truncated?'<p class="viewnote">仅显示前 100 个文字区域</p>':'')+'</details>';
}

function referenceSummary(item,canEdit,narrative=content) {
  const active=item.reference;
  const sources=(item.sources||[]).map(s=>`<li>${content(s.alias)} · ${s.available?`<button type="button" class="buttonlink" onclick="openReferenceCase('${s.id}')">${content(s.title)}</button>`:'<span>案例已撤下或归档</span>'} · <span>${s.used?'模型引用':'检索匹配'}</span></li>`).join('');
  const edit=canEdit&&has('practice.manage')&&item.status==='succeeded'&&!item.archived_at;
  if(!active&&!sources&&!edit&&!item.referenceRequested)return '';
  return `<section class="practice-reference"><h3>案例参考</h3>${sources?'<ul class="practice-points">'+sources+'</ul>':''}
    ${active?'<p><span class="pill">'+(active.title?'已收录':'待脱敏审核')+'</span></p><p>'+narrative(active.summary)+'</p>':item.referenceRequested?'<p class="subtitle">参考案例候选，等待复核摘要与映射。</p>':''}
    ${edit?`<div class="practice-tools no-export"><button type="button" onclick="reviewReference()">${active?'编辑案例摘要':item.referenceRequested?'审核候选案例':'收录为参考案例'}</button>
    ${active?'<button type="button" onclick="withdrawReference()">撤下案例</button>':''}</div>`:''}</section>`;
}

async function openReferenceCase(id) {
  try{
    const c=await api('practices/references/'+id);
    if($('#modal').open)closeModal();
    openForm('<h2>'+content(c.title)+'</h2><p>'+content(c.summary)+'</p>'+practiceTable(['原有组件','华为云候选服务'],c.mappings.map(m=>[content(m.product),serviceLink(m.service)]))+actions(false),()=>{});
  }catch(e){error(e)}
}
function reviewReference() {
  const item=practiceState.selected,options=item.referenceCandidates||[],saved=item.reference;
  const selected=new Set((saved?saved.mappings:options).map(m=>m.product+'|'+m.service));
  const boxes=options.map((m,i)=>`<label class="case-choice"><input type="checkbox" name="mapping" value="${i}" ${selected.has(m.product+'|'+m.service)?'checked':''}><span data-user-content>${esc(m.product)} → ${esc(practiceState.catalog.find(s=>s.id===m.service)?.name||m.service)}</span></label>`).join('');
  openForm(`<h2>审核参考案例</h2><p class="viewnote">后续分析可检索这份摘要及勾选的服务映射。请核对内容并去除客户敏感信息。</p>
    <label>公开案例标题</label><input name="publicTitle" required maxlength="200" value="${esc(saved?.title||'')}"><label>案例摘要</label><textarea name="summary" required maxlength="1000" rows="5">${esc(saved?.summary||practiceCitations.format(practiceInLanguage(item)?.result?.summary||item.result.summary,practiceCitations.index(item.ocrEvidence),practiceInLanguage(item)?.result?i18n.language:item.language).text.slice(0,1000))}</textarea>
    <h3>确认可复用的映射</h3>${boxes||'<p>暂无可确认信息</p>'}<label class="case-choice"><input type="checkbox" name="reviewed" required><span>已核对标题、摘要和映射，已去除客户敏感信息。</span></label>${actions()}`,async fd=>{
      const mappings=fd.getAll('mapping').map(i=>options[Number(i)]);
      await api('practices/'+item.id+'/reference','POST',{_version:item.version,publish:true,title:fd.get('publicTitle'),reviewed:fd.has('reviewed'),summary:fd.get('summary'),mappings});
      closeModal();await selectPractice(item.id);toast('已保存参考案例');
    });
}
async function withdrawReference(){
  const item=practiceState.selected;
  if(!confirm(i18n.t('撤下后，后续分析将停止引用此案例。是否继续？')))return;
  try{await api('practices/'+item.id+'/reference','POST',{_version:item.version,publish:false});await selectPractice(item.id);toast('已撤下参考案例')}catch(e){error(e)}
}

function openCaseLibrary() {
  openForm(`<h2>参考案例库</h2><label>搜索标题或摘要</label><div class="case-search"><input name="query" maxlength="80" type="search"><button>搜索</button></div><div id="caseResults" aria-live="polite"></div>${actions(false)}`,async()=>showCases());
  showCases().catch(error);
}
let caseQuerySerial=0;
async function showCases(pageNumber=1,product='',service='') {
  const token=++caseQuerySerial,box=$('#caseResults');if(!box)return;
  const q=$('#form [name=query]').value.trim(),query=new URLSearchParams({q,product,service,page:pageNumber});
  const data=await api('practices/references?'+query);
  if(token!==caseQuerySerial||!box.isConnected)return;
  box.innerHTML=`<h3>重复出现的服务映射</h3><div class="case-patterns">${data.patterns.map((m,i)=>`<button type="button" data-pattern="${i}">${content(m.product+' → '+(practiceState.catalog.find(s=>s.id===m.service_id)?.name||m.service_id))} <b>× ${Number(m.cases_used)}</b></button>`).join('')||'<p class="viewnote">同一映射在两张不同的已审核架构图中出现后，会在这里汇总。</p>'}</div>
    <h3>已审核案例</h3>${product?'<button type="button" data-clear></button>':''}
    ${data.items.map(c=>`<article class="case-entry"><button type="button" class="buttonlink" onclick="openReferenceCase('${c.id}')">${content(c.title)}</button><p>${content(c.summary)}</p><small>${i18n.t(c.business_type)} · ${esc(c.reviewed_at.slice(0,10))}</small></article>`).join('')||'<p class="empty">没有匹配的参考案例</p>'}
    <div class="practice-tools"><button type="button" data-prev ${data.page<=1?'disabled':''}>上一页</button><span>${data.page} / ${Math.max(1,Math.ceil(data.total/12))}</span><button type="button" data-next ${data.page*12>=data.total?'disabled':''}>下一页</button></div>`;
  box.querySelectorAll('[data-pattern]').forEach(b=>b.onclick=()=>{const m=data.patterns[+b.dataset.pattern];showCases(1,m.product,m.service_id).catch(error)});
  const clear=box.querySelector('[data-clear]');
  if(clear){clear.textContent=i18n.t('清除筛选')+' · '+product;clear.onclick=()=>showCases().catch(error)}
  box.querySelector('[data-prev]').onclick=()=>showCases(data.page-1,product,service).catch(error);
  box.querySelector('[data-next]').onclick=()=>showCases(data.page+1,product,service).catch(error);
  i18n.apply(box);
}

async function uncompressedDrawing(source) {
  const invalid=()=>new Error(i18n.t('请使用单页、可编辑的 draw.io 架构图'));
  if(typeof source!=='string'||source.length>450000)throw invalid();
  const parse=s=>{const doc=new DOMParser().parseFromString(s,'application/xml');if(doc.doctype||doc.getElementsByTagName('parsererror').length)throw invalid();return doc};
  const doc=parse(source);
  if(doc.documentElement.tagName==='mxGraphModel')return '<mxfile compressed="false"><diagram id="huawei-target" name="Huawei Cloud">'+source.replace(/^\s*<\?xml[^?]*\?>/,'')+'</diagram></mxfile>';
  const pages=doc.getElementsByTagName('diagram');if(doc.documentElement.tagName!=='mxfile'||pages.length!==1)throw invalid();
  const diagram=pages[0];
  if(!diagram.firstElementChild){
    const binary=Uint8Array.from(atob(diagram.textContent.trim()),c=>c.charCodeAt(0));
    const reader=new Blob([binary]).stream().pipeThrough(new DecompressionStream('deflate-raw')).getReader();
    const chunks=[];let size=0;
    try{while(true){const part=await reader.read();if(part.done)break;size+=part.value.length;if(size>1350000)throw invalid();chunks.push(part.value)}}finally{await reader.cancel()}
    const graph=parse(decodeURIComponent(await new Blob(chunks).text()));
    if(graph.documentElement.tagName!=='mxGraphModel')throw invalid();
    diagram.replaceChildren(doc.importNode(graph.documentElement,true));
  }
  if(diagram.firstElementChild.tagName!=='mxGraphModel')throw invalid();
  doc.documentElement.setAttribute('compressed','false');
  const value=new XMLSerializer().serializeToString(doc);
  if(new Blob([value]).size>450000)throw invalid();
  return value;
}

async function openDrawingEditor(){
  const item=practiceInLanguage(practiceState.selected),endpoint='practices/'+item.id+'/drawing?lang='+item.language;
  try{
    const drawing=await api(endpoint),origin=drawing.editorOrigin;
    const dialog=document.createElement('dialog');dialog.className='drawio-editor';dialog.setAttribute('aria-label',i18n.t('华为云目标架构图'));
    dialog.innerHTML=`<div class="drawio-head"><strong>华为云目标架构图</strong><span class="drawio-status" role="status">正在连接 draw.io 编辑器…</span><button type="button" data-draft hidden>下载当前编辑稿</button><button type="button" data-close>关闭</button></div><iframe title="draw.io" referrerpolicy="no-referrer"></iframe>`;
    document.body.append(dialog);dialog.showModal();i18n.apply(dialog);
    const frame=dialog.querySelector('iframe'),status=dialog.querySelector('.drawio-status'),draft=dialog.querySelector('[data-draft]');
    let version=drawing.version,pending=null,lastXml=drawing.xml,initialized=false,exportTimer,saveFailed=false;
    const tell=data=>frame.contentWindow?.postMessage(JSON.stringify(data),origin);
    const msg=value=>{status.textContent=i18n.t(value)};
    const timeout=setTimeout(()=>{if(!initialized)msg('编辑器未连接，可关闭后下载 .drawio 离线编辑。')},18000);
    const resetExport=()=>{clearTimeout(exportTimer);pending=null};
    const close=()=>dialog.close();
    dialog.querySelector('[data-close]').onclick=()=>{if(!initialized||!pending&&confirm(i18n.t('关闭编辑器？请先保存需要保留的修改。')))close()};
    dialog.addEventListener('cancel',e=>{e.preventDefault();dialog.querySelector('[data-close]').click()});
    draft.onclick=()=>{const a=document.createElement('a'),u=URL.createObjectURL(new Blob([lastXml],{type:'application/xml'}));a.href=u;a.download='huawei-cloud-'+item.id+'-'+item.language+'.drawio';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
    async function receive(event){
      if(event.origin!==origin||event.source!==frame.contentWindow||typeof event.data!=='string')return;
      let data;try{data=JSON.parse(event.data)}catch{return}
      try{
        if(data.event==='init'){
          initialized=true;clearTimeout(timeout);tell({action:'load',xml:drawing.xml,title:item.title,autosave:0});
          msg('正在编辑目标架构');
        }else if(data.event==='save'&&!pending){
          pending={exit:!!data.exit};saveFailed=false;
          lastXml=data.xml;draft.hidden=false;
          pending.xml=await uncompressedDrawing(data.xml);msg('正在保存目标架构图…');
          tell({action:'export',format:'png',xml:pending.xml,border:12,scale:1,background:'#ffffff'});
          exportTimer=setTimeout(()=>{resetExport();saveFailed=true;msg('预览生成超时，请重试或下载当前编辑稿。')},35000);
        }else if(data.event==='export'&&pending?.xml&&/^data:image\/png;base64,/.test(data.data)){
          clearTimeout(exportTimer);
          if(data.data.length>2796230)throw new Error(i18n.t('预览超过 2MB，请精简图形后保存。'));
          const saved=await api(endpoint,'POST',{version,language:item.language,xml:pending.xml,preview:data.data.split(',')[1]});
          version=saved.version;drawing.xml=pending.xml;
          const shouldExit=pending.exit;resetExport();draft.hidden=true;
          if(practiceState.selected?.id===item.id){const selected=practiceState.selected;selected.drawingVersions={...selected.drawingVersions,[item.language]:version};if(selected.language===item.language)selected.drawingVersion=version;renderPracticeDetail()}
          msg('目标架构图已保存');tell({action:'status',message:i18n.t('目标架构图已保存'),modified:false});
          if(shouldExit)close();
        }else if(data.event==='exit'){
          if(pending)pending.exit=true;else if(!saveFailed)close();
        }
      }catch(e){resetExport();saveFailed=true;draft.hidden=false;msg(e.message);tell({action:'status',message:i18n.t(e.message),modified:true})}
    }
    window.addEventListener('message',receive);
    dialog.addEventListener('close',()=>{clearTimeout(timeout);resetExport();window.removeEventListener('message',receive);dialog.remove()},{once:true});
    frame.referrerPolicy='origin';
    frame.src=origin+'/?embed=1&proto=json&spin=1&libraries=1&noSaveBtn=0&saveAndExit=1&noExitBtn=0&offline=1&stealth=1&lang='+item.language;
  }catch(e){error(e)}
}
