"""Owner login for the internet-facing synthetic demo, separate from demo RBAC."""
from __future__ import annotations
import base64,hashlib,hmac,json,os,secrets,time
from pathlib import Path
from collections import defaultdict,deque
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse
from pydantic import BaseModel,Field
import jwt
from .config import RUNTIME
from .localization import MESSAGES,translate

router=APIRouter()
COOKIE='nexo_owner'
PASSWORD_FILE=RUNTIME/'owner-password.json'
attempts=defaultdict(deque)


def enabled():return bool(os.getenv('NEXO_GATE_SECRET'))


def authenticated(request:Request):
    try:
        claims=jwt.decode(request.cookies.get(COOKIE,''),os.environ['NEXO_GATE_SECRET'],algorithms=['HS256'],audience='nexo-demo',issuer='nexo-owner')
        return claims.get('sub')=='owner'
    except (jwt.PyJWTError,KeyError):return False


async def gate(request:Request,call_next):
    if enabled() and request.url.path not in ('/login','/auth/login','/auth/enroll') and not authenticated(request):
        if request.url.path.startswith('/api/'):
            return JSONResponse({'detail':'请先登录演示环境'},status_code=401)
        return RedirectResponse('/login',status_code=303)
    response=await call_next(request)
    if enabled():response.headers['Cache-Control']='no-store'
    return response


def limit(request):
    if not enabled():raise HTTPException(404)
    key=request.client.host if request.client else 'unknown'
    queue=attempts[key];now=time.monotonic()
    while queue and queue[0]<now-300:queue.popleft()
    if len(queue)>=12:raise HTTPException(429,'尝试次数过多，请五分钟后再试')
    queue.append(now)


def password_hash(password,salt):
    return hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()


def signed_in():
    now=int(time.time())
    token=jwt.encode({'sub':'owner','aud':'nexo-demo','iss':'nexo-owner','iat':now,'exp':now+7*86400},os.environ['NEXO_GATE_SECRET'],algorithm='HS256')
    response=JSONResponse({'ok':True})
    response.set_cookie(COOKIE,token,httponly=True,secure=True,samesite='strict',max_age=7*86400,path='/')
    return response


class Login(BaseModel):
    password:str=Field(min_length=12,max_length=128)


class Enrollment(Login):
    token:str=Field(min_length=32,max_length=128)


@router.post('/auth/enroll')
async def enroll(body:Enrollment,request:Request):
    limit(request)
    expected=os.getenv('NEXO_INVITE_SHA256','')
    if PASSWORD_FILE.exists() or not expected or int(os.getenv('NEXO_INVITE_EXPIRES','0'))<time.time() or not hmac.compare_digest(hashlib.sha256(body.token.encode()).hexdigest(),expected):
        raise HTTPException(403,'邀请已使用、失效或不正确')
    salt=secrets.token_bytes(16)
    record={'salt':salt.hex(),'hash':password_hash(body.password,salt)}
    try:
        with open(PASSWORD_FILE,'x',opener=lambda p,f:os.open(p,f,0o600)) as file:json.dump(record,file)
    except FileExistsError:raise HTTPException(403,'邀请已使用')
    return signed_in()


@router.post('/auth/login')
async def login(body:Login,request:Request):
    limit(request)
    if not PASSWORD_FILE.exists():raise HTTPException(403,'请使用首次访问邀请链接设置密码')
    record=json.loads(PASSWORD_FILE.read_text())
    if not hmac.compare_digest(password_hash(body.password,bytes.fromhex(record['salt'])),record['hash']):
        raise HTTPException(401,'密码不正确')
    return signed_in()


