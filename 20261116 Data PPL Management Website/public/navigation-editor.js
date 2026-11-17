let navigationDraft=null;
let navigationDrag=null;
const navElement=id=>document.getElementById(id);

function renderWorkspaceNavigation() {
  clearNavigationDrag();
  const nav=navElement('nav'),editing=!!navigationDraft,busy=!!navigationDraft?.saving;
  const items=orderedWorkspaceMenus(editing?navigationDraft.order:data.navigation?.order);
  navElement('navEdit').hidden=user.roleId!=='admin'||editing;
  navElement('navHint').hidden=!editing;
  navElement('navActions').hidden=!editing;
  navElement('navCancel').disabled=busy;
  navElement('navSave').disabled=busy||!editing||navigationDraft.order.every((id,i)=>id===navigationDraft.original[i]);
  nav.classList.toggle('nav-editing',editing);
  if(!editing){
    nav.innerHTML=items.filter(menu=>canSeeWorkspaceMenu(user,menu)).map(menu=>
      `<button type="button" data-menu-id="${menu.id}" class="${page===menu.id?'active':''}" ${page===menu.id?'aria-current="page"':''} onclick="go('${menu.id}')"><span aria-hidden="true">${menu.icon}</span>${menu.label}</button>`).join('');
    return;
  }
  nav.innerHTML=items.map((menu,index)=>{
    const label=i18n.t(menu.label),title=action=>esc(i18n.t(action)+' · '+label);
    return `<div class="nav-sort-row" data-menu-id="${menu.id}">
      <button type="button" class="nav-grip" data-nav-grip title="${title('拖动排序')}" aria-label="${title('拖动排序')}" ${busy?'disabled':''}><i aria-hidden="true">⠿</i><b>${menu.label}</b></button>
      <button type="button" class="nav-step" data-step="-1" aria-label="${title('上移')}" title="${title('上移')}" ${busy||index===0?'disabled':''}>↑</button>
      <button type="button" class="nav-step" data-step="1" aria-label="${title('下移')}" title="${title('下移')}" ${busy||index===items.length-1?'disabled':''}>↓</button></div>`;
  }).join('');
}

function navDraftFrom(saved) {
  const order=orderedWorkspaceMenus(saved?.order).map(menu=>menu.id);
  return {order,original:[...order],version:saved?._version||0,saving:false};
}
function focusMenuGrip(id) {
  navElement('nav').querySelector('[data-menu-id="'+id+'"] [data-nav-grip]')?.focus({preventScroll:true});
}
function enterNavigationEdit() {
  if(user.roleId!=='admin'||navigationDraft)return;
  navigationDraft=navDraftFrom(data.navigation);
  navElement('navFeedback').textContent='';
  renderWorkspaceNavigation();
  focusMenuGrip(navigationDraft.order.includes(page)?page:navigationDraft.order[0]);
}
function finishNavigationEdit() {
  clearNavigationDrag();
  navigationDraft=null;
  navElement('navFeedback').textContent='';
  renderWorkspaceNavigation();
  navElement('navEdit').focus();
}
function moveNavigationItem(id,index) {
  const order=navigationDraft.order,old=order.indexOf(id);
  if(old<0||index<0||index>=order.length||old===index)return;
  order.splice(old,1);order.splice(index,0,id);
  const row=navList.querySelector('[data-menu-id="'+id+'"]');
  const next=order[index+1];
  navList.insertBefore(row,next?navList.querySelector('[data-menu-id="'+next+'"]'):null);
  for(const [pos,entry] of Array.from(navList.children).entries()){
    entry.querySelector('[data-step="-1"]').disabled=pos===0;
    entry.querySelector('[data-step="1"]').disabled=pos===order.length-1;
  }
  navElement('navSave').disabled=order.every((key,i)=>key===navigationDraft.original[i]);
  focusMenuGrip(id);
  const label=i18n.t(workspaceMenus.find(menu=>menu.id===id).label);
  navElement('navFeedback').textContent=i18n.language==='en'?`${label} moved to position ${index+1} of ${order.length}.`:`已将“${label}”移至第 ${index+1} 位，共 ${order.length} 项。`;
}
async function saveNavigationOrder() {
  const draft=navigationDraft;
  if(!draft||draft.saving)return;
  clearNavigationDrag();
  draft.saving=true;renderWorkspaceNavigation();
  try{
    data.navigation=await api('admin/navigation','POST',{order:draft.order,_version:draft.version});
    finishNavigationEdit();toast(i18n.t('导航顺序已保存'));
  }catch(err){
    let message=err.message;
    if(err.status===409){
      try{
        data.navigation=await api('navigation');
        navigationDraft=navDraftFrom(data.navigation);
        message='另一位管理员已保存排序。已载入最新顺序，请重新调整。';
      }catch(refreshError){message=refreshError.message}
    }
    navigationDraft.saving=false;renderWorkspaceNavigation();
    navElement('navFeedback').textContent=i18n.t(message);
  }
}

