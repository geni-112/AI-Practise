import {randomUUID} from 'node:crypto';
import {authError,digest} from './auth.mjs';
import {database} from './database.mjs';
import {memberDeletionImpact,detachMemberRecords} from '../dist/server/index.mjs';

export async function deleteMember(client,actor,input,adminEmail,preview=false){
  if(!actor?.permissions.includes('member.manage'))throw authError(403,'当前角色没有此操作权限');
  const email=typeof input.email==='string'?input.email.trim().toLowerCase():'';
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>190)throw authError(400,'邮箱无效');
  if(email===actor.email)throw authError(400,'请由其他管理员删除此账号');
  if(email===adminEmail)throw authError(400,'初始管理员账号不可删除');
  await client.query('SELECT email FROM accounts WHERE email=? FOR UPDATE',[email]);
  const member=(await client.query('SELECT m.*,r.payload FROM members m JOIN records r ON r.id=m.role_id WHERE m.email=? FOR UPDATE',[email])).rows[0];
  if(!member)throw authError(404,'成员已删除，请刷新列表');
  if(JSON.parse(member.payload).permissions.some(permission=>!actor.permissions.includes(permission)))throw authError(403,'不能管理超出自身权限的成员');
  const db=database(client);
  if(preview){
    const impact=await memberDeletionImpact(db,member);
    const analysisCount=Number((await client.query('SELECT COUNT(*) AS total FROM architecture_analyses WHERE owner_email=?',[email])).rows[0].total);
    return {email,displayName:member.display_name,userId:member.user_id,_version:member.version,...impact,analysisCount};
  }
  if(input.userId!==member.user_id||input._version!==member.version)throw authError(409,'成员已更新，请重新打开后确认');
  const impact=await detachMemberRecords(db,actor,member,adminEmail);
  // Keep running jobs on their current lease version so their result can commit.
  // A fresh request key avoids collisions when two former owners reused a key.
  const analyses=await client.query("UPDATE architecture_analyses SET owner_email=?,request_key=UUID(),version=IF(status='running',version,version+1) WHERE owner_email=?",[adminEmail,email]);
  await client.query('DELETE FROM content_translations WHERE owner_id=?',[member.user_id]);
  await client.query('DELETE FROM sessions WHERE email=?',[email]);
  await client.query('DELETE FROM account_password_state WHERE email=?',[email]);
  await client.query('DELETE FROM invitations WHERE email=?',[email]);
  await client.query('DELETE FROM accounts WHERE email=?',[email]);
  await client.query('DELETE FROM login_limits WHERE `key`=?',['email:'+digest(email)]);
  const removed=await client.query('DELETE FROM members WHERE email=? AND version=?',[email,member.version]);
  if(removed.rowCount!==1)throw authError(409,'成员已更新，请重新打开后确认');
  await client.query('INSERT INTO audit(id,actor,action,entity,at) VALUES(?,?,?,?,?)',
    [randomUUID(),actor.email,'删除成员：'+(member.display_name||email),email,new Date().toISOString()]);
  return {ok:true,...impact,analysisCount:analyses.rowCount};
}
