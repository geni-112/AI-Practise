// Recovery is an operator-only CLI; no HTTP reset bypass exists.
import fs from 'node:fs/promises';
import {createPool,transaction} from './database.mjs';
import {auditAuth,digest} from './auth.mjs';
const email=String(process.argv[2]||'').trim().toLowerCase();
if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||process.argv[3]!=='--verified-owner')throw new Error('Usage: node server/reset-mfa.mjs EMAIL --verified-owner. Verify the account owner out of band first.');
const pool=createPool({...process.env,DB_SSL_CA:process.env.DB_SSL_CA_FILE?await fs.readFile(process.env.DB_SSL_CA_FILE,'utf8'):undefined});
try{
 await transaction(pool,async c=>{
  if(!(await c.query('SELECT email FROM accounts WHERE email=? FOR UPDATE',[email])).rows[0])throw new Error('Account not found');
  await c.query('DELETE FROM account_mfa WHERE email=?',[email]);
  await c.query('DELETE FROM sessions WHERE email=?',[email]);
  await c.query('DELETE FROM login_limits WHERE `key`=?',['mfa:'+digest(email)]); 
  await auditAuth(c,'verified-cloud-operator','MFA 人工恢复并撤销所有会话：'+email);
 });
 console.log('Authenticator reset; all sessions revoked. The owner must enroll again after password authentication.');
}finally{await pool.end()}
