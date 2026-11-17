const $=selector=>document.querySelector(selector);
const form=$('#loginForm'),error=$('#loginError'),button=$('#loginButton');
let mustChangePassword=false,profileVersion;
const requestedPage=new URLSearchParams(location.search).get('next')||'';
const reviewSlug=/^review-([a-z0-9][a-z0-9-]{0,63})$/.exec(requestedPage)?.[1];
const destination=requestedPage==='maas'?'/settings?section=ai':requestedPage==='settings'?'/settings':reviewSlug?'/best-practices/reviews/'+reviewSlug:'/';
async function auth(path,body){
  const response=await fetch('/api/auth/'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  const result=await response.json();
  if(!response.ok)throw Object.assign(new Error(result.error||'操作失败'),{status:response.status});
  return result;
}
function showForm(required,email='',displayName='',version){
  profileVersion=version;
  $('#displayNameField').hidden=!required;$('#displayName').required=required;
  mustChangePassword=required;
  form.reset();$('#displayName').value=displayName;$('#email').value=email;$('#email').readOnly=required;
  $('#authTitle').textContent=required?'首次登录，请修改密码':'登录工作空间';
  $('#authHint').textContent=required?'请确认展示名并设置个人密码，完成后即可进入工作空间。':'使用管理员授权的账号登录。';
  $('#passwordLabel').textContent=required?'当前密码':'密码';
  $('#newPasswordField').hidden=!required;$('#newPassword').required=required;
  $('#repeatField').hidden=!required;$('#repeat').required=required;
  $('#signOut').hidden=!required;$('#loginNote').hidden=required;
  $('#loginActionLabel').textContent=required?'保存新密码':'登录';
  button.querySelector('.ui-icon').toggleAttribute('hidden',required);
  const params=new URLSearchParams();
  if(required)params.set('change-password','required');
  if(destination!=='/')params.set('next',requestedPage);
  history.replaceState(null,'','/login'+(params.size?'?'+params.toString():''));
  window.i18n.apply();
}
form.addEventListener('submit',async event=>{
  event.preventDefault();button.disabled=true;error.textContent='';
  try{
    if(mustChangePassword){
      const password=$('#newPassword').value;
      if(password!==$('#repeat').value)throw new Error('两次密码不一致');
      await auth('password',{currentPassword:$('#password').value,password,displayName:$('#displayName').value,_version:profileVersion});
      showForm(false,$('#email').value);
      $('#authHint').textContent='密码已更新，请使用新密码登录。';
      $('#password').focus();
    }else{
      const result=await auth('login',{email:$('#email').value,password:$('#password').value});
      if(result.mustChangePassword){showForm(true,$('#email').value,result.displayName||'',result.profileVersion);$('#password').focus()}
      else location.assign(destination);
    }
  }catch(e){
    if(e.status===401&&mustChangePassword)showForm(false,$('#email').value);
    error.textContent=e.message;
  }finally{button.disabled=false;window.i18n.apply()}
});
$('#signOut').addEventListener('click',async()=>{
  try{await auth('logout',{});showForm(false);error.textContent=''}catch(e){error.textContent=e.message}
});
window.addEventListener('hashchange',()=>{
  if(new URLSearchParams(location.hash.slice(1)).has('activate')){
    history.replaceState(null,'',location.pathname+location.search);
    error.textContent='链接设置密码已停用，请联系管理员重置初始密码';
    window.i18n.apply();
  }
});
async function initialize(){
  button.disabled=true;
  const legacyLink=new URLSearchParams(location.hash.slice(1)).has('activate');
  try{
    const status=await auth('status');
    showForm(!!status.mustChangePassword,status.email||'',status.displayName||'',status.profileVersion);
    if(legacyLink)error.textContent='链接设置密码已停用，请联系管理员重置初始密码';
  }catch(e){error.textContent=e.message}
  finally{button.disabled=false;window.i18n.apply()}
}
initialize();
