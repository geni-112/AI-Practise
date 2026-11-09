from __future__ import annotations
import json,os,base64,uuid
from pathlib import Path
from datetime import datetime,timezone
import httpx
from urllib.parse import urlsplit
from .config import ROOT,RUNTIME,settings
from .policy import ASSET_DOMAINS

TOKEN_FILE=RUNTIME/'openmetadata-token'
def token():return settings.metadata_token or (TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else '')

def local_bootstrap_allowed():
    url=urlsplit(settings.metadata_url)
    return settings.demo and not settings.metadata_token and url.scheme=='http' and url.hostname in ('127.0.0.1','localhost') and not url.username and not url.password

async def refresh_local_token():
    # Renew only our local demo session; explicitly supplied service tokens fail closed.
    if not local_bootstrap_allowed():raise RuntimeError('Supply a valid OPENMETADATA_TOKEN for this service')
    async with httpx.AsyncClient(timeout=20) as client:
        response=await client.post(settings.metadata_url+'/api/v1/users/login',json={'email':'admin@open-metadata.org','password':base64.b64encode(os.getenv('OM_BOOTSTRAP_PASSWORD','admin').encode()).decode()})
        if response.status_code!=200:raise RuntimeError('Local OpenMetadata session renewal failed')
        new_token=response.json()['accessToken']
    temporary=TOKEN_FILE.with_name('.openmetadata-token-'+uuid.uuid4().hex)
    with open(temporary,'x',opener=lambda path,flags:os.open(path,flags,0o600)) as file:file.write(new_token)
    temporary.replace(TOKEN_FILE)

async def api(method:str,path:str,payload:dict|None=None):
    async with httpx.AsyncClient(base_url=settings.metadata_url,headers={'Authorization':'Bearer '+token()},timeout=30) as client:
        response=await client.request(method,'/api/v1'+path,json=payload)
        if response.status_code==401 and local_bootstrap_allowed():
            await refresh_local_token()
            response=await client.request(method,'/api/v1'+path,json=payload,headers={'Authorization':'Bearer '+token()})
        if response.status_code>=400:raise RuntimeError(f'OpenMetadata {method} {path}: HTTP {response.status_code}')
        return response.json() if response.content else {}

async def available():
    try:
        async with httpx.AsyncClient(timeout=3) as c:r=await c.get(settings.metadata_url+'/api/v1/system/version')
        return r.status_code==200
    except Exception:return False

async def catalog(tenant:str,domains:list[str]):
    if not token():return None
    result=[]
    for schema in ['internal','external']:
        data=await api('GET',f'/tables?databaseSchema=nexo_demo.{tenant}_commerce.{schema}&limit=100&fields=columns')
        for table in data.get('data',[]):
            if ASSET_DOMAINS.get(table['name']) in domains:result.append({'name':table['name'],'domain':ASSET_DOMAINS[table['name']],'id':table['id'],'fullyQualifiedName':table['fullyQualifiedName'],'columns':[{'name':c['name'],'dataType':c['dataType']} for c in table.get('columns',[])]})
    return result

