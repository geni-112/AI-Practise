import asyncio
from dataclasses import replace
import httpx
import pytest


def test_expired_local_metadata_session_renews_once(monkeypatch,tmp_path):
    from backend import metadata
    token_file=tmp_path/'token'
    token_file.write_text('expired-local-token')
    monkeypatch.setattr(metadata,'TOKEN_FILE',token_file)
    monkeypatch.setattr(metadata,'settings',replace(metadata.settings,demo=True,metadata_url='http://127.0.0.1:8585',metadata_token=''))
    seen=[]
    def respond(request):
        seen.append(request)
        if request.url.path.endswith('/users/login'):
            return httpx.Response(200,json={'accessToken':'renewed-local-token'})
        if request.headers.get('Authorization')=='Bearer renewed-local-token':
            return httpx.Response(200,json={'data':[]})
        return httpx.Response(401,json={'message':'Expired token'})
    original=httpx.AsyncClient
    monkeypatch.setattr(metadata.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    assert asyncio.run(metadata.api('GET','/tables'))=={'data':[]}
    assert len(seen)==3 and sum(r.url.path.endswith('/users/login') for r in seen)==1
    assert token_file.read_text()=='renewed-local-token'
    assert token_file.stat().st_mode&0o777==0o600


@pytest.mark.parametrize('url,configured_token',[
    ('https://metadata.example.test',''),
    ('http://127.0.0.1:8585','externally-configured-token'),
])
def test_metadata_unauthorized_does_not_bootstrap_other_services(monkeypatch,tmp_path,url,configured_token):
    from backend import metadata
    monkeypatch.setattr(metadata,'TOKEN_FILE',tmp_path/'missing-token')
    monkeypatch.setattr(metadata,'settings',replace(metadata.settings,demo=True,metadata_url=url,metadata_token=configured_token))
    seen=[]
    def respond(request):
        seen.append(request)
        return httpx.Response(401,json={'message':'private upstream diagnostics'})
    original=httpx.AsyncClient
    monkeypatch.setattr(metadata.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    with pytest.raises(RuntimeError,match='HTTP 401'):
        asyncio.run(metadata.api('GET','/tables'))
    assert len(seen)==1 and not seen[0].url.path.endswith('/users/login')
