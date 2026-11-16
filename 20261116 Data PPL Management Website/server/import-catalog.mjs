import fs from 'node:fs/promises';
import {createHash,randomUUID} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {createPool,transaction} from './database.mjs';

const allowedRepos=new Set(['geni-112/AI-Practise','binrogithub/1-3-Cloud-Adoption-Skills']);
const validSha=value=>typeof value==='string' && /^[a-f0-9]{40}$/.test(value);
function publicLink(value,repo) {
  const url=new URL(value);
  return url.origin==='https://github.com'&&!url.username&&!url.password&&url.pathname.startsWith('/'+repo+'/');
}

export async function readCatalog() {
  const items=JSON.parse(await fs.readFile(new URL('./catalog/github-resources.json',import.meta.url),'utf8'));
  const keys=new Set(),urls=new Set();
  for(const item of items){
    const {repository,documentSha}=item.source;
    if(!allowedRepos.has(repository)||!validSha(documentSha)||!['大数据','数据库'].includes(item.type)||
       !item.key||!item.title||item.title.length>200||typeof item.body!=='string'||item.body.length>50000||
       !publicLink(item.url,repository)||keys.has(item.key)||urls.has(item.url)||!item.sourceBranches.length){
      throw new Error('Invalid or duplicate GitHub resource');
    }
    for(const ref of item.sourceBranches){
      if(!ref.branch||!validSha(ref.commit)||!publicLink(ref.url,repository)||!new URL(ref.url).pathname.split('/').includes(ref.commit)){
        throw new Error('Invalid GitHub branch reference');
      }
    }
    keys.add(item.key);urls.add(item.url);
  }
  return items;
}

export async function importCatalog(client,items,actor,apply) {
  const rows=(await client.query("SELECT id,payload,version FROM records WHERE kind='resource'"+(apply?' FOR UPDATE':''))).rows;
  const byId=new Map(),byUrl=new Map();
  for(const row of rows){
    const payload=JSON.parse(row.payload);
    byId.set(row.id,row);if(payload.url)byUrl.set(payload.url,row);
  }
  const counts={mode:apply?'apply':'dry-run',created:0,updatedSources:0,alreadyPresent:0};
  const time=new Date().toISOString();
  for(const {key,...fields} of items){
    const id='github_'+createHash('sha256').update(key).digest('hex').slice(0,32);
    const old=byId.get(id)||byUrl.get(fields.url);
    if(old){
      const payload=JSON.parse(old.payload);
      if(JSON.stringify([payload.source,payload.sourceBranches])===JSON.stringify([fields.source,fields.sourceBranches])){
        counts.alreadyPresent++;continue;
      }
      counts.updatedSources++;
      if(apply){
        payload.source=fields.source;payload.sourceBranches=fields.sourceBranches;
        const res=await client.query("UPDATE records SET payload=?,version=version+1 WHERE id=? AND version=?",[JSON.stringify(payload),old.id,old.version]);
        if(res.rowCount!==1)throw new Error('Resource version changed during import');
      }
    }else{
      counts.created++;
      if(apply){
        const value={id,...fields,createdAt:time,updatedAt:time,createdBy:actor};
        await client.query("INSERT INTO records(id,kind,payload) VALUES(?,'resource',?)",[id,JSON.stringify(value)]);
      }
    }
    if(apply)await client.query('INSERT INTO audit(id,actor,action,entity,at) VALUES(?,?,?,?,?)',[randomUUID(),actor,old?'更新 GitHub 分支来源':'导入 GitHub 功能资料',old?.id||id,time]);
  }
  return counts;
}

async function main(args) {
  const mode=args[0]||'--check';
  if(args.length>1||!['--check','--dry-run','--apply'].includes(mode))throw new Error('Usage: node server/import-catalog.mjs [--check|--dry-run|--apply]');
  const items=await readCatalog();
  if(mode==='--check'){
    console.log(JSON.stringify({resources:items.length,branchReferences:items.reduce((n,r)=>n+r.sourceBranches.length,0)}));
    return;
  }
  const env=process.env;
  if(!env.ADMIN_EMAIL)throw new Error('ADMIN_EMAIL is required for the audit trail');
  const pool=createPool({...env,DB_SSL_CA:env.DB_SSL_CA_FILE?await fs.readFile(env.DB_SSL_CA_FILE,'utf8'):undefined});
  try{
    const outcome=await transaction(pool,client=>importCatalog(client,items,env.ADMIN_EMAIL,mode==='--apply'));
    console.log(JSON.stringify(outcome));
  }finally{await pool.end()}
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  main(process.argv.slice(2)).catch(error=>{console.error(error.message);process.exitCode=1});
}
