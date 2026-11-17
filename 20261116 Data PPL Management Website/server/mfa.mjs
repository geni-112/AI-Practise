import fs from 'node:fs/promises';
import path from 'node:path';
import {randomBytes,randomInt,createHmac,timingSafeEqual} from 'node:crypto';
import {digest,cookieToken,sessionCookie,auditAuth} from './auth.mjs';
import {transaction} from './database.mjs';
import {createEmailLogin} from './email-login.mjs';

const json=(body,status=200,headers={})=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8',...headers}});
export const mfaRequired=user=>!!user&&(user.roleId==='admin'||user.permissions.some(p=>['member.manage','role.manage'].includes(p)));
export const maskEmail=email=>{const [name,domain]=email.split('@');return name.slice(0,Math.min(2,name.length))+'***@'+domain};
export const emailCodeHash=(key,user,token,challenge,code)=>createHmac('sha256',key).update(JSON.stringify([user.id,user.email,token,challenge,code])).digest('hex');
export function validEmailCode(key,user,token,challenge,code,expected){
 if(typeof code!=='string'||!/^\d{6}$/.test(code)||!/^[a-f0-9]{64}$/.test(expected||''))return false;
 return timingSafeEqual(Buffer.from(emailCodeHash(key,user,token,challenge,code),'hex'),Buffer.from(expected,'hex'));
}
export async function createMfa({env,secure,pool,enforce=true,emailProvider}){
 const dir=env.MFA_KEY_DIR||env.MAAS_KEY_DIR||path.join(path.dirname(env.UPLOAD_DIR||'.data/uploads'),'private');
 await fs.mkdir(dir,{recursive:true,mode:0o700});
 const filename=path.join(dir,'mfa.key');
 try{const f=await fs.open(filename,'wx',0o600);try{await f.writeFile(randomBytes(32));await f.sync()}finally{await f.close()}}catch(e){if(e.code!=='EEXIST')throw e}
 const key=await fs.readFile(filename);if(key.length!==32)throw new Error('Invalid MFA key');
 const provider=emailProvider||createEmailLogin(env);
 const tokenHash=request=>digest(cookieToken(request,secure));
 async function status(client,user,request){
  if(!user)return {required:false,enabled:false,verified:false,method:'email'};
  const legacy=(await client.query('SELECT enabled_at FROM account_mfa WHERE email=? AND user_id=?',[user.email,user.id])).rows[0];
  const required=enforce&&(mfaRequired(user)||!!legacy?.enabled_at);
  const proof=(await client.query('SELECT token_hash FROM session_email_mfa WHERE token_hash=?',[tokenHash(request)])).rows[0];
  const account=(await client.query('SELECT GREATEST(0,60-TIMESTAMPDIFF(SECOND,last_requested_at,now())) AS cooldown FROM account_email_mfa WHERE email=? AND user_id=?',[user.email,user.id])).rows[0];
  const challenge=(await client.query('SELECT delivery_status,expires_at>now() AS valid FROM email_mfa_challenges WHERE token_hash=? AND user_id=?',[tokenHash(request),user.id])).rows[0];
  return {required,enabled:required,verified:!!proof,method:'email',destination:maskEmail(user.email),
   retryAfter:Number(account?.cooldown)||0,deliveryStatus:challenge?.valid?challenge.delivery_status:'none'};
 }
 async function limited(client,user,kind,max,minutes){
  const k='mfa-email-'+kind+':'+digest(user.email);
  await client.query('INSERT INTO login_limits(\`key\`,attempts,reset_at) VALUES(?,1,now()+INTERVAL '+minutes+' MINUTE) ON DUPLICATE KEY UPDATE attempts=IF(reset_at<now(),1,attempts+1),reset_at=IF(reset_at<now(),now()+INTERVAL '+minutes+' MINUTE,reset_at)',[k]);
  return Number((await client.query('SELECT attempts FROM login_limits WHERE \`key\`=? FOR UPDATE',[k])).rows[0].attempts)>max;
 }
 async function finish(client,user,request){
  const token=randomBytes(32).toString('hex'),hash=digest(token);
  await client.query('INSERT INTO sessions(token_hash,email,expires_at) VALUES(?,?,now()+INTERVAL 8 HOUR)',[hash,user.email]);
  await client.query('INSERT INTO session_email_mfa(token_hash) VALUES(?)',[hash]);
  await client.query('DELETE FROM sessions WHERE token_hash=?',[tokenHash(request)]);
  await client.query('DELETE FROM login_limits WHERE \`key\`=?',['mfa-email-verify:'+digest(user.email)]);
  await auditAuth(client,user.email,'邮箱验证码验证通过');
  return json({ok:true},200,{'Set-Cookie':sessionCookie(token,secure)});
 }
 async function route(client,request,user){
  const url=new URL(request.url);
  if(!url.pathname.startsWith('/api/auth/mfa/'))return null;
  if(!user)return json({error:'请先登录'},401);
  if(request.method!=='POST')return json({error:'请使用 POST'},405);
  const action=url.pathname.slice('/api/auth/mfa/'.length);
  if(!['email/send','email/verify'].includes(action))return json({error:'已改用邮箱验证码，请刷新登录页面',code:'EMAIL_MFA_REQUIRED'},410);
  if(!user.mfa?.required)return json({error:'当前账号无需管理员验证'},403);
  if(user.mfa.verified)return json({ok:true,alreadyVerified:true});
  const body=await request.json(),hash=tokenHash(request);
  if(action==='email/send'){
   const state=(await client.query('SELECT GREATEST(0,60-TIMESTAMPDIFF(SECOND,last_requested_at,now())) AS cooldown FROM account_email_mfa WHERE email=?',[user.email])).rows[0];
   if(Number(state?.cooldown)>0)return json({error:'请稍后再发送验证码',retryAfter:Number(state.cooldown)},429,{'Retry-After':String(state.cooldown)});
   if(await limited(client,user,'send',20,60))return json({error:'验证码发送过于频繁，请一小时后重试'},429,{'Retry-After':'3600'});
   const code=String(randomInt(0,1000000)).padStart(6,'0'),id=randomBytes(16).toString('hex');
   await client.query('INSERT INTO account_email_mfa(email,user_id,last_requested_at) VALUES(?,?,now()) ON DUPLICATE KEY UPDATE user_id=VALUES(user_id),last_requested_at=now()',[user.email,user.id]);
   await client.query("INSERT INTO email_mfa_challenges(token_hash,challenge_id,user_id,code_hash,expires_at) VALUES(?,?,?,?,now()+INTERVAL 5 MINUTE) ON DUPLICATE KEY UPDATE challenge_id=VALUES(challenge_id),user_id=VALUES(user_id),code_hash=VALUES(code_hash),expires_at=VALUES(expires_at),attempts=0,delivery_status='queued'",
    [hash,id,user.id,emailCodeHash(key,user,hash,id,code)]);
   // Release database locks before making any external mail request.
   return {afterCommit:async()=>{
    let delivery;
    try{delivery=await provider.send({user:{id:user.id,email:user.email},code,language:body.language==='en'?'en':'zh'});
     if(!['sent','confirmation_required'].includes(delivery.status))throw new Error('Unexpected delivery result');
    }catch(e){
     const safeCodes=['NOT_CONFIGURED','CREDENTIAL_UNAVAILABLE','PERMISSION_DENIED','RECIPIENT_MISMATCH','TOPIC_MISMATCH','PROVIDER_RESPONSE'];
     delivery={status:'failed',code:safeCodes.includes(e.deliveryCode)?e.deliveryCode:'PROVIDER_UNAVAILABLE'};
     console.error(JSON.stringify({security_event:'email_delivery_failed',provider_code:delivery.code}));
    }
    const saved=await transaction(pool,async c=>{
     await c.query('SELECT email FROM accounts WHERE email=? FOR UPDATE',[user.email]);
     const result=await c.query("UPDATE email_mfa_challenges SET delivery_status=?,code_hash=IF(?='sent',code_hash,NULL) WHERE token_hash=? AND challenge_id=? AND user_id=?",
       [delivery.status,delivery.status,hash,id,user.id]);
     if(result.rowCount)await auditAuth(c,user.email,delivery.status==='sent'?'已发送登录邮箱验证码':delivery.status==='confirmation_required'?'等待登录邮箱确认收信订阅':'登录验证码邮件发送失败');
     return result.rowCount;
    });
    if(!saved)return json({error:'登录已过期，请重新登录'},401);
    if(delivery.status==='failed')return json({error:'验证码邮件暂时无法发送，请稍后重试或联系管理员',code:'EMAIL_DELIVERY_FAILED',retryAfter:60},503);
    return json({ok:true,status:delivery.status,destination:maskEmail(user.email),retryAfter:60,expiresIn:300});
   }};
  }
  if(await limited(client,user,'verify',10,15))return json({error:'尝试次数过多，请 15 分钟后重试'},429,{'Retry-After':'900'});
  const challenge=(await client.query('SELECT *,expires_at>now() AS valid FROM email_mfa_challenges WHERE token_hash=? AND user_id=?',[hash,user.id])).rows[0];
  if(!challenge||!challenge.valid||challenge.delivery_status!=='sent'||challenge.attempts>=5||!validEmailCode(key,user,hash,challenge.challenge_id,body.code,challenge.code_hash)){
   if(challenge)await client.query('UPDATE email_mfa_challenges SET attempts=attempts+1,code_hash=IF(attempts>=5,NULL,code_hash) WHERE token_hash=?',[hash]);
   await auditAuth(client,user.email,'邮箱验证码验证失败');
   return json({error:'验证码不正确、已使用或已过期'},400);
  }
  return finish(client,user,request);
 }
 return {status,route};
}
