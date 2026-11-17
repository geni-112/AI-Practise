import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {DatabaseSync} from 'node:sqlite';
import application,{initialize} from '../dist/server/index.mjs';

export async function verifyProjectEditingBrowser(browser){
 const origin='https://project-edit.invalid',adminEmail='admin-edit@example.invalid';
 const sqlite=new DatabaseSync(':memory:');
 sqlite.exec(await fs.readFile(new URL('../drizzle/0000_workspace.sql',import.meta.url),'utf8'));
 sqlite.exec('ALTER TABLE members ADD COLUMN version INTEGER NOT NULL DEFAULT 1');
 class Statement{
  constructor(sql,params=[]){this.sql=sql;this.params=params}
  bind(...params){return new Statement(this.sql,params)}
  async first(){return sqlite.prepare(this.sql).get(...this.params)||null}
  async all(){return {results:sqlite.prepare(this.sql).all(...this.params)}}
  async run(){return {meta:{changes:sqlite.prepare(this.sql).run(...this.params).changes}}}
 }
 const DB={prepare:sql=>new Statement(sql),async batch(statements){const result=[];for(const statement of statements)result.push(await statement.run());return result}};
 const env={DB,ADMIN_EMAIL:adminEmail};
 await initialize(DB,env);
 let current={email:adminEmail,id:'admin-edit'},patches=0;
 const sa={email:'sa-edit@example.invalid',id:'sa-edit'};
 const another={email:'second-edit@example.invalid',id:'second-edit'};
 async function dispatch(path,method='GET',body){
  const headers={'oai-authenticated-user-id':current.id,'oai-authenticated-user-email':current.email,Origin:origin,'Content-Type':'application/json'};
  return application.fetch(new Request(origin+'/api/'+path,{method,headers,body:method==='GET'?undefined:JSON.stringify(body)}),env);
 }
 async function read(path,method='GET',body){const res=await dispatch(path,method,body);assert(res.ok,path+': '+await res.clone().text());return res.json()}
 await read('me');
 for(const identity of [sa,another]){
  await read('admin/member','POST',{email:identity.email,roleId:'sa',displayName:identity===sa?'Architect A':'Architect B'});
  const saved=current;current=identity;await read('me');current=saved;
 }
 await read('admin/dictionaries','POST',{field:'repo',_version:0,allowCustom:true,items:[{value:'',zh:'巴西',en:'Brazil',enabled:true}]});
 const repo=(await read('dictionaries')).find(d=>d.field==='repo').items[0].value;
 let project=await read('projects','POST',{name:'Edit round-trip fixture',bdName:'',saIds:[sa.id,another.id],repo,stage:4,next:'Original next step',notes:'Original technical notes',planYear:2026,eiPlan:1,servicePlan:null,actuals:[],milestones:{'POC 资源':'进行中'}});
 assert.equal(project.bdName,'');assert.equal(project.bdNameManual,true);
 const ownerIdentity=project.bdId;
 const context=await browser.newContext({viewport:{width:1280,height:900},locale:'zh-CN'}),page=await context.newPage(),errors=[];
 page.setDefaultTimeout(12000);page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.origin!==origin)return route.abort();
  if(url.pathname==='/api/content-translations')return route.fulfill({json:{state:'unavailable',entries:[]}});
  if(url.pathname.startsWith('/api/')){
   const res=await dispatch(url.pathname.slice(5)+url.search,req.method(),req.method()==='GET'?undefined:req.postDataJSON());
   if(req.method()==='PATCH')patches++;
   return route.fulfill({status:res.status,headers:Object.fromEntries(res.headers),body:Buffer.from(await res.arrayBuffer())});
  }
  const res=await application.fetch(new Request(url),env);
  return route.fulfill({status:res.status,headers:Object.fromEntries(res.headers),body:Buffer.from(await res.arrayBuffer())});
 });
 const openProject=async()=>{
  await page.goto(origin);await page.waitForFunction(()=>typeof user!=='undefined'&&user);
  await page.evaluate(()=>go('projects','全部'));
  await page.getByText('Edit round-trip fixture',{exact:true}).click();
 };
 const save=async()=>{await page.locator('#form button[type=submit],#form .formactions button.primary').click();await page.locator('#modal').waitFor({state:'hidden'})};
 try{
  await openProject();
  assert.equal(await page.locator('[name=bdName]').inputValue(),'');
  assert.equal(await page.locator('[name=bdName]').getAttribute('placeholder'),'未分配');
  assert.equal(await page.locator('[name=bdId]').count(),0);assert.equal(await page.locator('[name=saName]').count(),0);
  await page.locator('[name=bdName]').fill('External BD contact');
  await page.locator('[name=next]').fill('Administrator saved the next step');
  await save();
  project=(await read('workspace')).projects.find(p=>p.id===project.id);
  assert.equal(project.bdName,'External BD contact');assert.equal(project.bdDisplayName,'External BD contact');
  assert.equal(project.bdId,ownerIdentity);assert.equal(project.next,'Administrator saved the next step');
  await openProject();assert.equal(await page.locator('[name=next]').inputValue(),project.next);
  await page.getByRole('button',{name:'取消',exact:true}).click();
  current=another;
  await openProject();
  assert(await page.locator('[name=next]').isDisabled());assert(!await page.locator('[name=notes]').isDisabled());
  await page.locator('[name=notes]').fill('Second SA saved technical changes');
  await page.locator('[name=update]').fill('SA recorded the POC verification result');
  await save();
  project=(await read('workspace')).projects.find(p=>p.id===project.id);
  assert.equal(project.notes,'Second SA saved technical changes');
  assert.equal(project.logs.at(-1).text,'SA recorded the POC verification result');
  assert.equal(project.next,'Administrator saved the next step');assert.equal(project.bdName,'External BD contact');
  await openProject();assert.equal(await page.locator('[name=notes]').inputValue(),project.notes);
  await page.getByRole('button',{name:'取消',exact:true}).click();
  current={email:adminEmail,id:'admin-edit'};
  await openProject();await page.locator('#modal [data-language=en]').click();
  await page.locator('[name=bdName]').fill('');await save();
  project=(await read('workspace')).projects.find(p=>p.id===project.id);
  assert.equal(project.bdName,'');assert.equal(project.bdDisplayName,'');assert.equal(project.bdId,ownerIdentity);
  await page.locator('#app .person').getByText('Unassigned',{exact:true}).waitFor();
  assert.equal(patches,3);assert.deepEqual(errors,[]);
  console.log('PASS: real project routes behind browser forms; administrator and second-SA save/reload, progress history, manual BD and blank/unassigned, account permissions unchanged');
 }finally{await context.close();sqlite.close()}
}
