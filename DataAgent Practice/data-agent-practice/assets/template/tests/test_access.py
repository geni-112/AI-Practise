import hashlib,time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def gated(monkeypatch,tmp_path):
    from backend import access
    token='one-time-demo-invitation-token-123456789'
    monkeypatch.setenv('NEXO_GATE_SECRET','fake-test-session-signing-key-123456789')
    monkeypatch.setenv('NEXO_INVITE_SHA256',hashlib.sha256(token.encode()).hexdigest())
    monkeypatch.setenv('NEXO_INVITE_EXPIRES',str(int(time.time())+300))
    monkeypatch.setattr(access,'PASSWORD_FILE',tmp_path/'owner.json')
    access.attempts.clear()
    app=FastAPI();app.middleware('http')(access.gate);app.include_router(access.router)
    @app.get('/api/protected')
    async def protected():return {'protected':True}
    with TestClient(app,base_url='https://demo.example.test') as client:yield client,token,access


def test_gate_requires_auth_for_assets_and_api(gated):
    client,_,_=gated
    assert client.get('/api/protected').status_code==401
    assert client.get('/demo-data.json',follow_redirects=False).status_code==303
    page=client.get('/login');assert page.status_code==200
    assert "frame-ancestors 'none'" in page.headers['content-security-policy']


def test_one_time_invite_and_persistent_password(gated):
    client,token,access=gated
    password='independent-demo-password-123'
    assert client.post('/auth/enroll',json={'token':'wrong-invitation-token-1234567890123456','password':password}).status_code==403
    response=client.post('/auth/enroll',json={'token':token,'password':password})
    assert response.status_code==200
    cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'secure' in cookie
    assert client.get('/api/protected').status_code==200
    assert password not in access.PASSWORD_FILE.read_text()
    assert access.PASSWORD_FILE.stat().st_mode&0o777==0o600
    assert client.post('/auth/enroll',json={'token':token,'password':password}).status_code==403
    client.cookies.clear()
    assert client.post('/auth/login',json={'password':'incorrect-password-123'}).status_code==401
    assert client.post('/auth/login',json={'password':password}).status_code==200
    assert client.get('/api/protected').status_code==200


def test_expired_invitation_is_rejected(gated,monkeypatch):
    client,token,_=gated
    monkeypatch.setenv('NEXO_INVITE_EXPIRES','1')
    assert client.post('/auth/enroll',json={'token':token,'password':'new-demo-password-123'}).status_code==403
