"""Local fake HTTP endpoint verifies provider configurability without calling any AI service."""
import asyncio,json,threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest

@pytest.mark.parametrize('locale',['zh-CN','en-US','es-ES'])
@pytest.mark.parametrize('model_name',['glm-5.3','another-configured-model'])
def test_openjiuwen_openai_compatible_contract(monkeypatch,model_name,locale):
    from backend import planning
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append(payload)
            content=json.dumps({'metric':'revenue','dimension':'region','month':'2026-10','region':None,'title':'Sales analysis'})
            body=json.dumps({'id':'fake-local-response','object':'chat.completion','created':0,'model':model_name,'choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(planning,'settings',replace(planning.settings,model_provider='huawei_maas' if model_name=='glm-5.3' else 'openai_compatible',model_name=model_name,model_base_url=f'http://127.0.0.1:{server.server_port}/v1',model_api_key='fake-local-test-key',model_timeout=10))
    try:
        plan,mode=asyncio.run(planning.make_plan('sales by region',None,[{'name':'orders'}],locale=locale))
        assert mode=='model' and plan.metric=='revenue'
        assert seen and seen[0]['model']==model_name
        from backend.localization import LANGUAGES
        assert LANGUAGES[locale] in seen[0]['messages'][0]['content']
    finally:server.shutdown();server.server_close()
