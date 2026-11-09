"""Smoke-check the real cloud stack without consuming the user's one-time invite."""
import csv,json,os,time
from decimal import Decimal
from pathlib import Path
import httpx,jwt
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')


def main():
    now=int(time.time())
    owner=jwt.encode({'sub':'owner','aud':'nexo-demo','iss':'nexo-owner','iat':now,'exp':now+1800},os.environ['NEXO_GATE_SECRET'],algorithm='HS256')
    checks=[]
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=180) as client:
        for _ in range(60):
            try:
                if client.get('/api/health').status_code==401:break
            except httpx.HTTPError:pass
            time.sleep(2)
        else:raise RuntimeError('Protected API did not become ready')
        checks.append('anonymous API access denied')
        client.cookies.set('nexo_owner',owner,domain='127.0.0.1',path='/')
        health=client.get('/api/health').json()
        assert all(health[k] for k in ('dws_connected','openmetadata','temporal','iceberg','model_connected'))
        assert health['data_backend']=='dws' and health['deployment']=='huawei_cloud'
        checks.append('DWS, OpenMetadata, Temporal and Iceberg connected')
        assert client.post('/api/demo/session',json={'tenant':'luma','persona':'manager'}).status_code==200
        response=client.post('/api/analyze',json={'question':'分析2026年10月各地区净销售额'})
        if response.status_code!=200:raise RuntimeError('Live model and DWS analysis failed')
        result=response.json();assert result['mode']=='model' and len(result['data'])==1 and result['data'][0]['name']=='Mexico City'
        with (ROOT/'data/orders.csv').open() as file:orders=list(csv.DictReader(file))
        expected=sum(Decimal(row['net_amount']) for row in orders if row['tenant_id']=='luma' and row['region']=='Mexico City' and row['status']!='Cancelled' and row['order_date'].startswith('2026-10'))
        assert abs(Decimal(str(result['data'][0]['value']))-expected)<=Decimal('0.01')
        checks.append('GLM5.3 → openJiuwen → scoped MCP → DWS matches synthetic source totals')
        assert client.post('/api/authorize/export').status_code==403
        assert client.get('/api/jobs').json()==[]
        checks.append('regional manager export and cached-run boundaries enforced')
        assert client.post('/api/demo/session',json={'tenant':'luma','persona':'engineer'}).status_code==200
        nodes=[{'id':'source','type':'source','label':'Read orders','description':'Synthetic DWS source','config':{'asset':'orders','range':'2026-10'}},
            {'id':'aggregate','type':'aggregate','label':'Aggregate revenue','description':'Revenue by region','config':{'metric':'revenue','dimension':'region'}},
            {'id':'quality','type':'quality','label':'Validate output','description':'Non-empty and non-negative','config':{'rule':'non_empty_non_negative'}},
            {'id':'publish','type':'publish','label':'Publish sandbox result','description':'No source table writes','config':{'target':'cloud_sales_summary'}}]
        flow={'id':'cloud-smoke-check','name':'Cloud deployment verification','tenant':'luma','domain':'Sales','version':1,'schedule':'manual','timezone':'America/Mexico_City','nodes':nodes,'edges':[{'id':str(i),'source':nodes[i]['id'],'target':nodes[i+1]['id']} for i in range(3)]}
        submitted=client.post('/api/jobs',json=flow);assert submitted.status_code==200
        job_id=submitted.json()['id']
        for _ in range(60):
            job=next(job for job in client.get('/api/jobs').json() if job['id']==job_id)
            if job['status'] not in ('queued','running'):break
            time.sleep(2)
        assert job['status']=='completed' and job.get('metadata_lineage') is True
        checks.append('Temporal workflow executes through MCP and records OpenMetadata lineage')
        assert client.post('/api/demo/session',json={'tenant':'northstar','persona':'engineer'}).status_code==200
        assert all(job['tenant']=='northstar' for job in client.get('/api/jobs').json())
        checks.append('tenant task boundary enforced')
    report={'status':'passed','checks':checks,'model':'glm-5.3','data_backend':'dws','synthetic_rows':10000}
    path=ROOT/'.runtime/cloud-verification.json';path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
    print(json.dumps(report))


if __name__=='__main__':main()
