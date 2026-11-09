from __future__ import annotations
import asyncio,json,sqlite3,uuid,re
from datetime import datetime,timezone,timedelta
from temporalio import workflow,activity
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from .config import RUNTIME
from .policy import Subject,authorize

def now():return datetime.now(timezone.utc).isoformat()
def db():
    c=sqlite3.connect(RUNTIME/'jobs.db');c.execute('PRAGMA journal_mode=WAL');c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,tenant TEXT,payload TEXT)');return c
def save(job:dict):
    with db() as c:c.execute('INSERT INTO jobs VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(job['id'],job['tenant'],json.dumps(job,default=str)))
def get(job_id:str)->dict:
    with db() as c:row=c.execute('SELECT payload FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not row:raise KeyError(job_id)
    return json.loads(row[0])
def list_jobs(tenant:str):
    with db() as c:return [json.loads(r[0]) for r in c.execute('SELECT payload FROM jobs WHERE tenant=? ORDER BY rowid DESC',(tenant,))]

def validate_flow(flow:dict,tenant:str):
    if flow.get('domain','Sales')!='Sales':raise ValueError('First executor supports Sales-domain flows only')
    if flow.get('tenant')!=tenant:raise PermissionError('Workflow tenant mismatch')
    nodes=flow.get('nodes',[]);edges=flow.get('edges',[]);lookup={n['id']:n for n in nodes}
    if len(lookup)!=len(nodes) or not nodes:raise ValueError('Invalid node identifiers')
    if len(edges)!=len(nodes)-1:raise ValueError('Only connected sequential flows are supported')
    degree={i:0 for i in lookup};nexts={i:[] for i in lookup}
    for e in edges:
        if e['source'] not in lookup or e['target'] not in lookup:raise ValueError('Unknown edge node')
        degree[e['target']]+=1;nexts[e['source']].append(e['target'])
    queue=[i for i,v in degree.items() if v==0]
    if len(queue)!=1:raise ValueError('Flow must have one connected source')
    result=[]
    while queue:
        i=queue.pop(0);result.append(lookup[i])
        if len(nexts[i])>1:raise ValueError('Branching is not supported in the first executor')
        for n in nexts[i]:
            degree[n]-=1
            if degree[n]==0:queue.append(n)
    if len(result)!=len(nodes):raise ValueError('Cyclic dependency')
    types=[n['type'] for n in result]
    if types[0]!='source' or types[-1]!='publish' or any(types.count(k)!=1 for k in ['source','aggregate','publish']):raise ValueError('Requires one source, one aggregate, one final publish')
    if any(t not in ['source','transform','aggregate','quality','publish'] for t in types):raise ValueError('Unsupported node')
    agg=types.index('aggregate')
    if any(t=='transform' and i>agg or t=='quality' and i<agg for i,t in enumerate(types)):raise ValueError('Transforms must precede aggregation; checks must follow it')
    if result[0]['config'].get('asset')!='orders':raise ValueError('Only orders source is supported')
    if not re.fullmatch(r'2026-(0[4-9]|10)',result[0]['config'].get('range','')):raise ValueError('Unsupported input period')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,60}',result[-1]['config'].get('target','')):raise ValueError('Invalid target')
    for n in result:
        if n['type']=='transform' and n['config'].get('operation') not in ['filter_valid','completed_only']:raise ValueError('Unsupported transform')
        if n['type']=='aggregate' and (n['config'].get('metric') not in ['revenue','orders'] or n['config'].get('dimension') not in ['region','category','channel']):raise ValueError('Unsupported aggregate')
        if n['type']=='quality' and n['config'].get('rule') not in ['force_fail','non_empty_non_negative']:raise ValueError('Unsupported quality rule')
    return result

@activity.defn
async def execute_node(job_id:str,node:dict,identity:dict):
    from .agent import call_mcp
    from .planning import Plan
    subject=Subject(**identity);await authorize(subject,'execute','Sales')
    job=get(job_id)
    if job['status']=='cancelled':raise ApplicationError('Job cancelled',non_retryable=True)
    index=next(i for i,n in enumerate(job['nodes']) if n['id']==node['id'])
    job.update(status='running',currentNode=node['id'],progress=round(index/len(job['nodes'])*100))
    job['logs'].append({'time':now(),'message':f'Executing {node["label"]} through the scoped executor'})
    save(job);activity.heartbeat(node['id'])
    if node['type']=='aggregate':
        source=job['nodes'][0];plan=Plan(metric=node['config']['metric'],dimension=node['config']['dimension'],month=source['config']['range'])
        completed=any(n['type']=='transform' and n['config'].get('operation')=='completed_only' for n in job['nodes'])
        result=await call_mcp(subject,'execute_plan',{'plan':plan.model_dump(),'completed_only':completed});job['result']=result['data']
    elif node['type']=='quality':
        rows=job.get('result',[])
        if node['config'].get('rule')=='force_fail' or not rows or any(r['value']<0 for r in rows):raise ApplicationError('Quality check failed; output was not published',type='QualityError',non_retryable=True)
    elif node['type']=='publish':
        # Re-read status after each awaited operation before side effects.
        if get(job_id)['status']=='cancelled':raise ApplicationError('Job cancelled',non_retryable=True)
        output=await call_mcp(subject,'publish_result',{'target':node['config']['target'],'rows':job.get('result',[]),'partition':job['nodes'][0]['config']['range'],'run_id':job_id});job['output']=output
        try:
            from .metadata import register_lineage
            job['metadata_lineage']=await register_lineage(subject,job)
        except Exception as error:job['logs'].append({'time':now(),'message':'Output created; metadata registration requires retry: '+str(error)[:180]})
    activity.heartbeat(node['id'])
    if get(job_id)['status']=='cancelled':return
    if node['type']=='publish':job.update(status='completed',progress=100,endedAt=now());job['logs'].append({'time':now(),'message':'Finished. Output is in local sandbox, not DWS source tables.'})
    save(job)

@activity.defn
async def mark_failed(job_id:str,error:str):
    job=get(job_id)
    if job['status']=='cancelled':return
    job.update(status='failed',error=error,endedAt=now());job['logs'].append({'time':now(),'message':error});save(job)

@activity.defn
async def create_scheduled_job(payload:dict,execution_id:str):
    import hashlib
    subject=Subject(**payload['subject']);await authorize(subject,'execute','Sales')
    flow=payload['flow'];nodes=validate_flow(flow,subject.tenant)
    job_id='RUN-'+hashlib.sha256(execution_id.encode()).hexdigest()[:10].upper()
    try:return get(job_id)['id']
    except KeyError:pass
    save({'id':job_id,'tenant':subject.tenant,'name':flow['name'],'version':flow.get('version',1),'status':'queued','createdAt':now(),'progress':0,'currentNode':nodes[0]['id'],'nodes':nodes,'logs':[{'time':now(),'message':'Triggered by Temporal schedule; immutable flow version attached.'}],'mode':'temporal','workflow':{**flow,'nodes':nodes}})
    return job_id

@workflow.defn
class ProcessingWorkflow:
    @workflow.run
    async def run(self,payload:dict):
        if not payload.get('job_id'):
            payload={**payload,'job_id':await workflow.execute_activity(create_scheduled_job,args=[payload,workflow.info().workflow_id],start_to_close_timeout=timedelta(seconds=15))}
        try:
            for node in payload['nodes']:
                await workflow.execute_activity(execute_node,args=[payload['job_id'],node,payload['subject']],start_to_close_timeout=timedelta(seconds=120),heartbeat_timeout=timedelta(seconds=110),retry_policy=RetryPolicy(maximum_attempts=2))
        except Exception as error:
            await workflow.execute_activity(mark_failed,args=[payload['job_id'],str(error)],start_to_close_timeout=timedelta(seconds=10))
            raise
