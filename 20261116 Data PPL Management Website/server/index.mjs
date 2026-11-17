import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { randomUUID } from 'node:crypto';
import { isIP } from 'node:net';
import { fileURLToPath } from 'node:url';
import { createPool, database, migrate, transaction } from './database.mjs';
import { sessionUser, authRoute, authError, initializeAccounts, ensureInitialAccount, readInitialPassword } from './auth.mjs';
import { fileStore } from './files.mjs';
import {createMfa} from './mfa.mjs';
import {deleteMember} from './members.mjs';
import {createPracticeService,initializePracticeRoles} from './practices.mjs';
import application, { initialize, initializeReportHistory, initializeAssignmentPermission } from '../dist/server/index.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const json = (data, status = 200) => new Response(JSON.stringify(data), {status,headers:{'Content-Type':'application/json; charset=utf-8'}});
const protectedHeaders = ['oai-authenticated-user-id','oai-authenticated-user-email','oai-authenticated-user-full-name'];
export async function createApplication(options = {}) {
  const env = options.env || process.env;
  const origin = new URL(env.APP_ORIGIN || 'http://127.0.0.1:3000').origin;
  const secure = origin.startsWith('https:');
  const editorOrigin=new URL(env.DRAWIO_ORIGIN||(secure?'https://drawio.'+new URL(origin).hostname:'http://127.0.0.1:3114')).origin;
  if(editorOrigin===origin||secure&&!editorOrigin.startsWith('https:'))throw new Error('DRAWIO_ORIGIN requires a separate HTTPS origin in production');
  if (env.NODE_ENV === 'production' && !secure) throw new Error('Production requires an HTTPS APP_ORIGIN');
  const initialPassword = await readInitialPassword(env);
  const pool = options.pool || createPool({...env,DB_SSL_CA:env.DB_SSL_CA_FILE ? await fs.readFile(env.DB_SSL_CA_FILE,'utf8') : undefined});
  const files = fileStore(env.UPLOAD_DIR || path.join(root,'.data','uploads'));
  const adminEmail = String(env.ADMIN_EMAIL || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(adminEmail)) throw new Error('ADMIN_EMAIL is required');
  await migrate(pool);
  await transaction(pool, client => initialize(database(client), {ADMIN_EMAIL:adminEmail}));
  await transaction(pool, client => initializeAccounts(client,adminEmail,initialPassword));
  await transaction(pool,initializePracticeRoles);
  await transaction(pool,async client=>{
    await client.query("SELECT id FROM records WHERE id='setup-v2' FOR UPDATE");
    await initializeReportHistory(database(client));
    await initializeAssignmentPermission(database(client));
  });
  const mfa=await createMfa({env,secure,enforce:options.mfaRequired!==false});
  const practices=await createPracticeService({pool,files,env,editorOrigin,fetchImpl:options.maasFetch,probeFactory:options.visionProbe});
  async function handle(request, ip = 'local') {
    const url = new URL(request.url);
    const publicAsset=['/style.css','/brand.svg','/ui-icons.svg'].includes(url.pathname);
    const settingsPage=['/settings','/settings/maas'].includes(url.pathname)&&['GET','HEAD'].includes(request.method);
    const reviewSlug=['GET','HEAD'].includes(request.method)?url.pathname.match(/^\/best-practices\/reviews\/([a-z0-9][a-z0-9-]{0,63})$/)?.[1]:null;
    const next=settingsPage?(url.pathname==='/settings/maas'||url.searchParams.get('section')==='ai'?'maas':'settings'):reviewSlug?'review-'+reviewSlug:'';
    function loginURL(required){
      const params=new URLSearchParams();
      if(required)params.set('change-password','required');
      if(next)params.set('next',next);
      return params.size?'/login?'+params.toString():'/login';
    }
    try {
      if (url.pathname === '/healthz' && request.method === 'GET') {
        await transaction(pool, client => client.query('SELECT 1'));
        return json({status:'ok'});
      }
      if (url.pathname === '/login' || url.pathname === '/login.js' || url.pathname === '/i18n.js') {
        return new Response(await fs.readFile(path.join(root,'public',url.pathname === '/login' ? 'login.html' : url.pathname.slice(1))),{headers:{'Content-Type':url.pathname.endsWith('.js')?'text/javascript; charset=utf-8':'text/html; charset=utf-8'}});
      }
      const write = !['GET','HEAD'].includes(request.method);
      if (write) {
        if (request.headers.get('origin') !== origin) throw authError(403,'请求来源无效，请刷新页面');
        if (!request.headers.get('content-type')?.startsWith('application/json')) throw authError(415,'仅支持 JSON 请求');
        const text = await request.text();
        if (Buffer.byteLength(text)>3100000) throw authError(413,'提交内容过大');
        let body; try { body=JSON.parse(text); } catch { throw authError(400,'JSON 格式无效'); }
        if (!body || typeof body !== 'object' || Array.isArray(body)) throw authError(400,'请求内容须为对象');
        request = new Request(url,{method:request.method,headers:request.headers,body:text});
      }
      const loginAttempt = url.pathname === '/api/auth/login'||url.pathname.startsWith('/api/auth/mfa/');
      const response=await transaction(pool, async client => {
        const user = await sessionUser(client,request,secure);
        if(user)user.mfa=await mfa.status(client,user,request);
        const auth = await authRoute(client,request,user,{origin,secure,initialPassword,mfa},ip);
        if (auth) return auth;
        if (!user && !publicAsset) {
          return url.pathname.startsWith('/api/') ? json({error:'登录已过期，请重新登录'},401) : new Response(null,{status:303,headers:{Location:loginURL(false)}});
        }
        if (user?.mustChangePassword && !publicAsset) {
          return url.pathname.startsWith('/api/') ? json({error:'请先修改初始密码',code:'PASSWORD_CHANGE_REQUIRED'},403) : new Response(null,{status:303,headers:{Location:loginURL(true)}});
        }
        if(user?.mfa?.required&&!user.mfa.verified&&!publicAsset){
          return url.pathname.startsWith('/api/')?json({error:'请完成管理员登录验证',code:'MFA_REQUIRED'},403):new Response(null,{status:303,headers:{Location:loginURL(false)}});
        }
        if(settingsPage&&user.roleId!=='admin')throw authError(403,'当前角色没有此操作权限');
        if(settingsPage)return new Response(await fs.readFile(path.join(root,'public','index.html')),{headers:{'Content-Type':'text/html; charset=utf-8'}});
        if(reviewSlug){
          if(user.roleId!=='admin')throw authError(403,'当前角色没有此操作权限');
          const reviewPath=path.join(env.UPLOAD_DIR||path.join(root,'.data','uploads'),'practice-reviews',reviewSlug+'.html');
          try{return new Response(await fs.readFile(reviewPath),{headers:{'Content-Type':'text/html; charset=utf-8'}})}
          catch(e){if(e.code==='ENOENT')throw authError(404,'文件不存在');throw e}
        }
        if(url.pathname==='/api/admin/member-deletion'&&request.method==='GET'){
          return json(await deleteMember(client,user,{email:url.searchParams.get('email')},adminEmail,true));
        }
        if(url.pathname==='/api/admin/member'&&request.method==='DELETE'){
          return json(await deleteMember(client,user,await request.json(),adminEmail));
        }
        const practice=await practices.route(client,request,user);
        if(practice)return practice;
        const headers = new Headers(request.headers);
        for (const header of protectedHeaders) headers.delete(header);
        if (user) { headers.set(protectedHeaders[0],user.id); headers.set(protectedHeaders[1],user.email); }
        const rawBody=write?await request.text():undefined;
        const domain=body=>application.fetch(new Request(request.url,{method:request.method,headers,body}),{DB:database(client),BUCKET:files,ADMIN_EMAIL:adminEmail,STANDALONE:true});
        if(['POST','PATCH'].includes(request.method)&&/^\/api\/projects(?:\/[^/]+)?$/.test(url.pathname)){
          const body=JSON.parse(rawBody);
          const owners=[...new Set([body.bdId,body.saId,...(Array.isArray(body.saIds)?body.saIds:[])].filter(value=>typeof value==='string'&&value))].sort();
          for(const id of owners)await client.query('SELECT a.email FROM accounts a JOIN members m ON m.email=a.email WHERE m.email=? OR m.user_id=? FOR UPDATE',[id,id]);
        }
        if(request.method==='POST'&&url.pathname==='/api/projects'){
          const fields=JSON.parse(rawBody);
          if(Object.hasOwn(fields,'architectureDiagram'))return practices.createProjectWithDiagram(client,user,fields,project=>domain(JSON.stringify(project)));
        }
        if (write && url.pathname==='/api/admin/member') {
          const email=String(JSON.parse(rawBody).email||'').trim().toLowerCase();
          await client.query('SELECT email FROM accounts WHERE email=? FOR UPDATE',[email]);
        }
        const result=await domain(rawBody);
        if (result.ok && url.pathname === '/api/admin/member' && request.method==='POST') {
          // A role change or disable takes effect on every device immediately.
          const body = JSON.parse(rawBody);
          const email=String(body.email).trim().toLowerCase();
          const accountCreated=await ensureInitialAccount(client,email,user.email,initialPassword);
          await client.query('DELETE FROM sessions WHERE email=$1',[email]);
          return json({...await result.json(),accountCreated,...(accountCreated?{initialPassword}:{})});
        }
        if (result.ok && url.pathname === '/api/admin' && request.method==='GET') {
          const body=await result.json();
          const states=(await client.query('SELECT email,must_change_password FROM account_password_state')).rows;
          const state=new Map(states.map(x=>[x.email,!!x.must_change_password]));
          body.members=body.members.map(m=>({...m,must_change_password:state.get(m.email)||false,
            canDelete:m.email!==adminEmail&&m.email!==user.email&&!!body.roles.find(role=>role.id===m.role_id)?.permissions.every(permission=>user.permissions.includes(permission))}));
          return json(body);
        }
        return result;
      }, !write, loginAttempt);
      return response?.afterCommit?await response.afterCommit():response;
    } catch (error) {
      const id=randomUUID();
      if (!error.status) console.error(JSON.stringify({level:'error',requestId:id,code:error.code||'INTERNAL'}));
      const conflict=['ER_LOCK_DEADLOCK','ER_LOCK_WAIT_TIMEOUT','ER_DUP_ENTRY','ER_NO_REFERENCED_ROW_2','ER_ROW_IS_REFERENCED_2'].includes(error.code);
      return json({error:error.status?error.message:conflict?'记录已变更，请刷新后重试':'服务暂时不可用，请稍后重试',requestId:id},error.status|| (conflict?409:500));
    }
  }
  return {pool,handle,origin,editorOrigin,secure,practices,trustProxy:env.TRUST_PROXY==='true'};
}

