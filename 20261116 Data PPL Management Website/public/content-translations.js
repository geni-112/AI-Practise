(()=>{
 const cache=new Map(),han=text=>/\p{Script=Han}/u.test(text);
 let timer=null,busy=false,generation=0,retryRequested=false;
 function chunks(text){
  const out=[];let rest=text;
  while(rest.length>1200){
   let cut=rest.slice(0,1100).search(/[。！？；\n][^。！？；\n]*$/u);
   if(cut<400)cut=1100;else cut++;
   out.push(rest.slice(0,cut));rest=rest.slice(cut);
  }
  if(rest)out.push(rest);
  return out;
 }
 function nodes(){return [...document.querySelectorAll('[data-auto-translate]')].filter(el=>!el.closest('script,style,input,textarea,select,datalist')&&el.getClientRects().length)}
 function state(text){
  if(!han(text)||i18n.t(text)!==text)return {status:'ready',translation:i18n.t(text)};
  return cache.get(text)||{status:'missing'};
 }
 function render(){
  const targets=nodes(),english=i18n.language==='en';let pending=0,failed=0;
  for(const el of targets){
   const original=el.dataset.autoTranslate;let output=original;
   if(english&&han(original)){
    const parts=chunks(original).map(text=>({text,...state(text)}));
    if(parts.every(part=>part.status==='ready'))output=parts.map(part=>part.translation).join(' ');
    else if(parts.some(part=>part.status==='failed'||part.error==='DAILY_LIMIT'||part.status==='unavailable'))failed++;
    else pending++;
    if(el.title!==original)el.title=original;
   }else if(el.hasAttribute('title'))el.removeAttribute('title');
   if(el.textContent!==output)el.textContent=output;
  }
  let status=document.querySelector('#contentTranslationStatus');
  if(!status){
   status=document.createElement('div');status.id='contentTranslationStatus';status.className='content-translation-status';status.setAttribute('role','status');status.setAttribute('data-user-content','');
   document.querySelector('main')?.insertBefore(status,document.querySelector('#app'));
  }
  const visible=english&&(pending||failed);
  status.hidden=!visible;
  if(visible){
   const message=failed?'Some text could not be translated. The original is shown.':'Translating content into English…';
   const existing=status.querySelector('span');
   if(!existing||existing.textContent!==message){
    status.replaceChildren();const label=document.createElement('span');label.textContent=message;status.append(label);
    if(failed){const button=document.createElement('button');button.type='button';button.textContent='Retry translation';button.addEventListener('click',()=>{retryRequested=true;schedule(0)});status.append(button)}
   }
  }
  return targets;
 }
 function schedule(delay=180){if(timer!==null)return;timer=setTimeout(()=>{timer=null;refresh().catch(()=>{})},delay)}
 async function refresh(){
  const targets=render();if(i18n.language!=='en'||busy||typeof user==='undefined'||!user)return;
  const retry=retryRequested;retryRequested=false;
  const wanted=[...new Set(targets.flatMap(el=>chunks(el.dataset.autoTranslate)))].filter(text=>han(text)&&i18n.t(text)===text);
  const candidates=wanted.filter(text=>{const item=state(text);return !['ready','failed','unavailable'].includes(item.status)&&item.error!=='DAILY_LIMIT'||retry&&item.status!=='ready'});
  const texts=[];let size=0;
  for(const text of candidates){if(texts.length>=40||size+text.length>16000)break;texts.push(text);size+=text.length}
  if(!texts.length)return;
  busy=true;const current=generation;
  try{
   const response=await api('content-translations','POST',{language:'en',texts,...(retry?{retry:true}:{})});
   if(current!==generation)return;
   if(response.state==='unavailable')for(const text of texts)cache.set(text,{status:'unavailable'});
   for(const entry of response.entries||[])if(texts.includes(entry.text))cache.set(entry.text,entry);
  }catch(e){if(current===generation)for(const text of texts)cache.set(text,{status:'failed'});}
  finally{busy=false;render();if(i18n.language==='en')schedule(2200)}
 }
 const observer=new MutationObserver(()=>schedule());
 observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['data-auto-translate']});
 document.addEventListener('languagechange',()=>{generation++;if(timer!==null){clearTimeout(timer);timer=null}render();schedule(0)});
 window.contentTranslation={text(value){const text=String(value??'');if(i18n.language!=='en')return text;return chunks(text).map(part=>state(part).translation||part).join(' ')},refresh(){schedule(0)}};
 schedule();
})();
