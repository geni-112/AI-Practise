import {randomUUID} from 'node:crypto';

// Only explicit imported IDs are removed. Account, role, audit and new business
// records are preserved. The marker prevents later initialization from reseeding.
export async function clearLegacy(client,manifest,{apply=false}={}){
 const projectIds=new Set(manifest.projectIds),resourceIds=new Set(manifest.resourceIds);
 if(projectIds.size!==manifest.projectIds.length||resourceIds.size!==manifest.resourceIds.length)throw new Error('Duplicate cleanup IDs');
 if([...projectIds].some(id=>resourceIds.has(id)))throw new Error('Ambiguous cleanup IDs');
 const rows=(await client.query('SELECT id,kind,payload FROM records FOR UPDATE')).rows;
 const matched=rows.filter(r=>(r.kind==='project'&&projectIds.has(r.id))||(r.kind==='resource'&&resourceIds.has(r.id)));
 if(matched.some(r=>JSON.parse(r.payload).fileKey))throw new Error('Imported resource unexpectedly has an uploaded file; review before cleanup');
 const reports=rows.filter(r=>r.kind==='report'&&(JSON.parse(r.payload).projects||[]).some(p=>projectIds.has(p.id)));
 const selected=[...matched,...reports],removed={projects:matched.filter(r=>r.kind==='project').length,resources:matched.filter(r=>r.kind==='resource').length,reports:reports.length};
 const retained={projects:rows.filter(r=>r.kind==='project').length-removed.projects,resources:rows.filter(r=>r.kind==='resource').length-removed.resources,reports:rows.filter(r=>r.kind==='report').length-removed.reports};
 if(apply){
  for(const row of selected)await client.query('DELETE FROM records WHERE id=$1 AND kind=$2',[row.id,row.kind]);
  const marker={file:'工作空间项目台账',sheet:'项目',rows:0,latestKnownDate:null,legacyClearedAt:new Date().toISOString()};
  await client.query("UPDATE records SET payload=$1,version=version+1 WHERE id='setup-v2' AND kind='meta'",[JSON.stringify(marker)]);
  await client.query('INSERT INTO audit(id,actor,action,entity,at) VALUES($1,$2,$3,$4,$5)',[randomUUID(),'system:maintenance','清理历史导入数据',JSON.stringify(removed),new Date().toISOString()]);
 }
 return {applied:apply,removed,retained};
}