export function httpServer(app) {
  const server = http.createServer(async (req,res) => {
    const start=Date.now();
    try {
      let total=0; const chunks=[];
      for await (const chunk of req) { total+=chunk.length; if(total>3100000) throw authError(413,'提交内容过大'); chunks.push(chunk); }
      const url=new URL(req.url,app.origin);
      if (url.origin!==app.origin) throw authError(400,'请求地址无效');
      const headers=new Headers();
      for (const [key,value] of Object.entries(req.headers)) if(value) headers.set(key,Array.isArray(value)?value.join(','):value);
      const request=new Request(url,{method:req.method,headers,body:['GET','HEAD'].includes(req.method)?undefined:Buffer.concat(chunks)});
      const forwarded=String(req.headers['x-forwarded-for']||'').split(',').at(-1).trim();
      const ip=app.trustProxy && isIP(forwarded) ? forwarded : req.socket.remoteAddress||'unknown';
      const response=await app.handle(request,ip);
      const outgoing=Object.fromEntries(response.headers);
      delete outgoing['content-security-policy'];
      Object.assign(outgoing,{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Permissions-Policy':'camera=(), microphone=(), geolocation=()'});
      outgoing['Content-Security-Policy']="default-src 'self'; script-src 'self'; script-src-attr 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'";
      if(['/', '/index.html', '/settings', '/settings/maas'].includes(url.pathname))outgoing['Content-Security-Policy']+="; frame-src 'self' "+app.editorOrigin;
      if(url.pathname.startsWith('/best-practices/reviews/'))outgoing['Content-Security-Policy']="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'";
      if(app.secure) outgoing['Strict-Transport-Security']='max-age=31536000';
      res.writeHead(response.status,outgoing);
      if(response.body && req.method!=='HEAD') await pipeline(Readable.fromWeb(response.body),res); else res.end();
      const authFailure=url.pathname.startsWith('/api/auth/')&&[400,401,429].includes(response.status);
      const adminChange=!['GET','HEAD'].includes(req.method)&&response.ok&&(url.pathname.startsWith('/api/admin/')||['/api/auth/password','/api/auth/reset-password','/api/auth/mfa/confirm'].includes(url.pathname));
      console.log(JSON.stringify({method:req.method,path:url.pathname,status:response.status,durationMs:Date.now()-start,...(authFailure||adminChange?{security_event:authFailure?'auth_failure':'admin_change',source_ip:ip}:{})}));
    } catch(error) { if(!res.headersSent) res.writeHead(error.status||500,{'Content-Type':'application/json'});res.end(JSON.stringify({error:error.status?error.message:'请求处理失败'})); }
  });
  server.on('listening',()=>app.practices.start());
  server.on('close',()=>app.practices.stop());
  server.requestTimeout=30000; server.headersTimeout=15000;
  return server;
}

if (process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const app=await createApplication(); const server=httpServer(app);
  server.listen(Number(process.env.PORT||3000),process.env.HOST||'127.0.0.1',()=>console.log(`Navigator listening on ${app.origin}`));
  const stop=()=>{server.close(async()=>{await app.practices.stop();await app.pool.end();process.exit(0)});setTimeout(()=>process.exit(1),10000).unref()};
  process.on('SIGINT',stop);process.on('SIGTERM',stop);
}
