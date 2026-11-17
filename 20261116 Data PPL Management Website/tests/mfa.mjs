import assert from 'node:assert/strict';
import * as OTPAuth from 'otpauth';
import {otpCounter,recoveryIndex,normalizeRecovery,mfaRequired} from '../server/mfa.mjs';
import {digest} from '../server/auth.mjs';
const secret=OTPAuth.Secret.fromUTF8('12345678901234567890').base32;
const otp=new OTPAuth.TOTP({secret:OTPAuth.Secret.fromBase32(secret),digits:6,period:30,algorithm:'SHA1'});
const now=59000,code=otp.generate({timestamp:now});
assert.equal(code,'287082'); // RFC 6238 SHA1 vector, truncated to 6 digits.
assert.equal(otpCounter(secret,code,-1,now),1);
assert.equal(otpCounter(secret,code,1,now),null);
assert.equal(otpCounter(secret,code,-1,now+90000),null);
assert.equal(otpCounter(secret,'abcdef',-1,now),null);
assert.equal(otpCounter(secret,'2870820',-1,now),null);
const recovery='abcd-1234-abcd-1234-abcd-1234-abcd-1234';
assert.equal(recoveryIndex(recovery.toUpperCase(),[digest(normalizeRecovery(recovery))]),0);
assert.equal(recoveryIndex(recovery,[]),-1);
assert.equal(recoveryIndex('123456',[digest('123456')]),-1);
assert.equal(mfaRequired({roleId:'admin',permissions:[]}),true);
assert.equal(mfaRequired({roleId:'custom',permissions:['member.manage']}),true);
assert.equal(mfaRequired({roleId:'sa',permissions:['project.edit']}),false);
console.log('MFA: RFC vector, replay/expiry checks, recovery format and privilege policy passed');

assert.equal(mfaRequired({roleId:'custom',permissions:['role.manage']}),true);
