import {createHash} from 'node:crypto';
import {BasicCredentials} from '@huaweicloud/huaweicloud-sdk-core';
import {SmnClient,CreateTopicRequest,CreateTopicRequestBody,ListSubscriptionsByTopicRequest,AddSubscriptionRequest,AddSubscriptionRequestBody,PublishMessageRequest,PublishMessageRequestBody} from '@huaweicloud/huaweicloud-sdk-smn';

export const loginTopicName=user=>'data-ppl-login-'+createHash('sha256').update(user.id+':'+user.email).digest('hex').slice(0,32);
const failure=code=>Object.assign(new Error('Email delivery unavailable'),{deliveryCode:code});
export function soleEmailSubscriber(subscriptions,email){
 if(!Array.isArray(subscriptions)||subscriptions.length>1||subscriptions.some(s=>s.protocol!=='email'||s.endpoint?.toLowerCase()!==email))throw failure('RECIPIENT_MISMATCH');
 return subscriptions[0]||null;
}
export function createEmailLogin(env,{fetchImpl=fetch,clientFactory}={}){
 const region=env.MFA_EMAIL_REGION||'',project=env.MFA_EMAIL_PROJECT_ID||'';
 let cached,validUntil=0;
 async function client(){
  if(clientFactory)return clientFactory();
  if(!/^[a-z]{2}-[a-z]+-\d+$/.test(region)||!/^[a-f0-9]{32}$/.test(project))throw failure('NOT_CONFIGURED');
  if(cached&&Date.now()<validUntil)return cached;
  const r=await fetchImpl('http://169.254.169.254/openstack/latest/securitykey',{signal:AbortSignal.timeout(4000),redirect:'error'});
  if(!r.ok)throw failure('CREDENTIAL_UNAVAILABLE');
  const {credential:v}=await r.json();
  if(!v?.access||!v?.secret||!v?.securitytoken)throw failure('CREDENTIAL_UNAVAILABLE');
  const expiry=Date.parse(v.expires_at);
  if(!Number.isFinite(expiry)||expiry<Date.now()+60000)throw failure('CREDENTIAL_UNAVAILABLE');
  const credential=new BasicCredentials().withAk(v.access).withSk(v.secret).withSecurityToken(v.securitytoken).withProjectId(project);
  cached=SmnClient.newBuilder().withCredential(credential).withEndpoint('https://smn.'+region+'.myhuaweicloud.com')
   .withOptions({axiosRequestConfig:{timeout:5000,maxRedirects:0,proxy:false}}).build();
  validUntil=Math.min(expiry-60000,Date.now()+300000);
  return cached;
 }
 async function send({user,code,language='zh'}){
  try{
   const c=await client(),name=loginTopicName(user);
   const topic=await c.createTopic(new CreateTopicRequest().withBody(new CreateTopicRequestBody(name,'Data Solutions Hub sign-in')));
   const urn=topic.topic_urn||topic.topicUrn;
   if(urn!=='urn:smn:'+region+':'+project+':'+name)throw failure('TOPIC_MISMATCH');
   // One topic per immutable account. Never use a shared alert topic for OTPs.
   const response=await c.listSubscriptionsByTopic(new ListSubscriptionsByTopicRequest(urn).withLimit(2).withOffset(0));
   let sub=soleEmailSubscriber(response.subscriptions,user.email);
   if(!sub||Number(sub.status)!==1){
    // SMN reissues the confirmation if pending; application cooldown/quotas bound requests.
    await c.addSubscription(new AddSubscriptionRequest(urn).withBody(new AddSubscriptionRequestBody('email',user.email).withRemark('Account sign-in verification')));
    return {status:'confirmation_required'};
   }
   if(!/^\d{6}$/.test(code))throw failure('INVALID_CODE');
   const english=language==='en';
   const message=english
    ?'Your Data Solutions Hub sign-in code is: '+code+'\n\nValid for 5 minutes and for one use only. Enter it only on your Data Solutions Hub sign-in page. Do not share this code. If you did not request it, ignore this email.'
    :'数据专项作战平台登录验证码：'+code+'\n\n验证码 5 分钟内有效，只能使用一次。请仅在数据专项作战平台登录页面输入，不要向他人透露。如果不是本人操作，请忽略此邮件。';
   const sent=await c.publishMessage(new PublishMessageRequest(urn).withBody(new PublishMessageRequestBody()
    .withSubject(english?'Data Solutions Hub — sign-in code':'数据专项作战平台 — 登录验证码').withMessage(message).withTimeToLive('300')));
   if(!(sent.message_id||sent.messageId))throw failure('PROVIDER_RESPONSE');
   return {status:'sent'};
  }catch(e){
   if(e.deliveryCode)throw e;
   // SDK errors may include signed headers and bodies; never expose or log them.
   throw failure(e.httpStatusCode===403||e.statusCode===403?'PERMISSION_DENIED':'PROVIDER_UNAVAILABLE');
  }
 }
 return {send};
}
