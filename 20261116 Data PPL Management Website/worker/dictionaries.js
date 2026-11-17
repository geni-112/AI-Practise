async function dictionaries(db){
 const saved=await all(db,'dictionary');
 return DICTIONARY_SCHEMA.map(def=>({...defaultDictionary(def),...saved.find(d=>d.field===def.field),name:def.name,extensible:!!def.extensible,required:!!def.required}));
}
async function saveDictionary(db,u,body){
 if(u.roleId!=='admin')fail(403,'仅管理员可维护数据字典');
 const def=DICTIONARY_SCHEMA.find(d=>d.field===body.field);
 if(!def||!Array.isArray(body.items)||body.items.length>200)fail(400,'字典内容无效');
 const old=await get(db,'dictionary:'+def.field,'dictionary'),previous=old||defaultDictionary(def);
 if(body._version!==previous._version)fail(409,'字典已被其他管理员更新，请重新打开后编辑');
 if(typeof body.allowCustom!=='boolean'||(!def.allowCustom&&body.allowCustom))fail(400,'字典填写方式无效');
 const values=new Set(),labels=new Set(),english=new Set();
 const items=body.items.map(item=>{
  if(!item||typeof item.zh!=='string'||!item.zh.trim()||item.zh.trim().length>120||typeof item.en!=='string'||item.en.trim().length>120||typeof item.enabled!=='boolean')fail(400,'请填写有效的字典名称');
  let value=item.value;
  if(value){if(!previous.items.some(i=>i.value===value))fail(400,'字典标识不可更改')}
  else {if(!def.extensible)fail(400,'流程选项只支持改名、排序和启停');value='option_'+crypto.randomUUID()}
  const zh=item.zh.trim(),en=item.en.trim();
  if(values.has(value)||labels.has(zh.toLowerCase())||(en&&english.has(en.toLowerCase())))fail(400,'字典选项名称不能重复');
  values.add(value);labels.add(zh.toLowerCase());if(en)english.add(en.toLowerCase());
  return {value,zh,en,enabled:item.enabled};
 });
 // Persisted values are never deleted: old records must remain understandable.
 if(previous.items.some(item=>!values.has(item.value)))fail(400,'已有选项请停用，不能删除');
 if((def.required||!body.allowCustom)&&!items.some(item=>item.enabled))fail(400,'请至少保留一个启用选项');
 const record={id:previous.id,field:def.field,allowCustom:body.allowCustom,items};
 if(old)await change(db,'dictionary',record,body._version);else await insert(db,'dictionary',record);
 await audit(db,u,'维护数据字典',def.name);
 return {...defaultDictionary(def),...record,_version:previous._version+1};
}
function validateDictionaryValue(list,field,value,oldValue,hasOld=false){
 if(hasOld&&String(value??'')===String(oldValue??''))return;
 const dict=list.find(d=>d.field===field);if(!dict)return;
 if(value===undefined||value===null||value===''){if(dict.required)fail(400,'字典字段不能为空：'+dict.name);return}
 const item=dict.items.find(i=>i.value===String(value));
 if(item?.enabled)return;
 if(item&&!item.enabled)fail(400,'字典选项已停用，请重新选择：'+dict.name);
 if(dict.allowCustom&&typeof value==='string'&&value.length<=2000&&!value.startsWith('option_'))return;
 fail(400,'请从数据字典选择有效选项：'+dict.name);
}
function validateProjectDictionaries(list,p,previous,names=new Map()){
 for(const field of ['type','cloud','repo','industry','vendor','bdName','saName','confidence','stage','status','risk']){
  if(field==='bdName'&&p.bdNameManual)continue;
  if(['bdName','saName'].includes(field)&&p[field.slice(0,2)+'Id']&&(p[field]===p[field.slice(0,2)+'AccountName']||p[field]===names.get(p[field.slice(0,2)+'Id'])))continue;
  if(field==='saName'&&p.saAccountEmail&&p.saName===p.saAccountEmail)continue;
  validateDictionaryValue(list,field,p[field],previous?.[field],!!previous);
 }
 for(const [key,value]of Object.entries(p.milestones||{}))validateDictionaryValue(list,'milestoneState',value,previous?.milestones?.[key],!!previous&&Object.hasOwn(previous.milestones||{},key));
 for(const entry of p.actuals||[])validateDictionaryValue(list,'revenueKind',entry.kind,entry.kind,!!previous?.actuals?.some(a=>a.kind===entry.kind&&a.month===entry.month&&a.amount===entry.amount));
}
