"""Run against the local running backend; creates only synthetic local test outputs."""
import time,json,sqlite3,sys
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_core import flow
from backend.config import RUNTIME

def wait(c,job_id):
    for _ in range(60):
        job=next(j for j in c.get('/api/jobs').json() if j['id']==job_id)
        if job['status'] not in ['queued','running']:return job
        time.sleep(.3)
    raise AssertionError('Job did not close')

def main():
    checks=[]
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60) as c:
        health=c.get('/api/health').json();assert health['openjiuwen'] and health['openmetadata'] and health['temporal'] and health['iceberg'];checks.append('real local services')
        assert c.get('/api/jobs').status_code==401;checks.append('anonymous access denied')
        c.post('/api/demo/session',json={'tenant':'luma','persona':'manager'})
        assert c.post('/api/analyze',json={'question':'分析广告ROAS'}).status_code==403
        r=c.post('/api/analyze',json={'question':'分析10月各地区销售额'});assert r.status_code==200 and len(r.json()['data'])==1
        assert c.post('/api/authorize/export').status_code==403
        assert c.get('/api/jobs').json()==[];checks.append('domain, region, export and cached-run boundaries')
        c.post('/api/demo/session',json={'tenant':'luma','persona':'engineer'})
        f=flow();f['nodes'][-1]['config']['target']='integration_sales'
        r=c.post('/api/jobs',json=f);assert r.status_code==200,r.text
        job=wait(c,r.json()['id']);assert job['status']=='completed',job
        assert job.get('metadata_lineage') is True,job['logs'];checks.append('Temporal → MCP execution and OpenMetadata lineage')
        r=c.post('/api/jobs',json=f);assert wait(c,r.json()['id'])['status']=='completed'
        with sqlite3.connect(RUNTIME/'outputs.db') as db:
            count=db.execute('SELECT COUNT(*) FROM outputs WHERE tenant=? AND target=? AND partition=?',('luma','integration_sales','2026-10')).fetchone()[0]
            assert count==1
        checks.append('idempotent partition publication')
        failed=flow();failed['nodes'][2]['config']['rule']='force_fail';failed['nodes'][-1]['config']['target']='must_not_publish'
        r=c.post('/api/jobs',json=failed);assert wait(c,r.json()['id'])['status']=='failed'
        with sqlite3.connect(RUNTIME/'outputs.db') as db:assert db.execute('SELECT COUNT(*) FROM outputs WHERE target=?',('must_not_publish',)).fetchone()[0]==0
        checks.append('quality failure stops publication')
        wrong=flow();wrong['tenant']='northstar';assert c.post('/api/jobs',json=wrong).status_code==403;checks.append('forged tenant rejected')
        daily=flow();daily['id']='integration-daily';daily['schedule']='daily';daily['nodes'][-1]['config']['target']='daily_test'
        r=c.post('/api/jobs',json=daily);assert r.status_code==200,r.text
        job=r.json();assert job['schedule_id']=='nexo-luma-integration-daily'
        assert c.delete('/api/schedules/'+job['schedule_id']).status_code==200
        assert wait(c,job['id'])['status']=='completed';checks.append('Mexico City schedule registration and removal')
        c.post('/api/demo/session',json={'tenant':'northstar','persona':'engineer'})
        assert all(j['tenant']=='northstar' for j in c.get('/api/jobs').json());checks.append('tenant-isolated job listing')
    print(json.dumps({'passed':checks,'count':len(checks)},indent=2))

if __name__=='__main__':main()