LOGIN_COPY_KEYS=['切换语言', '登录演示环境', '设置演示访问密码', '输入你为此演示环境设置的访问密码。', '邀请链接只能使用一次。设置密码后即可进入工作台。', '访问密码（至少 12 个字符）', '再次输入密码', '继续', '这是独立的演示访问密码。请使用新密码，不要填写华为云密码、API Key 或 Google 密码。演示中可切换的租户与角色均为合成数据场景。', '两次输入的密码不一致', '请检查输入后重试', '密码不正确', '请使用首次访问邀请链接设置密码', '邀请已使用、失效或不正确', '邀请已使用', '尝试次数过多，请五分钟后再试', '登录 · NEXO Data Agent']
LOGIN_COPY={locale:{key:translate(key,locale=locale) for key in LOGIN_COPY_KEYS} for locale in ['zh-CN','en-US','es-ES']}
LOGIN_HTML='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>登录 · NEXO Data Agent</title><style>*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:#f6f7f9;color:#25262b;font:16px/1.7 system-ui,sans-serif;font-family:var(--font-sans,system-ui);display:grid;min-height:100vh;place-items:center;padding:80px 24px 24px}main{width:min(480px,100%);background:white;padding:40px;border-radius:24px;border:1px solid #e6e7eb;box-shadow:0 16px 60px #25262b08;border-top:5px solid #ff441f}.logo{font-weight:800;letter-spacing:.1em;font-size:21px;color:#25262b}h1{font-size:28px;line-height:1.4;margin:30px 0 14px;letter-spacing:-.5px}p{font-size:16px;line-height:1.8;color:#606572}label{font-size:15px;display:block;margin-top:24px;font-weight:500}input{display:block;width:100%;font:inherit;padding:14px;margin:10px 0;border:1px solid #d8dbe4;border-radius:10px;color:#25262b;background:#fcfcfe}input:focus-visible,button:focus-visible{outline:3px solid #ffad94;outline-offset:3px}button{margin-top:18px;width:100%;min-height:50px;border:0;border-radius:11px;background:#d93614;color:white;padding:14px;font:inherit;font-weight:600;cursor:pointer}button:hover{background:#bc2d10}button:disabled{opacity:.6;cursor:wait}#error{color:#b72838;min-height:24px;font-size:14px}small{display:block;margin-top:26px;color:#606572;font-size:14px;line-height:1.8}@media(max-width:480px){body{padding:76px 18px 24px}main{padding:30px 24px;border-radius:20px}h1{font-size:26px}.logo{font-size:18px}}\n\n.login-language{position:absolute;right:24px;top:20px;display:flex;align-items:center;gap:8px;color:#606572;font-size:14px}.login-language select{font:inherit;color:#25262b;border:1px solid #d8dbe4;border-radius:9px;background:white;padding:9px 12px;min-height:40px}\n</style>\n<label class="login-language"><span aria-hidden="true">◎</span><select id="language" aria-label="切换语言"><option value="zh-CN">简体中文</option><option value="en-US">English (US)</option><option value="es-ES">Español</option></select></label>\n<main><div class="logo">NEXO<span style="color:#d93614"> / </span>DATA AGENT</div><h1 id="title">登录演示环境</h1><p id="intro">输入你为此演示环境设置的访问密码。</p><form><label><span data-i18n="访问密码（至少 12 个字符）">访问密码（至少 12 个字符）</span><input id="password" type="password" minlength="12" maxlength="128" required autocomplete="current-password"></label><label id="confirm-label" hidden><span data-i18n="再次输入密码">再次输入密码</span><input id="confirm" type="password" minlength="12" maxlength="128" autocomplete="new-password"></label><button type="submit" data-i18n="继续">继续</button><p id="error" role="alert"></p></form><small data-i18n="这是独立的演示访问密码。请使用新密码，不要填写华为云密码、API Key 或 Google 密码。演示中可切换的租户与角色均为合成数据场景。">这是独立的演示访问密码。</small></main><script>\nconst COPY=__COPY__;\nconst FONTS={\'zh-CN\':\'"Microsoft YaHei", "微软雅黑", "PingFang SC", "Noto Sans SC", sans-serif\',\'en-US\':\'Arial, Helvetica, sans-serif\',\'es-ES\':\'Verdana, "Segoe UI", Arial, sans-serif\'};\nconst token=new URLSearchParams(location.hash.slice(1)).get(\'invite\');history.replaceState(null,\'\',\'/login\');\nlet language=\'zh-CN\';let errorKey=\'\';try{const stored=localStorage.getItem(\'nexo-locale\');if(Object.hasOwn(FONTS,stored))language=stored;}catch{}\nconst t=key=>COPY[language][key]||key;\nfunction paint(){document.documentElement.lang=language;document.documentElement.style.setProperty(\'--font-sans\',FONTS[language]);document.title=t(\'登录 · NEXO Data Agent\');document.querySelector(\'#language\').value=language;document.querySelector(\'#language\').setAttribute(\'aria-label\',t(\'切换语言\'));document.querySelectorAll(\'[data-i18n]\').forEach(node=>node.textContent=t(node.dataset.i18n));document.querySelector(\'#title\').textContent=t(token?\'设置演示访问密码\':\'登录演示环境\');document.querySelector(\'#intro\').textContent=t(token?\'邀请链接只能使用一次。设置密码后即可进入工作台。\':\'输入你为此演示环境设置的访问密码。\');document.querySelector(\'#error\').textContent=t(errorKey);}\nif(token){document.querySelector(\'#confirm-label\').hidden=false;document.querySelector(\'#confirm\').required=true;document.querySelector(\'#password\').autocomplete=\'new-password\';}\npaint();document.querySelector(\'#language\').onchange=event=>{if(!Object.hasOwn(FONTS,event.target.value))return;language=event.target.value;try{localStorage.setItem(\'nexo-locale\',language);}catch{}paint();};\ndocument.querySelector(\'form\').onsubmit=async(event)=>{event.preventDefault();const button=document.querySelector(\'button\');const password=document.querySelector(\'#password\').value;if(token&&password!==document.querySelector(\'#confirm\').value){errorKey=\'两次输入的密码不一致\';paint();return;}button.disabled=true;errorKey=\'\';paint();try{const response=await fetch(token?\'/auth/enroll\':\'/auth/login\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(token?{token,password}:{password})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail===\'string\'?data.detail:\'请检查输入后重试\');location.assign(\'/\');}catch(e){errorKey=e.message;paint();}finally{button.disabled=false;}};\n</script></html>'.replace('__COPY__',json.dumps(LOGIN_COPY,ensure_ascii=False).replace('<','\\u003c'))


@router.get('/login')
async def login_page(request:Request):
    if not enabled():raise HTTPException(404)
    if authenticated(request):return RedirectResponse('/',status_code=303)
    script=LOGIN_HTML.split('<script>',1)[1].split('</script>',1)[0]
    digest=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return HTMLResponse(LOGIN_HTML,headers={'Content-Security-Policy':f"default-src 'none'; script-src 'sha256-{digest}'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",'Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})
