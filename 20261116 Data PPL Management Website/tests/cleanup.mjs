import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {createApplication} from '../server/index.mjs';
import {transaction} from '../server/database.mjs';
import {clearLegacy} from '../server/clear-legacy.mjs';
import {INITIAL_PASSWORD} from './test-credentials.mjs';
const env={INITIAL_ACCOUNT_PASSWORD:INITIAL_PASSWORD,DB_HOST:'127.0.0.1',DB_PORT:'13306',DB_USER:'navigator_test',DB_PASSWORD:'test-password-only',DB_NAME:'navigator_i18n_test',ADMIN_EMAIL:'i18n@test.local',APP_ORIGIN:'http://127.0.0.1:3101'};
const app=await createApplication({env});
const ids=Array.from({length:6},()=>randomUUID());
try{
 const baseline=await transaction(app.pool,async c=>({accounts:(await c.query('SELECT email,password_hash FROM accounts ORDER BY email')).rows,members:(await c.query('SELECT * FROM members ORDER BY email')).rows,roles:(await c.query("SELECT * FROM records WHERE kind='role' ORDER BY id")).rows}));
 await transaction(app.pool,async c=>{for(const [id,kind,obj]of [[ids[0],'project',{}],[ids[1],'project',{}],[ids[2],'resource',{}],[ids[3],'report',{projects:[{id:ids[0]}]}],[ids[4],'project',{name:'New user project'}],[ids[5],'report',{projects:[{id:ids[4]}]}]])await c.query('INSERT INTO records(id,kind,payload) VALUES($1,$2,$3)',[id,kind,JSON.stringify({id,...obj})]);});
 const manifest={projectIds:ids.slice(0,2),resourceIds:[ids[2]]};
 const preview=await transaction(app.pool,c=>clearLegacy(c,manifest));assert.equal(preview.applied,false);assert.deepEqual(preview.removed,{projects:2,resources:1,reports:1});
 await assert.rejects(transaction(app.pool,async c=>{await clearLegacy(c,manifest,{apply:true});throw new Error('injected failure')}),/injected failure/);
 assert.equal((await transaction(app.pool,c=>c.query('SELECT id FROM records WHERE id=$1',[ids[0]]))).rows.length,1,'rollback restores all rows');
 const result=await transaction(app.pool,c=>clearLegacy(c,manifest,{apply:true}));assert.deepEqual(result.removed,{projects:2,resources:1,reports:1});
 await transaction(app.pool,async c=>{
  for(const id of ids.slice(0,4))assert.equal((await c.query('SELECT id FROM records WHERE id=$1',[id])).rows.length,0);
  for(const id of ids.slice(4))assert.equal((await c.query('SELECT id FROM records WHERE id=$1',[id])).rows.length,1);
  assert.deepEqual((await c.query('SELECT email,password_hash FROM accounts ORDER BY email')).rows,baseline.accounts);
  assert.deepEqual((await c.query('SELECT * FROM members ORDER BY email')).rows,baseline.members);
  assert.deepEqual((await c.query("SELECT * FROM records WHERE kind='role' ORDER BY id")).rows,baseline.roles);
  assert.equal(JSON.parse((await c.query("SELECT payload FROM records WHERE id='setup-v2'")).rows[0].payload).rows,0);
 });
 const second=await transaction(app.pool,c=>clearLegacy(c,manifest,{apply:true}));assert.deepEqual(second.removed,{projects:0,resources:0,reports:0});
 console.log('PASS: exact imported IDs and associated reports removed atomically; new records, accounts and roles retained; dry-run, rollback and repeated cleanup verified');
}finally{await transaction(app.pool,async c=>{for(const id of ids)await c.query('DELETE FROM records WHERE id=$1',[id])});await app.pool.end()}
