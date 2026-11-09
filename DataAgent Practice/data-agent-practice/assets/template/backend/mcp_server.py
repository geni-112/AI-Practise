"""Scoped MCP gateway: demo SQLite or DWS. No free-form execute_sql tool is exposed."""
from __future__ import annotations
import os,json,sqlite3,re
from decimal import Decimal
from fastmcp import FastMCP
from .config import ROOT,RUNTIME,settings
from .policy import Subject,authorize,METRIC_DOMAINS,ASSET_DOMAINS
from .planning import Plan,compile_sql

mcp=FastMCP('nexo-scoped-data')
# Created by the authenticated application, not supplied by model tool arguments.
subject=Subject(os.environ['NEXO_SUBJECT_TENANT'],os.environ['NEXO_SUBJECT_PERSONA'])

@mcp.tool
async def list_assets()->list[dict]:
    from .metadata import catalog
    registered=await catalog(subject.tenant,subject.role['domains'])
    if registered is not None:
        for item in registered:await authorize(subject,'discover',item['domain'])
        return registered
    result=[]
    for name,domain in ASSET_DOMAINS.items():
        if domain in subject.role['domains']:
            await authorize(subject,'discover',domain)
            result.append({'name':name,'domain':domain})
    return result

@mcp.tool
async def execute_plan(plan:dict,completed_only:bool=False)->dict:
    parsed=Plan.model_validate(plan)
    await authorize(subject,'query',METRIC_DOMAINS[parsed.metric])
    sql,params,sources=compile_sql(parsed,subject.tenant,subject.role.get('region'),completed_only)
    if settings.data_backend=='sqlite':
        conn=sqlite3.connect(f'file:{RUNTIME / "warehouse.db"}?mode=ro',uri=True);conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        try:rows=[dict(row) for row in conn.execute(sql,params).fetchall()]
        finally:conn.close()
    elif settings.data_backend=='dws':
        from .database import connect_dws
        # The official DWS MCP server also uses Psycopg2. This scoped adapter
        # exposes approved plans instead of arbitrary model-authored SQL.
        conn=connect_dws()
        conn.set_session(readonly=True)
        sql=sql.replace('?', '%s')
        for table in sorted(ASSET_DOMAINS,key=len,reverse=True):sql=re.sub(r'\b(FROM|JOIN) '+table+r'\b',lambda m:m.group(1)+' '+('external' if table in ['ad_metrics','competitor_prices','reviews'] else 'internal')+'.'+table,sql)
        try:
            with conn.cursor() as cur:
                cur.execute('SET statement_timeout = 60000');cur.execute(sql,params);columns=[c[0] for c in cur.description];rows=[{key:float(value) if isinstance(value,Decimal) else value for key,value in zip(columns,row)} for row in cur.fetchall()]
        finally:conn.close()
    else:raise ValueError('Unknown data backend')
    return {'data':rows,'sql':sql,'params':params,'sources':sources,'backend':settings.data_backend}

@mcp.tool
async def publish_result(target:str,rows:list[dict],partition:str,run_id:str)->dict:
    await authorize(subject,'execute','Sales')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,60}',target):raise ValueError('Invalid output target')
    if not re.fullmatch(r'2026-(0[4-9]|10)',partition):raise ValueError('Invalid partition')
    if len(rows)>1000:raise ValueError('Result too large')
    # Demo outputs are deliberately kept in a separate local database; never
    # mutate source warehouse tables. Same tenant/target/partition is idempotent.
    conn=sqlite3.connect(RUNTIME/'outputs.db')
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS outputs (tenant TEXT,target TEXT,partition TEXT,run_id TEXT,payload TEXT,PRIMARY KEY(tenant,target,partition))')
        conn.execute('INSERT INTO outputs VALUES (?,?,?,?,?) ON CONFLICT(tenant,target,partition) DO UPDATE SET run_id=excluded.run_id,payload=excluded.payload',(subject.tenant,target,partition,run_id,json.dumps(rows,default=str)));conn.commit()
    finally:conn.close()
    return {'target':f'sandbox.{target}','rows':len(rows),'location':'local_outputs','tenant':subject.tenant,'partition':partition}

if __name__=='__main__':mcp.run(transport='stdio',show_banner=False)