const navList=navElement('nav');
function clearNavigationDrag() {
  const drag=navigationDrag;if(!drag)return;
  navigationDrag=null;
  if(drag.frame)cancelAnimationFrame(drag.frame);
  if(drag.handle.hasPointerCapture(drag.pointerId))drag.handle.releasePointerCapture(drag.pointerId);
  navList.querySelectorAll('.nav-dragging,.nav-drop-before,.nav-drop-after').forEach(row=>row.classList.remove('nav-dragging','nav-drop-before','nav-drop-after'));
}
function updateDropTarget(drag) {
  const rows=[...navList.querySelectorAll('.nav-sort-row')].filter(row=>row!==drag.row);
  const before=rows.find(row=>{const box=row.getBoundingClientRect();return drag.y<box.top+box.height/2});
  rows.forEach(row=>{
    row.classList.toggle('nav-drop-before',row===before);
    row.classList.toggle('nav-drop-after',!before&&row===rows.at(-1));
  });
  return before?rows.indexOf(before):rows.length;
}
function scrollWhileDragging() {
  const drag=navigationDrag;if(!drag)return;
  drag.frame=0;
  const box=navList.getBoundingClientRect();
  if(drag.x<box.left||drag.x>box.right)return;
  const speed=drag.y<box.top+28?-7:drag.y>box.bottom-28?7:0,was=navList.scrollTop;
  if(!speed)return;
  navList.scrollTop+=speed;
  if(navList.scrollTop!==was){updateDropTarget(drag);drag.frame=requestAnimationFrame(scrollWhileDragging)}
}
// The grip owns this gesture. Suppress its synthetic tap so a rapid tap on
// Save after a touch drag is delivered to the button on the first press.
navList.addEventListener('touchstart',event=>{
  if(event.touches.length===1&&event.target.closest('[data-nav-grip]'))event.preventDefault();
},{passive:false});
navList.addEventListener('pointerdown',event=>{
  const handle=event.target.closest('[data-nav-grip]');
  if(!handle||!navigationDraft||navigationDraft.saving||navigationDrag||!event.isPrimary||event.button!==0)return;
  navigationDrag={row:handle.closest('.nav-sort-row'),handle,pointerId:event.pointerId,startY:event.clientY,x:event.clientX,y:event.clientY,started:false,frame:0};
  handle.setPointerCapture(event.pointerId);
});
navList.addEventListener('pointermove',event=>{
  const drag=navigationDrag;if(!drag||drag.pointerId!==event.pointerId)return;
  drag.x=event.clientX;drag.y=event.clientY;
  if(!drag.started&&Math.abs(drag.y-drag.startY)<4)return;
  drag.started=true;drag.row.classList.add('nav-dragging');updateDropTarget(drag);
  if(!drag.frame)drag.frame=requestAnimationFrame(scrollWhileDragging);
});
navList.addEventListener('pointerup',event=>{
  const drag=navigationDrag;if(!drag||drag.pointerId!==event.pointerId)return;
  const box=navList.getBoundingClientRect();
  drag.y=event.clientY;
  const inside=event.clientX>=box.left&&event.clientX<=box.right&&drag.y>=box.top&&drag.y<=box.bottom;
  const target=drag.started&&inside?updateDropTarget(drag):-1,id=drag.row.dataset.menuId;
  clearNavigationDrag();
  if(target>=0)moveNavigationItem(id,target);
});
for(const type of ['pointercancel','lostpointercapture'])navList.addEventListener(type,event=>{
  if(event.pointerId===navigationDrag?.pointerId)clearNavigationDrag();
});
navList.addEventListener('click',event=>{
  const step=event.target.closest('[data-step]');if(!step||!navigationDraft||navigationDraft.saving)return;
  const id=step.closest('.nav-sort-row').dataset.menuId;
  moveNavigationItem(id,navigationDraft.order.indexOf(id)+Number(step.dataset.step));
});
navList.addEventListener('keydown',event=>{
  if(!navigationDraft||navigationDraft.saving)return;
  if(event.key==='Escape'){event.preventDefault();finishNavigationEdit();return}
  const grip=event.target.closest('[data-nav-grip]');
  if(!grip||!['ArrowUp','ArrowDown'].includes(event.key))return;
  event.preventDefault();
  const id=grip.closest('.nav-sort-row').dataset.menuId;
  moveNavigationItem(id,navigationDraft.order.indexOf(id)+(event.key==='ArrowUp'?-1:1));
});
navElement('navEdit').addEventListener('click',enterNavigationEdit);
navElement('navSave').addEventListener('click',saveNavigationOrder);
navElement('navCancel').addEventListener('click',finishNavigationEdit);
document.addEventListener('languagechange',()=>{
  if(!user)return;
  clearNavigationDrag();
  navElement('navFeedback').textContent='';
  renderWorkspaceNavigation();
  i18n.apply(navList);
});
