const $=selector=>document.querySelector(selector);
const form=$('#loginForm'),error=$('#loginError'),button=$('#loginButton');
let mustChangePassword=false,profileVersion,cooldownTimer;
const requestedPage=new URLSearchParams(location.search).get('next')||'';
const reviewSlug=/^review-([a-z0-9][a-z0-9-]{0,63})$/.exec(requestedPage)?.[1];
const destination=requestedPage==='maas'?'/settings?section=ai':requestedPage==='settings'?'/settings':reviewSlug?'/best-practices/reviews/'+reviewSlug:'/';
async function auth(path,body){
  const response=await fetch('/api/auth/'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  const result=await response.json();
  if(!response.ok)throw Object.assign(new Error(result.error||'操作失败'),{status:response.status,retryAfter:Number(result.retryAfter)||Number(response.headers.get('retry-after'))||0});
  return result;
}
function showForm(required,email='',displayName='',version){
  $('#mfaPanel').hidden=true;form.hidden=false;
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
      const result=await auth('password',{currentPassword:$('#password').value,password,displayName:$('#displayName').value,_version:profileVersion});
      if(result.authenticated){await continueSession(await auth('status'));return}
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
    if(status.authenticated&&status.mfa?.required&&!status.mfa.verified&&(!status.mustChangePassword||status.mfa.enabled))await showMfa(status);
    else showForm(!!status.mustChangePassword,status.email||'',status.displayName||'',status.profileVersion);
    if(legacyLink)error.textContent='链接设置密码已停用，请联系管理员重置初始密码';
  }catch(e){error.textContent=e.message}
  finally{button.disabled=false;window.i18n.apply()}
}
function clearMfa(){
 clearInterval(cooldownTimer);$('#mfaCode').value='';$('#mfaNotice').textContent='';$('#mfaError').textContent='';
}
function setCooldown(seconds){
 clearInterval(cooldownTimer);let remaining=Math.max(0,Number(seconds)||0);
 function update(){ $('#mfaSend').disabled=remaining>0;$('#mfaCooldownRow').hidden=remaining===0;$('#mfaCooldown').textContent=String(remaining);if(remaining===0)clearInterval(cooldownTimer)}
 update();if(remaining>0)cooldownTimer=setInterval(()=>{remaining=Math.max(0,remaining-1);update()},1000);
}
function deliveryNotice(status){
 $('#mfaNotice').textContent=status==='confirmation_required'
  ?'首次收信请打开华为云确认邮件，确认订阅后再点击发送验证码。以后登录只需输入验证码。'
  :status==='sent'?'验证码已发送，5 分钟内有效。请查看收件箱或垃圾邮件。'
  :status==='failed'?'验证码邮件暂时无法发送，请稍后重试或联系管理员':'点击发送验证码，验证登录邮箱。';
}
async function sendCode(){
 $('#mfaSend').disabled=true;$('#mfaError').textContent='';
 try{
  const result=await auth('mfa/email/send',{language:window.i18n.language});
  if(result.alreadyVerified)return continueSession(await auth('status'));
  $('#mfaDestination').textContent=result.destination;deliveryNotice(result.status);
  setCooldown(result.retryAfter);$('#mfaCode').focus();
 }catch(e){
  setCooldown(e.retryAfter);$('#mfaError').textContent=e.message;
  if(e.status===401){clearMfa();showForm(false);error.textContent=e.message}
 }finally{window.i18n.apply()}
}
async function showMfa(status){
 clearMfa();form.hidden=true;$('#mfaPanel').hidden=false;$('#loginNote').hidden=true;$('#signOut').hidden=false;
 $('#authTitle').textContent='邮箱登录验证';
 $('#authHint').textContent='输入登录邮箱收到的 6 位验证码，无需扫码或安装验证器。';
 $('#mfaDestination').textContent=status.mfa.destination||status.email;
 deliveryNotice(status.mfa.deliveryStatus);setCooldown(status.mfa.retryAfter);
 window.i18n.apply();$('#mfaCode').focus();
 if(!status.mfa.retryAfter&&(!status.mfa.deliveryStatus||status.mfa.deliveryStatus==='none'))await sendCode();
}
async function continueSession(status){
 if(status.mfa?.required&&!status.mfa.verified)await showMfa(status);
 else if(status.mustChangePassword){clearMfa();showForm(true,status.email,status.displayName||'',status.profileVersion);$('#password').focus()}
 else location.assign(destination);
}
$('#mfaSend').addEventListener('click',sendCode);
$('#mfaCodeForm').addEventListener('submit',async event=>{
 event.preventDefault();const button=event.currentTarget.querySelector('button[type="submit"]');button.disabled=true;$('#mfaError').textContent='';
 try{
  await auth('mfa/email/verify',{code:$('#mfaCode').value.trim()});$('#mfaCode').value='';
  await continueSession(await auth('status'));
 }catch(e){
  $('#mfaError').textContent=e.message;
  if(e.status===401){clearMfa();showForm(false);error.textContent=e.message}
 }finally{button.disabled=false;window.i18n.apply()}
});
initialize();
