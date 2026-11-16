let reportIsArchived=false,templateRequest=0,templateTimer,templateDimensions=null;
function templateRequestBody(format='html'){
 const summary=document.querySelector('#summaryEdit')?.value;
 return {format,id:reportIsArchived?report.id:'current',period:report.period,type:report.type,repo:report.repo,language:i18n.language,summary:summary??report.summary,summaryGenerated:summary===undefined?report.summaryGenerated:report.summaryGenerated&&summary===lastSummaryValue,support:(document.querySelector('#supportEdit')?.value??(report.support||[]).join('\n')).split('\n'),contact:document.querySelector('#reportContact')?.value??report.contact??''};
}
async function refreshTemplatePreview(){
 const frame=document.querySelector('#templateFrame');if(!frame||!report)return;
 const token=++templateRequest,body=templateRequestBody();
 try{
  const result=await api('reports/template','POST',body);if(token!==templateRequest||frame!==document.querySelector('#templateFrame'))return;
  frame.srcdoc=result.html;templateDimensions=result;frame.style.width=result.width+'px';frame.style.height=result.height+'px';
  const summary=document.querySelector('#summaryEdit');if(summary&&body.summaryGenerated&&summary.value===body.summary){summary.value=result.summary;lastSummaryValue=result.summary;}
  frame.hidden=false;document.querySelector('#templateLoading')?.remove();applyTemplateZoom();
 }catch(e){const loading=document.querySelector('#templateLoading');if(loading)loading.textContent=e.message;else error(e)}
}
function applyTemplateZoom(){
 const frame=document.querySelector('#templateFrame'),stage=document.querySelector('#templateStage'),viewport=document.querySelector('#templateViewport');if(!frame||!stage||!templateDimensions)return;
 const selected=document.querySelector('#templateZoom')?.value||'1',scale=selected==='fit'?Math.min(1,(viewport.clientWidth-24)/templateDimensions.width):Number(selected);
 frame.style.transform=`scale(${scale})`;stage.style.width=templateDimensions.width*scale+'px';stage.style.height=templateDimensions.height*scale+'px';
}
document.addEventListener('input',event=>{if(['summaryEdit','supportEdit','reportContact'].includes(event.target.id)){clearTimeout(templateTimer);templateTimer=setTimeout(refreshTemplatePreview,500)}});
window.addEventListener('resize',applyTemplateZoom);
document.addEventListener('languagechange',()=>{if(document.querySelector('#templateFrame'))setTimeout(refreshTemplatePreview,0)});
