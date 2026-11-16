import { randomBytes, createHash, scrypt as scryptCallback, timingSafeEqual, randomUUID } from 'node:crypto';
import { promisify } from 'node:util';
import {readFile} from 'node:fs/promises';
const scrypt = promisify(scryptCallback);
export const digest = value => createHash('sha256').update(value).digest('hex');
const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type':'application/json; charset=utf-8', ...headers } });
export const authError = (status, message) => Object.assign(new Error(message), { status });
export async function readInitialPassword(env) {
  const password = env.INITIAL_ACCOUNT_PASSWORD_FILE
    ? (await readFile(env.INITIAL_ACCOUNT_PASSWORD_FILE, 'utf8')).replace(/\r?\n$/, '')
    : env.INITIAL_ACCOUNT_PASSWORD;
  if (typeof password !== 'string' || password.length < 10 || password.length > 128 || /[\r\n]/.test(password)) {
    throw new Error('Configure INITIAL_ACCOUNT_PASSWORD_FILE or a private INITIAL_ACCOUNT_PASSWORD (10–128 characters)');
  }
  return password;
}

export async function hashPassword(password, initialPassword) {
  if (password === initialPassword) throw authError(400, '新密码不能使用初始密码');
  if (typeof password !== 'string' || password.length < 12 || password.length > 128) throw authError(400, '密码长度需为 12–128 个字符');
  return encodePassword(password);
}
async function encodePassword(password) {
  const salt = randomBytes(16).toString('hex');
  const key = await scrypt(password, salt, 64, { N:32768, r:8, p:1, maxmem:64 * 1024 * 1024 });
  return `scrypt:${salt}:${key.toString('hex')}`;
}
export async function checkPassword(password, stored) {
  if (typeof password !== 'string' || password.length > 128) return false;
  const [, salt, key] = (stored || `scrypt:${'0'.repeat(32)}:${'0'.repeat(128)}`).split(':');
  if (!salt || !key) return false;
  const actual = await scrypt(password, salt, 64, { N:32768, r:8, p:1, maxmem:64 * 1024 * 1024 });
  const expected = Buffer.from(key, 'hex');
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
export async function auditAuth(client, email, action) {
  await client.query('INSERT INTO audit(id,actor,action,entity,at) VALUES($1,$2,$3,$4,$5)', [randomUUID(), email, action, email, new Date().toISOString()]);
}
export function sessionCookie(token, secure, maxAge = 28800) {
  return `${secure ? '__Host-navigator' : 'navigator'}=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${secure ? '; Secure' : ''}`;
}
export function cookieToken(request, secure) {
  return (request.headers.get('cookie') || '').split(';').map(x => x.trim()).find(x => x.startsWith((secure ? '__Host-navigator' : 'navigator') + '='))?.split('=')[1] || '';
}
export async function sessionUser(client, request, secure) {
  const token = cookieToken(request, secure);
  if (!/^[a-f0-9]{64}$/.test(token)) return null;
  const session = (await client.query('SELECT email FROM sessions WHERE token_hash=$1 AND expires_at>now()', [digest(token)])).rows[0];
  if (!session) return null;
  // Lock credentials and recheck the session: resets cannot leave a stale
  // authenticated request running after their revocation has committed.
  await client.query('SELECT email FROM accounts WHERE email=$1 FOR UPDATE', [session.email]);
  const result = await client.query(`SELECT m.email,m.user_id,m.role_id,r.payload,COALESCE(p.must_change_password,0) AS must_change_password FROM sessions s JOIN members m ON m.email=s.email JOIN records r ON r.id=m.role_id LEFT JOIN account_password_state p ON p.email=m.email WHERE s.token_hash=$1 AND s.expires_at>now() AND m.enabled=1`, [digest(token)]);
  const row = result.rows[0];
  return row ? { id:row.user_id, email:row.email, roleId:row.role_id, permissions:JSON.parse(row.payload).permissions, mustChangePassword:!!row.must_change_password } : null;
}
export async function ensureInitialAccount(client, email, actor, initialPassword) {
  await client.query('SELECT email FROM members WHERE email=$1 FOR UPDATE', [email]);
  if ((await client.query('SELECT email FROM accounts WHERE email=$1 FOR UPDATE', [email])).rows[0]) return false;
  await client.query('INSERT INTO accounts(email,password_hash) VALUES($1,$2)', [email,await encodePassword(initialPassword)]);
  await client.query('INSERT INTO account_password_state(email,must_change_password) VALUES($1,1)', [email]);
  await client.query('UPDATE members SET user_id=COALESCE(user_id,$1) WHERE email=$2', [randomUUID(),email]);
  await auditAuth(client,actor,'创建初始密码账号：' + email);
  return true;
}
export async function initializeAccounts(client, actor, initialPassword) {
  const pending = (await client.query('SELECT m.email FROM members m LEFT JOIN accounts a ON a.email=m.email WHERE a.email IS NULL ORDER BY m.email')).rows;
  for (const member of pending) await ensureInitialAccount(client,member.email,actor,initialPassword);
}
async function resetPassword(client, actor, email, initialPassword) {
  if (!actor.permissions.includes('member.manage')) throw authError(403, '无法为此成员重置密码');
  if (actor.email===email) throw authError(400, '请使用修改密码功能修改自己的密码');
  await client.query('SELECT email FROM accounts WHERE email=$1 FOR UPDATE', [email]);
  const member = (await client.query('SELECT m.*,r.payload FROM members m JOIN records r ON r.id=m.role_id WHERE email=$1', [email])).rows[0];
  if (!member || !member.enabled || JSON.parse(member.payload).permissions.some(p => !actor.permissions.includes(p))) throw authError(403, '无法为此成员重置密码');
  await client.query('INSERT INTO accounts(email,password_hash) VALUES($1,$2) ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash),changed_at=now()', [email,await encodePassword(initialPassword)]);
  await client.query('INSERT INTO account_password_state(email,must_change_password) VALUES($1,1) ON DUPLICATE KEY UPDATE must_change_password=1', [email]);
  await client.query('UPDATE members SET user_id=COALESCE(user_id,$1) WHERE email=$2', [randomUUID(),email]);
  await client.query('DELETE FROM invitations WHERE email=$1', [email]);
  await client.query('DELETE FROM sessions WHERE email=$1', [email]);
  await client.query('DELETE FROM login_limits WHERE `key`=$1', ['email:' + digest(email)]);
  await auditAuth(client, actor.email, '重置为初始密码：' + email);
  return { ok:true, mustChangePassword:true, initialPassword };
}
export async function authRoute(client, request, user, config, ip) {
  const path = new URL(request.url).pathname;
  if (!path.startsWith('/api/auth/')) return null;
  if (path === '/api/auth/status' && request.method === 'GET') return json({authenticated:!!user,...(user?{email:user.email,mustChangePassword:user.mustChangePassword}:{})});
  if (path === '/api/auth/activate' || path === '/api/auth/invite') return json({error:'链接设置密码已停用，请联系管理员重置初始密码'},410);
  if (user?.mustChangePassword && !['/api/auth/password','/api/auth/logout'].includes(path)) return json({error:'请先修改初始密码',code:'PASSWORD_CHANGE_REQUIRED'},403);
  if (request.method !== 'POST') return json({ error:'请使用 POST' }, 405);
  const body = await request.json();
  if (!body || typeof body !== 'object' || Array.isArray(body)) return json({error:'请求格式无效'},400);
  if (path === '/api/auth/login') {
    const email = String(body.email || '').trim().toLowerCase().slice(0,254);
    for (const key of ['ip:' + digest(ip), 'email:' + digest(email)]) {
      await client.query("INSERT INTO login_limits(`key`,attempts,reset_at) VALUES($1,1,now()+INTERVAL 15 MINUTE) ON DUPLICATE KEY UPDATE attempts=IF(reset_at<now(),1,attempts+1), reset_at=IF(reset_at<now(),now()+INTERVAL 15 MINUTE,reset_at)", [key]);
      const row = (await client.query('SELECT attempts FROM login_limits WHERE `key`=$1 FOR UPDATE',[key])).rows[0];
      if (row.attempts > (key.startsWith('ip:') ? 50 : 10)) return json({ error:'尝试次数过多，请 15 分钟后重试' }, 429, { 'Retry-After':'900' });
    }
    await client.query('SELECT email FROM accounts WHERE email=$1 FOR UPDATE', [email]);
    const account = (await client.query('SELECT a.password_hash,m.enabled,COALESCE(p.must_change_password,0) AS must_change_password FROM accounts a JOIN members m ON m.email=a.email LEFT JOIN account_password_state p ON p.email=a.email WHERE a.email=$1', [email])).rows[0];
    if (!await checkPassword(body.password, account?.password_hash) || !account?.enabled) return json({ error:'邮箱或密码不正确，或账号已停用' }, 401);
    await client.query('DELETE FROM login_limits WHERE `key`=$1', ['email:' + digest(email)]);
    await client.query('DELETE FROM sessions WHERE expires_at<=now()');
    const token = randomBytes(32).toString('hex');
    await client.query("INSERT INTO sessions(token_hash,email,expires_at) VALUES($1,$2,now()+INTERVAL 8 HOUR)", [digest(token),email]);
    await auditAuth(client,email,'登录');
    return json({ok:true,mustChangePassword:!!account.must_change_password},200,{'Set-Cookie':sessionCookie(token,config.secure)});
  }
  if (!user) throw authError(401,'请先登录');
  if (path === '/api/auth/logout') {
    await client.query('DELETE FROM sessions WHERE token_hash=$1', [digest(cookieToken(request,config.secure))]);
    return json({ok:true},200,{'Set-Cookie':sessionCookie('',config.secure,0)});
  }
  if (path === '/api/auth/password') {
    const row = (await client.query('SELECT password_hash FROM accounts WHERE email=$1 FOR UPDATE',[user.email])).rows[0];
    if (!await checkPassword(body.currentPassword,row?.password_hash)) throw authError(400,'当前密码不正确');
    const hash = await hashPassword(body.password,config.initialPassword);
    if (await checkPassword(body.password,row.password_hash)) throw authError(400,'新密码不能与当前密码相同');
    await client.query('UPDATE accounts SET password_hash=$1,changed_at=now() WHERE email=$2',[hash,user.email]);
    await client.query('UPDATE account_password_state SET must_change_password=0 WHERE email=$1',[user.email]);
    await client.query('DELETE FROM sessions WHERE email=$1',[user.email]);
    await auditAuth(client,user.email,'修改密码并退出所有会话');
    return json({ok:true},200,{'Set-Cookie':sessionCookie('',config.secure,0)});
  }
  if (path === '/api/auth/reset-password') return json(await resetPassword(client,user,String(body.email||'').trim().toLowerCase(),config.initialPassword));
  return json({error:'接口不存在'},404);
}
