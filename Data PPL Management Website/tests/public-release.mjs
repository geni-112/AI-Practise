import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {readInitialPassword,hashPassword,checkPassword} from '../server/auth.mjs';
import {readCatalog,importCatalog} from '../server/import-catalog.mjs';
import {INITIAL_PASSWORD} from './test-credentials.mjs';

const secretDir=await mkdtemp(path.join(tmpdir(),'ppl-fixture-'));
try{
  const secretFile=path.join(secretDir,'initial');
  await writeFile(secretFile,INITIAL_PASSWORD+'\r\n');
  assert.equal(await readInitialPassword({INITIAL_ACCOUNT_PASSWORD_FILE:secretFile}),INITIAL_PASSWORD);
  assert.equal(await readInitialPassword({INITIAL_ACCOUNT_PASSWORD:INITIAL_PASSWORD}),INITIAL_PASSWORD);
  await assert.rejects(readInitialPassword({}));
  await assert.rejects(hashPassword(INITIAL_PASSWORD,INITIAL_PASSWORD));
  const personal='new-'+INITIAL_PASSWORD;
  assert.ok(await checkPassword(personal,await hashPassword(personal,INITIAL_PASSWORD)));
}finally{await rm(secretDir,{recursive:true,force:true})}

const items=await readCatalog();
assert.equal(items.length,48);assert.equal(items.filter(i=>i.type==='数据库').length,12);
const db=new DatabaseSync(':memory:');
try{
 db.exec("CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,version INTEGER DEFAULT 1); CREATE TABLE audit(id TEXT,actor TEXT,action TEXT,entity TEXT,at TEXT)");
 const client={async query(sql,params=[]){
   const stmt=db.prepare(sql.replace(/ FOR UPDATE$/,''));
   return sql.startsWith('SELECT')?{rows:stmt.all(...params)}:{rowCount:stmt.run(...params).changes};
 }};
 const run=apply=>importCatalog(client,items,'test@example.invalid',apply);
 assert.equal((await run(false)).created,48);assert.equal(db.prepare('SELECT count(*) AS n FROM records').get().n,0);
 assert.equal((await run(true)).created,48);assert.equal((await run(true)).alreadyPresent,48);
 const one=db.prepare('SELECT id,payload FROM records LIMIT 1').get(),data=JSON.parse(one.payload);
 data.title='Reviewed by the team';delete data.sourceBranches;
 db.prepare('UPDATE records SET payload=? WHERE id=?').run(JSON.stringify(data),one.id);
 assert.equal((await run(true)).updatedSources,1);assert.equal(JSON.parse(db.prepare('SELECT payload FROM records WHERE id=?').get(one.id).payload).title,data.title);
 assert.equal(db.prepare('SELECT count(*) AS n FROM audit').get().n,49);
}finally{db.close()}
console.log('PASS: deployment-owned credentials and idempotent catalog import');
