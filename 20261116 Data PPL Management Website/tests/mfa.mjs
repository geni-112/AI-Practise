import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {emailCodeHash,validEmailCode,mfaRequired,maskEmail} from '../server/mfa.mjs';
import {createEmailLogin,loginTopicName,soleEmailSubscriber} from '../server/email-login.mjs';
const key=randomBytes(32),user={id:'immutable-account-1',email:'admin@example.invalid'};
const code='004219',token='session-one',challenge='nonce-one',hash=emailCodeHash(key,user,token,challenge,code);
assert(validEmailCode(key,user,token,challenge,code,hash));
for(const [u,t,n,c] of [[{...user,id:'new-account'},token,challenge,code],[{...user,email:'another@example.invalid'},token,challenge,code],[user,'another-session',challenge,code],[user,token,'new-challenge',code],[user,token,challenge,'123456']])assert(!validEmailCode(key,u,t,n,c,hash));
assert(!validEmailCode(key,user,token,challenge,4219,hash));
assert(!validEmailCode(randomBytes(32),user,token,challenge,code,hash));
assert.equal(maskEmail(user.email),'ad***@example.invalid');
for(const role of [{roleId:'admin',permissions:[]},{roleId:'custom',permissions:['member.manage']},{roleId:'custom',permissions:['role.manage']}])assert(mfaRequired(role));
assert(!mfaRequired({roleId:'sa',permissions:['project.edit']}));
assert.throws(()=>soleEmailSubscriber([{protocol:'email',endpoint:'other@example.invalid',status:1}],user.email));
assert.throws(()=>soleEmailSubscriber([{protocol:'email',endpoint:user.email},{protocol:'https',endpoint:'https://elsewhere.invalid'}],user.email));
const env={MFA_EMAIL_REGION:'la-south-2',MFA_EMAIL_PROJECT_ID:'a'.repeat(32)};
const urn='urn:smn:'+env.MFA_EMAIL_REGION+':'+env.MFA_EMAIL_PROJECT_ID+':'+loginTopicName(user);
let subscriptions=[],added=0,published=[];
const sdk={
 async createTopic(r){assert.equal(r.body.name,loginTopicName(user));return {topic_urn:urn}},
 async listSubscriptionsByTopic(r){assert.equal(r.limit,2);return {subscriptions}},
 async addSubscription(r){assert.equal(r.body.endpoint,user.email);assert.equal(r.body.protocol,'email');added++;return {}},
 async publishMessage(r){published.push(r.body);return {message_id:'synthetic-message'}}
};
const provider=createEmailLogin(env,{clientFactory:()=>sdk});
assert.equal((await provider.send({user,code})).status,'confirmation_required');assert.equal(added,1);assert.equal(published.length,0);
subscriptions=[{protocol:'email',endpoint:user.email,status:1}];
assert.equal((await provider.send({user,code,language:'en'})).status,'sent');
assert.match(published[0].message,/004219/);assert.match(published[0].message,/5 minutes/);assert.equal(published[0].timeToLive,'300');
await provider.send({user,code,language:'zh'});assert.match(published[1].message,/验证码/);
subscriptions.push({protocol:'email',endpoint:'other@example.invalid',status:1});
await assert.rejects(provider.send({user,code}),e=>e.deliveryCode==='RECIPIENT_MISMATCH');assert.equal(published.length,2);
subscriptions=[{protocol:'sms',endpoint:'123456',status:1}];
await assert.rejects(provider.send({user,code}),e=>e.deliveryCode==='RECIPIENT_MISMATCH');
sdk.listSubscriptionsByTopic=()=>{throw new Error('Authorization: secret credential; OTP '+code)};
await assert.rejects(provider.send({user,code}),e=>!e.message.includes(code)&&!e.message.includes('secret'));
assert.notEqual(loginTopicName(user),loginTopicName({...user,id:'recreated-account'}));
await assert.rejects(createEmailLogin({}).send({user,code}),e=>e.deliveryCode==='NOT_CONFIGURED');
console.log('PASS: email OTP account/session binding, HMAC key, privilege rules, isolated SMN recipients, confirmation gate, delivery languages and safe errors');
