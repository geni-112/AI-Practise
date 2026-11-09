from __future__ import annotations
import os,sys,json,uuid
from datetime import datetime,timezone
from openjiuwen.core.workflow import Workflow,WorkflowComponent,Start,End,create_workflow_session
from openjiuwen.core.foundation.tool import McpServerConfig
from openjiuwen.core.foundation.tool.mcp.client.stdio_client import StdioClient
from .config import ROOT
from .policy import Subject,authorize,METRIC_DOMAINS
from .planning import make_plan
from .localization import Locale,translate

async def call_mcp(subject:Subject,tool:str,arguments:dict):
    env={**os.environ,'PYTHONPATH':str(ROOT),'NEXO_SUBJECT_TENANT':subject.tenant,'NEXO_SUBJECT_PERSONA':subject.persona}
    client=StdioClient(McpServerConfig(server_name='scoped-data',server_path='backend.mcp_server',client_type='stdio',params={'command':sys.executable,'args':['-m','backend.mcp_server'],'env':env,'cwd':str(ROOT)}))
    if not await client.connect(timeout=20):raise RuntimeError('MCP connection failed')
    try:
        result=await client.call_tool(tool,arguments,timeout=90)
        if getattr(result,'success',True) is False:raise RuntimeError(str(getattr(result,'error','MCP operation failed')))
        if not isinstance(result,(str,dict,list)) and hasattr(result,'data'):result=result.data
        if isinstance(result,str):return json.loads(result)
        return result
    finally:await client.disconnect()

class CatalogStep(WorkflowComponent):
    async def invoke(self,inputs,session,context):
        request=inputs['request'];subject=Subject(**request['subject'])
        catalog=await call_mcp(subject,'list_assets',{})
        return {'request':request,'catalog':catalog}

class PlanningStep(WorkflowComponent):
    async def invoke(self,inputs,session,context):
        request=inputs['request'];subject=Subject(**request['subject'])
        plan,mode=await make_plan(request['question'],request.get('previous'),inputs['catalog'],request.get('locale','zh-CN'))
        await authorize(subject,'query',METRIC_DOMAINS[plan.metric])
        return {'request':request,'plan':plan.model_dump(),'mode':mode}

class ExecuteStep(WorkflowComponent):
    async def invoke(self,inputs,session,context):
        request=inputs['request'];subject=Subject(**request['subject']);plan=inputs['plan']
        result=await call_mcp(subject,'execute_plan',{'plan':plan})
        data=result['data'];top=data[0] if data else None
        locale=request.get('locale','zh-CN')
        summary=translate('已通过 openJiuwen → MCP 在 {0} 执行受控查询，返回 {1} 个分组。',(result['backend'],len(data)),locale)
        if top:summary+=' '+translate('首项为 {0}，数值 {1}。',(top['name'],top['value']),locale)
        summary+=' '+translate('当前使用合成数据；规则演示模式未调用大模型。' if inputs['mode']=='demo_rules' else '分析计划由已配置模型生成，SQL 由受控编译器生成。',locale=locale)
        steps=[translate(step,locale=locale) for step in ['解析服务端身份与租户','通过 MCP 检索可见资产','生成并校验结构化计划','按域与地区范围编译 SQL','通过 MCP 执行并返回结果']]
        return {'response':{'id':str(uuid.uuid4()),'question':request['question'],'title':plan['title'],'summary':summary,'data':data,'metric':plan['metric'],'dimension':plan['dimension'],'sql':result['sql'],'steps':steps,'sources':result['sources'],'mode':inputs['mode'],'plan':plan,'createdAt':datetime.now(timezone.utc).isoformat()}}

async def analyze(question:str,subject:Subject,previous:dict|None=None,locale:Locale='zh-CN'):
    workflow=Workflow()
    workflow.set_start_comp('start',Start(),inputs_schema={'request':'${request}'})
    workflow.add_workflow_comp('catalog',CatalogStep(),inputs_schema={'request':'${start.request}'})
    workflow.add_workflow_comp('plan',PlanningStep(),inputs_schema={'request':'${catalog.request}','catalog':'${catalog.catalog}'})
    workflow.add_workflow_comp('execute',ExecuteStep(),inputs_schema={'request':'${plan.request}','plan':'${plan.plan}','mode':'${plan.mode}'})
    workflow.set_end_comp('end',End(),inputs_schema={'response':'${execute.response}'})
    for a,b in [('start','catalog'),('catalog','plan'),('plan','execute'),('execute','end')]:workflow.add_connection(a,b)
    from dataclasses import asdict
    output=await workflow.invoke({'request':{'question':question,'subject':asdict(subject),'previous':previous,'locale':locale}},create_workflow_session(session_id=str(uuid.uuid4())))
    result=output.result
    if isinstance(result,dict) and 'output' in result:result=result['output']
    if not isinstance(result,dict) or 'response' not in result:raise RuntimeError('Agent workflow did not produce a response')
    return result['response']
