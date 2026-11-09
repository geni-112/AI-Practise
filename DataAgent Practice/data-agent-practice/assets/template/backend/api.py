from __future__ import annotations
import asyncio,json,secrets,uuid,os
from dataclasses import asdict
from contextlib import asynccontextmanager
from datetime import timedelta
from fastapi import FastAPI,Request,Response,HTTPException,Depends
from pydantic import BaseModel,Field
from .localization import Locale
import httpx,jwt
from temporalio.client import Client,Schedule,ScheduleSpec,ScheduleActionStartWorkflow,ScheduleUpdate,ScheduleAlreadyRunningError
from temporalio.worker import Worker,UnsandboxedWorkflowRunner
from .config import ROOT,RUNTIME,settings
from .policy import Subject,ROLES,authorize
from . import jobs,metadata

sessions={};temporal=None;worker_task=None

@asynccontextmanager
async def lifespan(app):
    global temporal,worker_task
    if settings.temporal_enabled:
        try:
            temporal=await asyncio.wait_for(Client.connect(settings.temporal_address),timeout=5)
            worker=Worker(temporal,task_queue='nexo-processing',workflows=[jobs.ProcessingWorkflow],activities=[jobs.execute_node,jobs.mark_failed,jobs.create_scheduled_job],workflow_runner=UnsandboxedWorkflowRunner())
            worker_task=asyncio.create_task(worker.run())
        except Exception:temporal=None
    yield
    if worker_task:worker_task.cancel()

app=FastAPI(title='NEXO Data Agent',version='0.1.0',lifespan=lifespan)
from . import access
app.middleware('http')(access.gate)
app.include_router(access.router)