async def seed():
    if not token():
        # Explicitly local-only bootstrap, using the official demo installation.
        await refresh_local_token()
    data=json.loads((ROOT/'public/demo-data.json').read_text())['tables']
    await api('PUT','/services/databaseServices',{'name':'nexo_demo','serviceType':'CustomDatabase','description':'NEXO synthetic commerce source. Data stays in the local demo warehouse until DWS is connected.'})
    entities=[]
    for tenant in ['luma','northstar']:
        domain_ids={}
        for domain in ['Sales','Marketing','Supply Chain','Finance','Platform']:
            name=tenant+'_'+domain.lower().replace(' ','_')
            d=await api('PUT','/domains',{'name':name,'displayName':f'{tenant.title()} · {domain}','description':'Synthetic commerce business domain','domainType':'Source-aligned'})
            domain_ids[domain]=d['fullyQualifiedName']
        await api('PUT','/databases',{'name':tenant+'_commerce','service':'nexo_demo','description':f'Isolated metadata namespace for {tenant} demo tenant'})
        for schema in ['internal','external']:
            await api('PUT','/databaseSchemas',{'name':schema,'database':f'nexo_demo.{tenant}_commerce'})
        for name,rows in data.items():
            if name=='tenants':continue
            schema='external' if name in ['ad_metrics','competitor_prices','reviews'] else 'internal'
            cols=[]
            for col in rows[0]:
                sample=next((r[col] for r in rows if r[col] is not None),'')
                dtype='BOOLEAN' if isinstance(sample,bool) else 'BIGINT' if isinstance(sample,int) else 'DOUBLE' if isinstance(sample,float) else 'STRING'
                cols.append({'name':col,'dataType':dtype,'description':'Restricted fictional contact field' if col in ['email','phone'] else f'Synthetic {col.replace("_"," ")}'})
            body={'name':name,'databaseSchema':f'nexo_demo.{tenant}_commerce.{schema}','columns':cols,'description':f'Fictional English commerce data. Tenant {tenant}. Grain and metrics are controlled by NEXO.','domains':[domain_ids[ASSET_DOMAINS[name]]]}
            table=await api('PUT','/tables',body);entities.append(table)
    count=await snapshot_history(entities)
    return {'tables_registered':len(entities),'history_rows':count,'server':settings.metadata_url,'version':'2.0.7'}

async def snapshot_history(entities:list[dict]):
    from pyiceberg.catalog import load_catalog
    from pyiceberg.schema import Schema
    from pyiceberg.types import NestedField,StringType
    import pyarrow as pa
    warehouse=RUNTIME/'iceberg';warehouse.mkdir(exist_ok=True)
    catalog=load_catalog('nexo_history',type='sql',uri='sqlite:///'+str(RUNTIME/'iceberg-catalog.db'),warehouse=warehouse.as_uri())
    if ('metadata',) not in catalog.list_namespaces():catalog.create_namespace('metadata')
    schema=Schema(NestedField(1,'entity_id',StringType(),required=False),NestedField(2,'name',StringType(),required=False),NestedField(3,'fully_qualified_name',StringType(),required=False),NestedField(4,'captured_at',StringType(),required=False))
    try:table=catalog.load_table('metadata.assets_history')
    except Exception:table=catalog.create_table('metadata.assets_history',schema=schema)
    captured=datetime.now(timezone.utc).isoformat()
    rows=[{'entity_id':e['id'],'name':e['name'],'fully_qualified_name':e['fullyQualifiedName'],'captured_at':captured} for e in entities]
    table.append(pa.Table.from_pylist(rows,schema=pa.schema([pa.field('entity_id',pa.string()),pa.field('name',pa.string()),pa.field('fully_qualified_name',pa.string()),pa.field('captured_at',pa.string())])))
    return len(rows)

async def register_lineage(subject,job:dict):
    if not token():return False
    name='flow_'+job['workflow']['id'].replace('-','_')
    service=await api('PUT','/services/pipelineServices',{'name':'nexo_temporal','serviceType':'CustomPipeline','description':'NEXO demo execution lineage'})
    pipeline=await api('PUT','/pipelines',{'name':name+'_'+subject.tenant,'service':'nexo_temporal','description':f'Workflow version {job["version"]}; run {job["id"]}. Output lives in a separate local sandbox.'})
    source=await api('GET',f'/tables/name/nexo_demo.{subject.tenant}_commerce.internal.orders')
    output=await api('PUT','/tables',{'name':job['workflow']['nodes'][-1]['config']['target'],'databaseSchema':f'nexo_demo.{subject.tenant}_commerce.internal','columns':[{'name':'name','dataType':'STRING'},{'name':'value','dataType':'DOUBLE'}],'description':'Derived local sandbox output; not a DWS table'})
    await api('PUT','/lineage',{'edge':{'fromEntity':{'id':source['id'],'type':'table'},'toEntity':{'id':output['id'],'type':'table'},'lineageDetails':{'pipeline':{'id':pipeline['id'],'type':'pipeline'}}}})
    return True

if __name__=='__main__':
    import asyncio
    print(json.dumps(asyncio.run(seed()),indent=2))
