import fs from 'node:fs/promises';
import path from 'node:path';
import {randomBytes,createCipheriv,createDecipheriv,timingSafeEqual} from 'node:crypto';
import * as OTPAuth from 'otpauth';
import QRCode from 'qrcode';
import {digest,checkPassword,cookieToken,sessionCookie,auditAuth} from './auth.mjs';

const json=(body,status=200,headers={})=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8',...headers}});
export const mfaRequired=user=>!!user&&(user.roleId==='admin'||user.permissions.some(p=>['member.manage','role.manage'].includes(p)));
export function otpCounter(secret,code,last=-1,now=Date.now()){
 if(typeof code!=='string'||!/^\d{6}$/.test(code))return null;
 const otp=new OTPAuth.TOTP({secret:OTPAuth.Secret.fromBase32(secret),algorithm:'SHA1',digits:6,period:30});
 const delta=otp.validate({token:code,window:1,timestamp:now});
 if(delta===null)return null;
 const counter=Math.floor(now/30000)+delta;
 return counter>Number(last)?counter:null;
}
export const normalizeRecovery=value=>typeof value==='string'?value.toLowerCase().replace(/[-\s]/g,''):'';
export function recoveryIndex(code,hashes){
 const normalized=normalizeRecovery(code);
 if(!/^[a-f0-9]{32}$/.test(normalized))return -1;
 const target=Buffer.from(digest(normalized),'hex');
 return hashes.findIndex(h=>/^[a-f0-9]{64}$/.test(h)&&timingSafeEqual(target,Buffer.from(h,'hex')));
}
export async function createMfa({env,secure,enforce=true}){
 const dir=env.MFA_KEY_DIR||env.MAAS_KEY_DIR||path.join(path.dirname(env.UPLOAD_DIR||'.data/uploads'),'private');
 await fs.mkdir(dir,{recursive:true,mode:0o700});
 const filename=path.join(dir,'mfa.key');
 try{const f=await fs.open(filename,'wx',0o600);try{await f.writeFile(randomBytes(32));await f.sync()}finally{await f.close()}}catch(e){if(e.code!=='EEXIST')throw e}
 const key=await fs.readFile(filename);if(key.length!==32)throw new Error('Invalid MFA encryption key');
 function seal(secret,user){
  const iv=randomBytes(12),c=createCipheriv('aes-256-gcm',key,iv);
  c.setAAD(Buffer.from(user.email+':'+user.id));
  return [iv,Buffer.concat([c.update(secret,'utf8'),c.final()]),c.getAuthTag()].map(b=>b.toString('base64')).join('.');
 }
 function unseal(cipher,user){
  const [iv,data,tag]=cipher.split('.').map(x=>Buffer.from(x,'base64'));
  const d=createDecipheriv('aes-256-gcm',key,iv);d.setAAD(Buffer.from(user.email+':'+user.id));d.setAuthTag(tag);
  return Buffer.concat([d.update(data),d.final()]).toString('utf8');
 }
 const tokenHash=request=>digest(cookieToken(request,secure));
 async function row(client,user){
  return (await client.query('SELECT *,pending_expires>now() AS pending_valid FROM account_mfa WHERE email=? AND user_id=?',[user.email,user.id])).rows[0];
 }
 async function status(client,user,request){
  if(!user)return {required:false,enabled:false,verified:false};
  const r=await row(client,user),enabled=!!r?.enabled_at;
  const required=enforce&&(mfaRequired(user)||enabled);
  const s=enabled?(await client.query('SELECT mfa_version FROM session_mfa WHERE token_hash=?',[tokenHash(request)])).rows[0]:null;
  return {required,enabled,verified:enabled&&s?.mfa_version===r.version};
 }
 async function limited(client,user){
  const k='mfa:'+digest(user.email);
  await client.query("INSERT INTO login_limits(`key`,attempts,reset_at) VALUES(?,1,now()+INTERVAL 15 MINUTE) ON DUPLICATE KEY UPDATE attempts=IF(reset_at<now(),1,attempts+1),reset_at=IF(reset_at<now(),now()+INTERVAL 15 MINUTE,reset_at)",[k]);
  return Number((await client.query('SELECT attempts FROM login_limits WHERE `key`=? FOR UPDATE',[k])).rows[0].attempts)>10;
 }
 async function failed(client,user,message='验证码不正确、已使用或已过期'){
  await auditAuth(client,user.email,'MFA 验证失败');
  return json({error:message},400);
 }
 async function finish(client,user,request,version,extra={}){
  const token=randomBytes(32).toString('hex'),hash=digest(token);
  await client.query("INSERT INTO sessions(token_hash,email,expires_at) VALUES(?,?,now()+INTERVAL 8 HOUR)",[hash,user.email]);
  await client.query('INSERT INTO session_mfa(token_hash,mfa_version) VALUES(?,?)',[hash,version]);
  await client.query('DELETE FROM sessions WHERE token_hash=?',[tokenHash(request)]);
  await client.query('DELETE FROM login_limits WHERE `key`=?',['mfa:'+digest(user.email)]);
  return json({ok:true,...extra},200,{'Set-Cookie':sessionCookie(token,secure)});
 }
 async function route(client,request,user){
  const url=new URL(request.url);
  if(!url.pathname.startsWith('/api/auth/mfa/'))return null;
  if(!user)return json({error:'请先登录'},401);
  if(user.mustChangePassword&&!user.mfa?.enabled)return json({error:'请先修改初始密码',code:'PASSWORD_CHANGE_REQUIRED'},403);
  if(request.method!=='POST')return json({error:'请使用 POST'},405);
  const action=url.pathname.slice('/api/auth/mfa/'.length);
  if(!['enroll','confirm','verify'].includes(action))return json({error:'接口不存在'},404);
  const body=await request.json();
  const r=await row(client,user);
  if(action==='enroll'||action==='confirm'){
   if(r?.enabled_at)return json({error:'此账号已绑定验证器'},409);
   if(!mfaRequired(user))return json({error:'当前账号无需管理员验证'},403);
  }else if(!r?.enabled_at)return json({error:'请先绑定验证器'},409);
  if(await limited(client,user))return json({error:'尝试次数过多，请 15 分钟后重试'},429,{'Retry-After':'900'});
  if(action==='enroll'){
   const account=(await client.query('SELECT password_hash FROM accounts WHERE email=?',[user.email])).rows[0];
   if(!await checkPassword(body.password,account?.password_hash))return failed(client,user,'当前密码不正确');
   const secret=new OTPAuth.Secret({size:20}).base32;
   await client.query('INSERT INTO account_mfa(email,user_id,pending_cipher,pending_token_hash,pending_expires) VALUES(?,?,?,?,now()+INTERVAL 10 MINUTE) ON DUPLICATE KEY UPDATE user_id=VALUES(user_id),pending_cipher=VALUES(pending_cipher),pending_token_hash=VALUES(pending_token_hash),pending_expires=VALUES(pending_expires)',
    [user.email,user.id,seal(secret,user),tokenHash(request)]);
   const uri=new OTPAuth.TOTP({issuer:'Data Solutions Hub',label:user.email,algorithm:'SHA1',digits:6,period:30,secret:OTPAuth.Secret.fromBase32(secret)}).toString();
   await auditAuth(client,user.email,'开始绑定管理员验证器');
   return json({secret,qr:await QRCode.toDataURL(uri,{width:256,errorCorrectionLevel:'M'}),expiresIn:600});
  }
  if(action==='confirm'){
   if(!r?.pending_cipher||!r.pending_valid||r.pending_token_hash!==tokenHash(request))return json({error:'绑定已过期，请重新开始'},409);
   const counter=otpCounter(unseal(r.pending_cipher,user),body.code);
   if(counter===null)return failed(client,user);
   const codes=Array.from({length:8},()=>randomBytes(16).toString('hex').match(/.{4}/g).join('-'));
   const hashes=codes.map(x=>digest(normalizeRecovery(x)));
   await client.query('UPDATE account_mfa SET secret_cipher=pending_cipher,pending_cipher=NULL,pending_token_hash=NULL,pending_expires=NULL,enabled_at=now(),version=version+1,last_counter=?,recovery_hashes=? WHERE email=?',[counter,JSON.stringify(hashes),user.email]);
   // Revoke other sessions; a password-only session must not survive enrollment.
   await client.query('DELETE FROM sessions WHERE email=? AND token_hash<>?',[user.email,tokenHash(request)]);
   await auditAuth(client,user.email,'已启用管理员 MFA');
   return finish(client,user,request,r.version+1,{recoveryCodes:codes});
  }
  const hashes=JSON.parse(r.recovery_hashes||'[]');
  const recovery=recoveryIndex(body.code,hashes);
  if(recovery>=0){
   hashes.splice(recovery,1);
   await client.query('UPDATE account_mfa SET recovery_hashes=? WHERE email=?',[JSON.stringify(hashes),user.email]);
   await auditAuth(client,user.email,'使用一次性 MFA 恢复码登录');
  }else{
   const counter=otpCounter(unseal(r.secret_cipher,user),body.code,r.last_counter);
   if(counter===null)return failed(client,user);
   await client.query('UPDATE account_mfa SET last_counter=? WHERE email=?',[counter,user.email]);
   await auditAuth(client,user.email,'MFA 验证通过');
  }
  return finish(client,user,request,r.version);
 }
 return {status,route};
}
