function dictionary(field){return data.dictionaries?.find(d=>d.field===field)||defaultDictionary(DICTIONARY_SCHEMA.find(d=>d.field===field))}
function dictionaryLabel(field,value){const item=dictionary(field).items.find(i=>i.value===String(value));return item?(i18n.language==='en'?(item.en||item.zh):item.zh):String(value??'')}
function dictionaryValue(field,value){const item=dictionary(field).items.find(i=>[i.value,i.zh,i.en].filter(Boolean).includes(value));return item?.value??value}
function dictionaryDefault(field){return dictionary(field).items.find(i=>i.enabled)?.value??''}
function dictionaryContent(field,value,fallback=''){return value===null||value===undefined||value===''?`<span>${esc(fallback)}</span>`:`<span data-user-content ${!['bdName','saName'].includes(field)?`data-auto-translate="${esc(dictionaryLabel(field,value))}"`: ''} data-dictionary-field="${field}" data-dictionary-value="${esc(value)}">${esc(dictionaryLabel(field,value))}</span>`}
function dictionaryOptions(field,current,{blank=false,filter=false}={}){
 const dict=dictionary(field),items=dict.items.filter(i=>filter||i.enabled||i.value===String(current));
 if(current!==undefined&&current!==null&&current!==''&&!items.some(i=>i.value===String(current)))items.push({value:String(current),zh:String(current),en:String(current),enabled:false});
 return (blank?'<option value="">—</option>':'')+items.map(item=>`<option data-user-content data-dictionary-field="${field}" data-dictionary-value="${esc(item.value)}" ${!item.enabled?'data-inactive="true"':''} value="${esc(item.value)}" ${String(current)===item.value?'selected':''} ${!item.enabled&&!filter&&String(current)!==item.value?'disabled':''}>${esc(dictionaryLabel(field,item.value))}${!item.enabled?' '+i18n.t('（已停用）'):''}</option>`).join('');
}
function dictionaryField(label,name,value='',disabled=false,wide=false){
 const dict=dictionary(name),text=dictionaryLabel(name,value),id='dictionary-input-'+name;
 if(!dict.allowCustom)return `<div class="${wide?'wide':''}"><label for="${id}">${label}</label><select id="${id}" name="${name}" ${disabled?'disabled':''}>${dictionaryOptions(name,value,{blank:!dict.required})}</select></div>`;
 return `<div class="${wide?'wide':''}"><label for="${id}">${label}</label><input id="${id}" name="${name}" list="dictionary-list-${name}" value="${esc(text)}" data-dictionary-input="${name}" data-dictionary-value="${esc(value??'')}" data-rendered-value="${esc(text)}" ${disabled?'disabled':''} autocomplete="off">${translatedPreview(text,name)}<datalist id="dictionary-list-${name}">${dict.items.filter(i=>i.enabled).map(i=>`<option data-user-content data-dictionary-suggestion="${name}" data-dictionary-value="${esc(i.value)}" value="${esc(dictionaryLabel(name,i.value))}"></option>`).join('')}</datalist></div>`;
}
function refreshDictionaryLabels(){
 document.querySelectorAll('[data-dictionary-field]').forEach(el=>{el.textContent=dictionaryLabel(el.dataset.dictionaryField,el.dataset.dictionaryValue)+(el.dataset.inactive?' '+i18n.t('（已停用）'):'');if(el.hasAttribute('data-auto-translate'))el.dataset.autoTranslate=dictionaryLabel(el.dataset.dictionaryField,el.dataset.dictionaryValue)});
 document.querySelectorAll('[data-dictionary-suggestion]').forEach(el=>{el.value=dictionaryLabel(el.dataset.dictionarySuggestion,el.dataset.dictionaryValue)});
 document.querySelectorAll('[data-dictionary-input]').forEach(el=>{if(el.value===el.dataset.renderedValue){el.value=dictionaryLabel(el.dataset.dictionaryInput,el.dataset.dictionaryValue);el.dataset.renderedValue=el.value}});
}
function dictionariesHTML(){return `<div class="panel sectiongap"><div class="row"><div><h2>数据字典</h2><p class="subtitle">按字段维护可选项，无需修改代码。保存后重新打开表单即可使用。</p></div></div><div class="dictionary-grid">${DICTIONARY_SCHEMA.map(def=>{const dict=dictionary(def.field);return `<article class="dictionary-card"><h3>${def.name}</h3><p><span>${dict.extensible?'可新增选项':'流程固定选项'}</span> · <span>${dict.allowCustom?'允许手动填写':'仅字典选项'}</span></p><div class="row"><span class="subtitle">${dict.items.filter(i=>i.enabled).length} / ${dict.items.length} <span>已启用</span></span><button type="button" onclick="dictionaryForm('${def.field}')">维护选项</button></div></article>`}).join('')}</div></div>`}
let dictionaryDraft=null;
function dictionaryRows(){
 $('#dictionaryRows').innerHTML=dictionaryDraft.items.map((item,index)=>`<div class="dictionary-row" data-dictionary-row="${index}"><div><label for="dict-zh-${index}">中文名称</label><input id="dict-zh-${index}" data-property="zh" value="${esc(item.zh)}" maxlength="120" required></div><div><label for="dict-en-${index}">英文名称（可选）</label><input id="dict-en-${index}" data-property="en" value="${esc(item.en)}" maxlength="120"></div><div class="dictionary-row-actions"><label><input data-property="enabled" type="checkbox" ${item.enabled?'checked':''}>启用</label><button type="button" aria-label="上移" ${index===0?'disabled':''} onclick="moveDictionaryItem(${index},-1)">${uiIcon('up')}</button><button type="button" aria-label="下移" ${index===dictionaryDraft.items.length-1?'disabled':''} onclick="moveDictionaryItem(${index},1)">${uiIcon('down')}</button>${item.value?'':`<button type="button" aria-label="移除未保存选项" onclick="removeDictionaryItem(${index})">${uiIcon('close')}</button>`}</div></div>`).join('')||'<p class="empty">暂无选项，可新增或允许手动填写。</p>';
}
function captureDictionaryRows(){document.querySelectorAll('[data-dictionary-row]').forEach(row=>{const item=dictionaryDraft.items[+row.dataset.dictionaryRow];item.zh=row.querySelector('[data-property=zh]').value;item.en=row.querySelector('[data-property=en]').value;item.enabled=row.querySelector('[data-property=enabled]').checked})}
function addDictionaryItem(){captureDictionaryRows();dictionaryDraft.items.push({value:'',zh:'',en:'',enabled:true});dictionaryRows();$('#dictionaryRows .dictionary-row:last-child input').focus()}
function moveDictionaryItem(index,offset){captureDictionaryRows();const next=index+offset;[dictionaryDraft.items[index],dictionaryDraft.items[next]]=[dictionaryDraft.items[next],dictionaryDraft.items[index]];dictionaryRows()}
function removeDictionaryItem(index){captureDictionaryRows();if(!dictionaryDraft.items[index].value)dictionaryDraft.items.splice(index,1);dictionaryRows()}
async function dictionaryForm(field){
 try{
  const latest=await api('dictionaries');data.dictionaries=latest;dictionaryDraft=structuredClone(dictionary(field));
  const def=DICTIONARY_SCHEMA.find(d=>d.field===field);
  openForm(`<h2><span>维护数据字典</span> · <span>${def.name}</span></h2><p class="viewnote">修改显示名称不会改变已有记录。停用后不再提供给新记录选择，已有记录保留。</p>${!def.extensible?'<div class="notice">这些选项关联业务统计，可改名、排序和停用，原有流程含义保持不变。</div>':''}${def.allowCustom?`<label class="dictionary-custom"><input type="checkbox" name="allowCustom" ${dictionaryDraft.allowCustom?'checked':''}>允许手动填写字典之外的内容</label>`:''}<div id="dictionaryRows"></div>${def.extensible?'<button type="button" class="sectiongap" onclick="addDictionaryItem()">' + uiIcon('plus') + '<span>新增选项</span></button>':''}${actions()}`,async fd=>{
   captureDictionaryRows();await api('admin/dictionaries','POST',{field,_version:dictionaryDraft._version,allowCustom:def.allowCustom?fd.get('allowCustom')==='on':false,items:dictionaryDraft.items});closeModal();await reload();toast('数据字典已保存，新打开的表单将使用最新选项');
  });dictionaryRows();
 }catch(e){error(e)}
}
document.addEventListener('languagechange',refreshDictionaryLabels);
