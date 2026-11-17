import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

export async function verifyContentCollaborationBrowser(browser){
 const origin='https://content-collaboration.invalid',root=new URL('../public/',import.meta.url);
 const context=await browser.newContext({viewport:{width:1360,height:900},locale:'zh-CN'}),page=await context.newPage();
 page.setDefaultTimeout(15000);
 const errors=[],calls=[],counts=new Map();page.on('pageerror',error=>errors.push(error.message));
 const user={id:'admin-id',email:'admin@example.invalid',displayName:'Admin',roleId:'admin',permissions:['project.read.all','project.create','project.biz.all','project.tech.all','project.assign','practice.read','practice.analyze']};
 const projects=[{id:'cn-project',name:'CPFL 数据库迁移',customer:'CPFL',next:'启动数据库 POC',notes:'数据库技术方案',repo:'巴西',type:'数据库',stage:0,status:'正常',bdId:'bd-id',saId:'sa-1',saIds:['sa-1','sa-2'],saDisplayName:'Alice / Bob',updatedAt:'2026-11-17',_version:1}];
 const translations={'巴西':'Brazil','CPFL 数据库迁移':'CPFL database migration','启动数据库 POC':'Start the database POC','数据库技术方案':'Database technical design','进展已更新':'Progress updated','中文 <img src=x onerror=alert(1)>':'English <img src=x onerror=alert(1)>'};
 const members=[{user_id:'sa-1',email:'alice@example.invalid',display_name:'Alice',role_id:'sa',enabled:1},{user_id:'sa-2',email:'bob@example.invalid',display_name:'Bob',role_id:'sa',enabled:1}];
 let reject=false;
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url()),p=url.pathname,reply=json=>route.fulfill({json});
  if(url.origin!==origin)return route.abort();
  if(p==='/api/me')return reply({user,source:{},permissions:{}});
  if(p==='/api/workspace')return reply({projects,resources:[],roles:[],members});
  if(p==='/api/content-translations'){
   const body=route.request().postDataJSON();calls.push(body);
   assert.equal(body.language,'en');assert(body.texts.every(text=>!text.includes('@example.invalid')));
   return reply({state:'ready',entries:body.texts.map(text=>{
    const n=(counts.get(text)||0)+1;counts.set(text,n);
    return {text,status:reject&&!body.retry?'failed':n===1&&!body.retry?'queued':'ready',translation:translations[text]||'Translated text'};
   })});
  }
  if(p==='/api/practices')return reply({items:[],total:0,page:1,service:{ready:true,inputMode:'ocr',model:'Test'},catalog:[]});
  if(p.startsWith('/api/'))throw Error('Unexpected fixture route '+p);
  const name=p==='/'?'index.html':p.slice(1);
  return route.fulfill({body:await fs.readFile(new URL(name,root)),contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.svg')?'image/svg+xml':'text/html'});
 });
 try{
  await page.goto(origin);await page.waitForFunction(()=>typeof user!=='undefined'&&user);
  await page.evaluate(()=>go('projects','全部'));
  await page.locator('#app').getByText('CPFL 数据库迁移',{exact:true}).waitFor();
  assert.equal(calls.length,0);
  await page.locator('header [data-language=en]').click();
  await page.locator('#app').getByText('CPFL database migration',{exact:true}).waitFor();
  await page.locator('#app').getByText('Start the database POC',{exact:true}).waitFor();
  assert.equal(await page.locator('[data-auto-translate="CPFL 数据库迁移"]').getAttribute('title'),'CPFL 数据库迁移');
  const before=counts.get('CPFL 数据库迁移');
  await page.locator('header [data-language=zh]').click();await page.locator('#app').getByText('CPFL 数据库迁移',{exact:true}).waitFor();
  await page.locator('header [data-language=en]').click();await page.locator('#app').getByText('CPFL database migration',{exact:true}).waitFor();
  assert.equal(counts.get('CPFL 数据库迁移'),before);
  await page.locator('#app').getByText('CPFL database migration',{exact:true}).click();
  assert.equal(await page.locator('[name=name]').inputValue(),'CPFL 数据库迁移');
  assert.equal(await page.locator('[name=notes]').inputValue(),'数据库技术方案');
  assert(await page.locator('[name=saIds][value="sa-1"]').isChecked());assert(await page.locator('[name=saIds][value="sa-2"]').isChecked());
  await page.locator('.field-translation').getByText('Database technical design',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  await page.locator('.sa-picker').scrollIntoViewIfNeeded();
  assert(await page.locator('#form').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
  if(process.env.PPL_TEST_ARTIFACTS){await fs.mkdir(process.env.PPL_TEST_ARTIFACTS,{recursive:true});await page.screenshot({path:path.join(process.env.PPL_TEST_ARTIFACTS,'multi-sa-en.png')})}
  await page.getByRole('button',{name:'Cancel',exact:true}).click();await page.setViewportSize({width:1360,height:900});
  projects[0].next='进展已更新';await page.evaluate(()=>reload());await page.locator('#app').getByText('Progress updated',{exact:true}).waitFor();
  projects[0].next='中文 <img src=x onerror=alert(1)>';reject=true;await page.evaluate(()=>reload());
  await page.getByRole('button',{name:'Retry translation',exact:true}).waitFor();
  reject=false;await page.getByRole('button',{name:'Retry translation',exact:true}).click();
  await page.locator('#app').getByText('English <img src=x onerror=alert(1)>',{exact:true}).waitFor();
  assert.equal(await page.locator('#app img[src=x]').count(),0);
  projects[0].next='启动数据库 POC';await page.evaluate(()=>reload());await page.locator('#app').getByText('Start the database POC',{exact:true}).waitFor();
  if(process.env.PPL_TEST_ARTIFACTS)await page.screenshot({path:path.join(process.env.PPL_TEST_ARTIFACTS,'translated-project-en.png')});
  await page.evaluate(()=>{user={...user,id:'sa-2',roleId:'sa',permissions:['project.read.own','project.tech.own','practice.read','practice.analyze']};project('cn-project')});
  assert.equal(await page.locator('[name=notes]').isDisabled(),false);
  assert.equal(await page.getByRole('button',{name:'View project diagrams',exact:true}).count(),1);
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.evaluate(()=>go('practices'));await page.getByRole('button',{name:'Upload architecture',exact:true}).click();
  assert.equal(await page.locator('[name=targetRegion]').count(),0);
  assert(!(await page.locator('#form').innerText()).includes('Santiago'));
  assert.deepEqual(errors,[]);
  console.log('PASS: automatic English prose, source preservation, locale switching, cached translations, changed content, failure retry, safe rendering, multiple SAs and region-free upload');
 }finally{await context.close()}
}
