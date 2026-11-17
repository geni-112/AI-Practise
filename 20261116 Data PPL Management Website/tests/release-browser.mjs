import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '@playwright/test';
import {fixture} from './architecture-fixture.mjs';

const root=new URL('../public/',import.meta.url),origin='https://ppl-fixture.invalid';
const user={id:'bd-id',email:'bd@example.invalid',roleId:'bd',roleName:'BD',permissions:['project.read.own','project.create','project.biz.own','project.assign.sa.own','practice.read','practice.analyze']};
const image=await fs.readFile(new URL('../server/ocr-check.png',import.meta.url));
const result={...fixture,summary:'Object storage (L1)',target:{...fixture.target,summary:'Storage layer (L1)'}};
const sample={id:'10000000-0000-4000-8000-000000000001',title:'Browser fixture',status:'succeeded',language:'en',owner_email:user.email,updated_at:'2026-01-01',created_at:'2026-01-01',result,translations:{zh:{status:'succeeded',result:{...result,summary:'对象存储（L1）'}}},ocrEvidence:{labels:[{id:'L1',text:'Storage',box:[100,200,300,120],confidence:94}],connections:[]}};
let offline,submitted;
const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url()),path=url.pathname;
  if(url.origin!==origin)return route.abort();
  if(path==='/offline')return route.fulfill({contentType:'text/html',body:offline});
  if(path==='/api/me')return route.fulfill({json:{user,permissions:{},source:{}}});
  if(path==='/api/workspace')return route.fulfill({json:{projects:[],resources:[],roles:[],members:[{email:'sa@example.invalid',user_id:'sa-id',role_id:'sa',enabled:1}]}});
  if(path==='/api/projects'){submitted=route.request().postDataJSON();return route.fulfill({status:201,json:{id:'test'}})}
  if(path==='/api/practices')return route.fulfill({json:{items:[sample],total:1,page:1,service:{ready:true},catalog:[]}});
  if(path==='/api/practices/'+sample.id)return route.fulfill({json:sample});
  if(path.endsWith('/image')||path.endsWith('/drawing/preview'))return route.fulfill({contentType:'image/png',body:image});
  if(path.startsWith('/api/'))throw Error('Unexpected fixture route '+path);
  const name=path==='/'?'index.html':path.slice(1);
  return route.fulfill({body:await fs.readFile(new URL(name,root)),contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto(origin);await page.getByRole('button',{name:/新建项目/}).click();
 await page.locator('[name=name]').fill('First lead');
 await page.locator('[name=saId]').selectOption('sa-id');
 assert.equal(await page.locator('[name=vendor]').isVisible(),false);
 await page.getByRole('button',{name:'保存',exact:true}).click();await page.waitForSelector('#modal:not([open])',{state:'attached'});
 assert.equal(submitted.saId,'sa-id');assert.equal(submitted.name,'First lead');assert(!('bdId' in submitted));
 await page.getByRole('button',{name:/最佳实践/}).click();await page.getByRole('button',{name:/Browser fixture/}).click();
 async function mark(scope=page){
  const details=scope.locator('.practice-citations').first();await details.locator('summary').click();
  await details.locator('a.diagram-link').first().click();
  const metrics=await scope.locator('.diagram-highlight:target').evaluate(el=>{
   const rect=el.getBoundingClientRect(),img=el.parentElement.querySelector('img').getBoundingClientRect();
   return {outline:getComputedStyle(el).outlineStyle,x:(rect.left-img.left)/img.width,y:(rect.top-img.top)/img.height,w:rect.width/img.width,h:rect.height/img.height};
  });
  assert.equal(metrics.outline,'solid');for(const [k,v]of Object.entries({x:.1,y:.2,w:.3,h:.12}))assert(Math.abs(metrics[k]-v)<.012,k);
 }
 await mark();
 await page.locator('header [data-language=en]').click();
 await page.getByRole('tab',{name:/Solution comparison/i}).click();
 await page.setViewportSize({width:390,height:844});await mark();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:/Export analysis report/i}).click();
 offline=await fs.readFile(await (await download).path(),'utf8');
 assert(offline.includes('data:image/png;base64,'));assert(!offline.includes('/api/practices/'));assert(!offline.includes('<script'));
 await page.goto(origin+'/offline');await mark();
 assert.deepEqual(errors,[]);
 console.log('PASS: compact BD creation and SA selection, bilingual OCR links, geometric alignment and script-free offline report at phone width');
}finally{await browser.close()}