async def identity(request:Request)->Subject:
    if settings.demo:
        subject=sessions.get(request.cookies.get('nexo_session'))
        if subject:return subject
    authorization=request.headers.get('Authorization','')
    if authorization.startswith('Bearer ') and settings.oidc_issuer and settings.oidc_jwks_url:
        try:
            token=authorization.removeprefix('Bearer ');key=jwt.PyJWKClient(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
            claims=jwt.decode(token,key.key,algorithms=['RS256'],audience=settings.oidc_audience,issuer=settings.oidc_issuer)
            return Subject(tenant=claims['nexo_tenant'],persona=claims['nexo_role'],user_id=claims['sub'])
        except Exception:raise HTTPException(401,'Invalid identity token')
    raise HTTPException(401,'Sign in before accessing data')

@app.exception_handler(PermissionError)
async def forbidden(request,error):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':str(error)},status_code=403)

@app.get('/api/health')
async def health():
    from .database import dws_available
    dws=await asyncio.to_thread(dws_available) if settings.data_backend=='dws' else False
    return {'service':'nexo-api','openjiuwen':True,'data_backend':settings.data_backend,'dws_connected':dws,'model_connected':bool(settings.model_api_key and settings.model_base_url),'model':settings.model_name,'openmetadata':await metadata.available(),'temporal':temporal is not None,'iceberg':(RUNTIME/'iceberg-catalog.db').exists(),'demo':settings.demo,'region':settings.region,'deployment':os.getenv('DEPLOYMENT_KIND','local')}

class DemoSession(BaseModel):
    tenant:str='luma';persona:str='analyst'

@app.post('/api/demo/session')
async def demo_session(body:DemoSession,response:Response):
    if not settings.demo:raise HTTPException(404,'Demo identities disabled')
    try:subject=Subject(body.tenant,body.persona)
    except PermissionError:raise HTTPException(400,'Unknown demo identity')
    token=secrets.token_urlsafe(32);sessions[token]=subject;response.set_cookie('nexo_session',token,httponly=True,samesite='strict',max_age=3600)
    return {'tenant':subject.tenant,'persona':subject.persona,'demo':True}

class AnalyzeRequest(BaseModel):
    question:str=Field(min_length=1,max_length=2000)
    previous:dict|None=None
    locale:Locale='zh-CN'

@app.post('/api/analyze')
async def analyze(body:AnalyzeRequest,subject:Subject=Depends(identity)):
    from .agent import analyze
    try:return await analyze(body.question,subject,body.previous,body.locale)
    except PermissionError:raise
    except Exception as error:
        # Don't surface credentials, upstream headers or connection DSNs.
        message=str(error)
        if 'denied' in message.lower():raise HTTPException(403,'The current role cannot access this metric or region')
        raise HTTPException(502,'Analysis failed. Inspect local service logs for the failing stage; no provider fallback was used.')

@app.post('/api/authorize/export')
async def export(subject:Subject=Depends(identity)):
    await authorize(subject,'export');return {'allowed':True}

@app.get('/api/catalog')
async def catalog(subject:Subject=Depends(identity)):
    result=await metadata.catalog(subject.tenant,subject.role['domains']) or []
    allowed=[]
    for item in result:
        try:await authorize(subject,'discover',item['domain']);allowed.append(item)
        except PermissionError:pass
    return allowed

@app.get('/api/jobs')
async def list_jobs(subject:Subject=Depends(identity)):
    # A global aggregate cannot be safely narrowed to a region after execution.
    # Region-limited users cannot read broader runs or their cached results.
    if subject.role.get('region'):return []
    return jobs.list_jobs(subject.tenant)

@app.post('/api/jobs')
async def start_job(flow:dict,subject:Subject=Depends(identity)):
    await authorize(subject,'execute','Sales')
    try:nodes=jobs.validate_flow(flow,subject.tenant)
    except ValueError as error:raise HTTPException(400,str(error))
    if not temporal:raise HTTPException(503,'Temporal is not connected. Start the local orchestration service first.')
    schedule_id=None
    if flow.get('schedule','manual')=='daily':
        if flow.get('timezone')!='America/Mexico_City':raise HTTPException(400,'Demo schedules must use America/Mexico_City')
        import re
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',flow.get('id','')):raise HTTPException(400,'Invalid flow ID')
        schedule_id=f'nexo-{subject.tenant}-{flow["id"]}'
        scheduled=Schedule(action=ScheduleActionStartWorkflow(jobs.ProcessingWorkflow.run,{'nodes':nodes,'subject':asdict(subject),'flow':flow},id=schedule_id+'-run',task_queue='nexo-processing'),spec=ScheduleSpec(cron_expressions=['0 8 * * *'],time_zone_name=flow['timezone']))
        try:await temporal.create_schedule(schedule_id,scheduled)
        except ScheduleAlreadyRunningError:await temporal.get_schedule_handle(schedule_id).update(lambda _:ScheduleUpdate(schedule=scheduled))
    elif flow.get('schedule','manual')!='manual':raise HTTPException(400,'Unsupported schedule')
    job_id='RUN-'+uuid.uuid4().hex[:10].upper();job={'id':job_id,'tenant':subject.tenant,'name':flow['name'],'version':flow.get('version',1),'status':'queued','createdAt':jobs.now(),'progress':0,'currentNode':nodes[0]['id'],'nodes':nodes,'logs':[{'time':jobs.now(),'message':'Submitted to Temporal. Authorization is checked again at each node.'}],'mode':'temporal','workflow':{**flow,'nodes':nodes}}
    jobs.save(job)
    if schedule_id:
        job['schedule_id']=schedule_id;job['logs'].append({'time':jobs.now(),'message':'Daily 08:00 America/Mexico_City schedule saved. Running the first execution now.'});jobs.save(job)
    await temporal.start_workflow(jobs.ProcessingWorkflow.run,{'job_id':job_id,'nodes':nodes,'subject':asdict(subject)},id=job_id,task_queue='nexo-processing')
    return job

@app.post('/api/jobs/{job_id}/cancel')
async def cancel(job_id:str,subject:Subject=Depends(identity)):
    await authorize(subject,'execute')
    try:job=jobs.get(job_id)
    except KeyError:raise HTTPException(404,'Job not found')
    if job['tenant']!=subject.tenant:raise HTTPException(404,'Job not found')
    if job['status'] not in ['queued','running']:raise HTTPException(409,'Job is already closed')
    job.update(status='cancelled',endedAt=jobs.now());job['logs'].append({'time':jobs.now(),'message':'Cancellation requested. No further publication nodes may run.'});jobs.save(job)
    if temporal:await temporal.get_workflow_handle(job_id).cancel()
    return {'status':'cancel_requested'}

@app.delete('/api/schedules/{schedule_id}')
async def delete_schedule(schedule_id:str,subject:Subject=Depends(identity)):
    await authorize(subject,'execute')
    if not schedule_id.startswith(f'nexo-{subject.tenant}-'):raise HTTPException(404,'Schedule not found')
    if not temporal:raise HTTPException(503,'Temporal unavailable')
    await temporal.get_schedule_handle(schedule_id).delete()
    return {'deleted':schedule_id}

# Cloud deployment serves the built UI on the same protected origin as the API.
if (ROOT/'dist').is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')
