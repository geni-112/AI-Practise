const $=selector=>document.querySelector(selector);
const form=$('#loginForm'),error=$('#loginError'),button=$('#loginButton');
let mustChangePassword=false,profileVersion,mfaMode='',recoveryCodes=[];
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
  $('#mfaPanel').hidden=true;form.hidden=false;mfaMode='';
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
      await continueSession(await auth('status'));
    }
  }catch(e){
    if(e.status===401&&mustChangePassword)showForm(false,$('#email').value);
    error.textContent=e.message;
  }finally{button.disabled=false;window.i18n.apply()}
});
$('#signOut').addEventListener('click',async()=>{
  try{await auth('logout',{});clearMfa();showForm(false);error.textContent=''}catch(e){error.textContent=e.message}
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
    if(status.authenticated&&status.mfa?.required&&!status.mfa.verified&&(!status.mustChangePassword||status.mfa.enabled))showMfa(status);
    else showForm(!!status.mustChangePassword,status.email||'',status.displayName||'',status.profileVersion);
    if(legacyLink)error.textContent='链接设置密码已停用，请联系管理员重置初始密码';
  }catch(e){error.textContent=e.message}
  finally{button.disabled=false;window.i18n.apply()}
}
function clearMfa(){
 $('#mfaQr').removeAttribute('src');$('#mfaSecret').textContent='';$('#mfaRecoveryCodes').textContent='';
 $('#mfaPassword').value='';$('#mfaCode').value='';$('#mfaSaved').checked=false;recoveryCodes=[];
}
function showMfa(status){
 clearMfa();form.hidden=true;$('#mfaPanel').hidden=false;$('#loginNote').hidden=true;$('#signOut').hidden=false;
 mfaMode=status.mfa.enabled?'verify':'enroll-password';
 $('#authTitle').textContent=status.mfa.enabled?'管理员登录验证':'绑定管理员验证器';
 $('#authHint').textContent=status.mfa.enabled?'请输入验证器中的 6 位验证码，或使用一个恢复码。':'管理员账号需要完成两步验证。请先确认当前密码，然后绑定验证器。';
 $('#mfaStartForm').hidden=status.mfa.enabled;$('#mfaCodeForm').hidden=!status.mfa.enabled;
 $('#mfaEnrollment').hidden=true;$('#mfaRecovery').hidden=true;$('#mfaError').textContent='';
 window.i18n.apply();$(status.mfa.enabled?'#mfaCode':'#mfaPassword').focus();
}
async function continueSession(status){
 if(status.mfa?.required&&!status.mfa.verified&&(!status.mustChangePassword||status.mfa.enabled))showMfa(status);
 else if(status.mustChangePassword){clearMfa();showForm(true,status.email,status.displayName||'',status.profileVersion);$('#password').focus()}
 else location.assign(destination);
}
async function mfaSubmit(event,callback){
 event.preventDefault();const button=event.currentTarget.querySelector('button');button.disabled=true;$('#mfaError').textContent='';
 try{await callback()}catch(e){$('#mfaError').textContent=e.message;if(e.status===401){clearMfa();showForm(false);error.textContent=e.message}}
 finally{button.disabled=false;window.i18n.apply()}
}
$('#mfaStartForm').addEventListener('submit',e=>mfaSubmit(e,async()=>{
 const result=await auth('mfa/enroll',{password:$('#mfaPassword').value});$('#mfaPassword').value='';
 $('#mfaQr').src=result.qr;$('#mfaSecret').textContent=result.secret;$('#mfaStartForm').hidden=true;
 $('#mfaCodeForm').hidden=false;$('#mfaEnrollment').hidden=false;$('#mfaCodeLabel').textContent='验证器中的 6 位验证码';
 mfaMode='enroll-code';$('#mfaCode').focus();
}));
$('#mfaCodeForm').addEventListener('submit',e=>mfaSubmit(e,async()=>{
 const result=await auth(mfaMode==='enroll-code'?'mfa/confirm':'mfa/verify',{code:$('#mfaCode').value.trim()});
 $('#mfaCode').value='';
 if(result.recoveryCodes){
  clearMfa();recoveryCodes=result.recoveryCodes;$('#mfaCodeForm').hidden=true;$('#mfaRecovery').hidden=false;
  $('#authTitle').textContent='验证器已绑定';$('#authHint').textContent='恢复码只显示这一次。请保存到你自己的安全位置。';
  $('#mfaRecoveryCodes').textContent=recoveryCodes.join('\n');$('#mfaContinue').disabled=true;
 }else await continueSession(await auth('status'));
}));
$('#mfaSaved').addEventListener('change',()=>{$('#mfaContinue').disabled=!$('#mfaSaved').checked});
$('#mfaContinue').addEventListener('click',async()=>{if($('#mfaSaved').checked){clearMfa();await continueSession(await auth('status'))}});
$('#mfaDownload').addEventListener('click',()=>{
 const blob=new Blob(['Data Solutions Hub — recovery codes\n\n'+recoveryCodes.join('\n')+'\n'],{type:'text/plain;charset=utf-8'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='data-solutions-hub-recovery-codes.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
initialize();

$('#mfaRestart').addEventListener('click',async()=>{try{showMfa(await auth('status'))}catch(e){$('#mfaError').textContent=e.message;window.i18n.apply()}});
