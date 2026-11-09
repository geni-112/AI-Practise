import asyncio,json,sqlite3
from pathlib import Path
import pytest
from pydantic import ValidationError
from backend.config import ROOT,RUNTIME
from backend.policy import Subject,authorize
from backend.planning import Plan,compile_sql,rule_plan
from backend.jobs import validate_flow

@pytest.fixture(scope='module')
def warehouse():
    if not (RUNTIME/'warehouse.db').exists():
        from scripts.generate_data import generate
        generate()
    c=sqlite3.connect(RUNTIME/'warehouse.db');c.row_factory=sqlite3.Row
    yield c
    c.close()

def test_exact_row_count_and_english_data(warehouse):
    manifest=json.loads((ROOT/'data/manifest.json').read_text())
    assert sum(warehouse.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in manifest['tables'])==10000
    assert manifest['language']=='English' and manifest['synthetic'] is True
    for row in warehouse.execute('SELECT review_text FROM reviews'):
        assert row[0].isascii()

@pytest.mark.parametrize('left,right,key',[('order_items','orders','order_id'),('order_items','products','product_id'),('orders','customers','customer_id'),('returns','orders','order_id'),('shipments','orders','order_id'),('inventory','products','product_id'),('ad_metrics','campaigns','campaign_id'),('reviews','products','product_id')])
def test_cross_table_keys_preserve_tenants(warehouse,left,right,key):
    count=warehouse.execute(f'SELECT COUNT(*) FROM {left} a LEFT JOIN {right} b ON a.{key}=b.{key} AND a.tenant_id=b.tenant_id WHERE b.{key} IS NULL').fetchone()[0]
    assert count==0

def test_order_money_reconciles_to_lines(warehouse):
    count=warehouse.execute('SELECT COUNT(*) FROM (SELECT o.order_id FROM orders o JOIN order_items i ON o.order_id=i.order_id AND o.tenant_id=i.tenant_id GROUP BY o.order_id,o.net_amount HAVING ABS(o.net_amount-SUM(i.net_amount))>0.01)').fetchone()[0]
    assert count==0

@pytest.mark.parametrize('tenant,region',[('luma',None),('northstar',None),('luma','Mexico City')])
def test_scoped_query_matches_independent_sum(warehouse,tenant,region):
    sql,params,_=compile_sql(Plan(),tenant,region)
    rows=warehouse.execute(sql,params).fetchall()
    expected=warehouse.execute("SELECT SUM(net_amount) FROM orders WHERE tenant_id=? AND status<>'Cancelled' AND order_date BETWEEN '2026-10-01' AND '2026-10-31'"+(' AND region=?' if region else ''),[tenant]+([region] if region else [])).fetchone()[0]
    assert sum(r['value'] for r in rows)==pytest.approx(expected,abs=.01)
    if region:assert {r['name'] for r in rows}=={region}

def test_plan_rejects_sql_injection_and_region_escape():
    with pytest.raises(ValidationError):Plan(dimension='region; DROP TABLE orders')
    with pytest.raises(ValidationError):Plan(month="2026-10' OR 1=1--")
    with pytest.raises(PermissionError):compile_sql(Plan(region='North'),'luma','Mexico City')

@pytest.mark.parametrize('metric',['roas','stock','pricing'])
def test_period_filter_is_not_ignored_for_external_or_snapshot_data(warehouse,metric):
    sql,params,_=compile_sql(Plan(metric=metric,month='2026-09'),'luma')
    assert warehouse.execute(sql,params).fetchall()==[]

def test_domain_and_execution_authorization():
    with pytest.raises(PermissionError):asyncio.run(authorize(Subject('luma','manager'),'query','Marketing'))
    with pytest.raises(PermissionError):asyncio.run(authorize(Subject('luma','analyst'),'execute','Sales'))
    assert asyncio.run(authorize(Subject('luma','engineer'),'execute','Sales'))

def flow():
    nodes=[{'id':'source','type':'source','label':'Read','description':'orders','config':{'asset':'orders','range':'2026-10'}},{'id':'agg','type':'aggregate','label':'Aggregate','description':'region','config':{'dimension':'region','metric':'revenue'}},{'id':'quality','type':'quality','label':'Check','description':'quality','config':{'rule':'non_empty_non_negative'}},{'id':'publish','type':'publish','label':'Publish','description':'sandbox','config':{'target':'test_sales','mode':'replace_partition'}}]
    return {'id':'test-flow','name':'Test sales flow','tenant':'luma','domain':'Sales','version':1,'schedule':'manual','timezone':'America/Mexico_City','nodes':nodes,'edges':[{'id':str(i),'source':a['id'],'target':b['id']} for i,(a,b) in enumerate(zip(nodes,nodes[1:]))]}

def test_flow_validation():
    f=flow();assert len(validate_flow(f,'luma'))==4
    with pytest.raises(PermissionError):validate_flow(f,'northstar')
    f['edges'].append({'id':'cycle','source':'publish','target':'source'})
    with pytest.raises(ValueError):validate_flow(f,'luma')
    f=flow();f['nodes'][-1]['config']['target']='orders; DROP TABLE orders'
    with pytest.raises(ValueError):validate_flow(f,'luma')

def test_real_openjiuwen_mcp_query(warehouse):
    from backend.agent import analyze
    result=asyncio.run(analyze('分析10月各地区销售额',Subject('luma','manager')))
    assert result['mode']=='demo_rules'
    assert len(result['data'])==1 and result['data'][0]['name']=='Mexico City'
    assert result['data'][0]['value']==pytest.approx(7180.33)

def test_missing_model_is_not_silently_another_provider(monkeypatch):
    from backend import planning
    from dataclasses import replace
    monkeypatch.setattr(planning,'settings',replace(planning.settings,demo=False,model_api_key='',model_base_url=''))
    with pytest.raises(RuntimeError):asyncio.run(planning.make_plan('sales',None,[]))
