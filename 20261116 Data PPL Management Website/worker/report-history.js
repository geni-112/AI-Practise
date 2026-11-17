const reportFields=['id','name','customer','repo','type','vendor','scenario','stage','originalStage','status','archivedAt','risk','pipelineDate','updatedAt','planYear','eiPlan','servicePlan','actuals','logs','notes','weekly','next','due','bdName','saName','milestones'];
const reportInput = p => Object.fromEntries(reportFields.filter(k=>p[k]!==undefined).map(k=>[k,p[k]]));
const santiagoDate = (at=new Date())=>new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Santiago'}).format(at);

async function rememberProject(db,project,version,at=new Date()) {
  await db.prepare('INSERT INTO project_report_states(project_id,project_version,effective_month,payload) VALUES(?,?,?,?)')
    .bind(project.id,version,santiagoDate(at).slice(0,7),JSON.stringify(reportInput(project))).run();
}

export async function initializeReportHistory(db) {
  if(await get(db,'report-history-v1','meta'))return;
  const at=new Date();
  for(const project of await all(db,'project'))await rememberProject(db,project,project._version,at);
  await insert(db,'meta',{id:'report-history-v1',month:santiagoDate(at).slice(0,7)});
}

function reportAudience(user,report) {
  return !report.scopeOwner || user.email===report.scopeOwner || has(user,'project.read.all');
}

async function reportForPeriod(db,user,filters,{preferSnapshot=true}={}) {
  const {period,type='全部',repo='全部'}=filters;
  if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(period||''))fail(400,'请选择月份');
  const historical=period<santiagoDate().slice(0,7);
  if(historical && preferSnapshot) {
    const snapshots=(await all(db,'report')).filter(r=>r.period===period&&r.type===type&&r.repo===repo&&reportAudience(user,r)&&(!r.scopeOwner||r.scopeOwner===user.email&&!has(user,'project.read.all')));
    snapshots.sort((a,b)=>b.generatedAt.localeCompare(a.generatedAt)||b.id.localeCompare(a.id));
    if(snapshots.length)return {...snapshots[0],basis:'snapshot'};
  }
  const current=reportProjects(user,await all(db,'project'));
  let inputs=current,basis='live';
  if(historical) {
    const tracking=await get(db,'report-history-v1','meta');
    if(!tracking || period<tracking.month)basis='ledger';
    else{
      const {results}=await db.prepare(`SELECT s.project_id,s.payload FROM project_report_states s JOIN
        (SELECT project_id,MAX(project_version) AS version FROM project_report_states WHERE effective_month<=? GROUP BY project_id) last_state
        ON s.project_id=last_state.project_id AND s.project_version=last_state.version`).bind(period).all();
      const permitted=new Set(current.map(p=>p.id));
      inputs=results.filter(r=>permitted.has(r.project_id)).map(r=>JSON.parse(r.payload));
      basis='monthEnd';
    }
  }
  const report=buildReport(inputs,period,type,repo);
  const ids=new Set(report.projects.map(p=>p.id));
  report.reportInputs=inputs.filter(p=>ids.has(p.id)).map(reportInput);
  report.basis=basis;report.dataBasis=basis;
  if(basis==='ledger')report.warnings.unshift('该月没有归档快照或完整历史，按当前台账重算。');
  return report;
}

async function visibleReport(db,user,stored) {
  if(!reportAudience(user,stored))fail(404,'报表不存在');
  const {reportInputs,dictionarySnapshot,scopeOwner,...publicFields}=stored;
  let r=structuredClone(publicFields);
  const restricted=has(user,'project.read.own')&&!has(user,'project.read.all');
  if(restricted && r.basis==='snapshot') {
    const allowed=new Set((await all(db,'project')).filter(p=>canRead(user,p)).map(p=>p.id));
    // New snapshots freeze each project's contribution. Old snapshots only contain
    // the table rows, so unavailable per-project financial figures remain unknown.
    const inputs=(reportInputs||r.projects||[]).filter(p=>allowed.has(p.id));
    const subset=buildReport(reportInputs?inputs:inputs.map(p=>({...p,planYear:Number(r.period.slice(0,4))})),r.period,r.type,r.repo,r.source);
    if(!reportInputs){
      const sum=key=>{const nums=inputs.map(p=>p[key]).filter(Number.isFinite);return nums.length?nums.reduce((a,b)=>a+b,0):null};
      const current=sum('ytdActual'),prior=sum('priorYtdActual');
      subset.stats.ytdActual=current;subset.stats.yoy=current!==null&&prior?current/prior-1:null;
      subset.stats.revenueCoverage=inputs.filter(p=>Number.isFinite(p.ytdActual)).length;
      if(inputs.length){subset.stats.customers=null;subset.stats.updates=null;}
      subset.warnings.push('此旧快照仅保留项目行，部分汇总项缺少历史明细。');
    }
    r={...subset,id:r.id,generatedAt:r.generatedAt,publishedBy:r.publishedBy,publishedByName:r.publishedByName,basis:r.basis,dataBasis:r.dataBasis};
  }
  const details=has(user,'report.generate')&&(has(user,'project.read.all')||has(user,'project.read.own'));
  if(!details || restricted&&r.basis==='snapshot') {
    r.summaryGenerated=true;r.summary='本期机会点 '+r.stats.projects+' 个，新增 '+r.stats.newProjects+' 个。';
    r.support=[];r.contact='';
    if(!details){r.projects=[];r.updates=[];}
  }
  return reportForUser(user,r);
}
