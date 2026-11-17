import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '@playwright/test';
import {verifyContentCollaborationBrowser} from './content-collaboration-browser.mjs';
import {verifyMemberSettingsBrowser} from './member-settings-browser.mjs';
import {verifyNavigationBrowser} from './navigation-browser.mjs';
import {fixture} from './architecture-fixture.mjs';

const root=new URL('../public/',import.meta.url),origin='https://ppl-fixture.invalid';
const user={id:'bd-id',email:'bd@example.invalid',roleId:'bd',roleName:'BD',permissions:['project.read.own','project.create','project.biz.own','project.assign.sa.own','practice.read','practice.analyze']};
const image=await fs.readFile(new URL('../server/ocr-check.png',import.meta.url));
const result={...fixture,summary:'Object storage (L1)',target:{...fixture.target,summary:'Storage layer (L1)'}};
const sample={id:'10000000-0000-4000-8000-000000000001',title:'Browser fixture',status:'succeeded',language:'en',owner_email:user.email,updated_at:'2026-01-01',created_at:'2026-01-01',result,translations:{zh:{status:'succeeded',result:{...result,summary:'对象存储（L1）'}}},ocrEvidence:{labels:[{id:'L1',text:'Storage',box:[100,200,300,120],confidence:94}],connections:[]}};
let offline,submitted,filtered=false;const projects=[];
function luminance(color) {
 const [r,g,b]=color.match(/\d+(?:\.\d+)?/g).slice(0,3).map(Number).map(n=>n/255).map(n=>n<=0.04045?n/12.92:((n+0.055)/1.055)**2.4);
 return 0.2126*r+0.7152*g+0.0722*b;
}
async function verifyWorkspaceAppearance(page) {
 const add=page.getByRole('button',{name:'新建项目',exact:true});
 await add.waitFor();
 assert.equal(await page.title(),'数据专项作战平台');
 await page.waitForFunction(()=>[...document.querySelectorAll('#nav .menu-icon use,.track-art use,.page-actions .primary use')].every(el=>el.getBBox().width>0));
 const glyphs=await page.locator('#nav .menu-icon use').evaluateAll(items=>items.map(el=>el.getAttribute('href')));
 assert(glyphs.length>=4);assert.equal(new Set(glyphs).size,glyphs.length);
 assert.equal(await page.locator('.track-art').count(),2);
 const colors=await add.evaluate(el=>{const s=getComputedStyle(el);return [s.color,s.backgroundColor]});
 const [light,dark]=colors.map(luminance).sort((a,b)=>b-a);
 assert((light+.05)/(dark+.05)>=4.5,'Primary button contrast');
 await page.locator('header [data-language=en]').click();
 assert.equal(await page.title(),'Data Solutions Hub');
 assert.equal((await page.locator('aside .brand').innerText()).trim(),'Data Solutions Hub');
 await page.getByRole('button',{name:'New project',exact:true}).waitFor();
 await page.locator('.track[data-business=database]').click();
 assert.equal(await page.locator('body').getAttribute('data-business'),'database');
 assert.equal(await page.getByRole('button',{name:'New project',exact:true}).evaluate(el=>getComputedStyle(el).backgroundColor),colors[1]);
 await page.locator('#nav [data-menu-id=home]').click();
 await page.locator('header [data-language=zh]').click();
}
const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
try{
 await verifyNavigationBrowser(browser);
 await verifyMemberSettingsBrowser(browser);
 await verifyContentCollaborationBrowser(browser);
 const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url()),path=url.pathname;
  if(url.origin!==origin)return route.abort();
  if(path==='/offline')return route.fulfill({contentType:'text/html',body:offline});
  if(path==='/api/me')return route.fulfill({json:{user,permissions:{},source:{}}});
  if(path==='/api/workspace')return route.fulfill({json:{projects,resources:[],roles:[],members:[{email:'sa@example.invalid',user_id:'sa-id',role_id:'sa',enabled:1},{email:'second@example.invalid',user_id:'second-sa',role_id:'sa',enabled:1}]}});
  if(path==='/api/projects'){
    submitted=route.request().postDataJSON();
    const {architectureDiagram,...fields}=submitted,id='project-'+projects.length;
    projects.push({...fields,id,bdId:user.id,_version:1});
    return route.fulfill({status:201,json:{id,architectureSubmitted:!!architectureDiagram}});
  }
  if(path==='/api/practices'){if(url.searchParams.get('projectId')==='project-1'&&url.searchParams.get('archived')==='true')filtered=true;return route.fulfill({json:{items:[sample],total:1,page:1,service:{ready:true},catalog:[]}})}
  if(path==='/api/practices/'+sample.id)return route.fulfill({json:sample});
  if(path.endsWith('/image')||path.endsWith('/drawing/preview'))return route.fulfill({contentType:'image/png',body:image});
  if(path==='/api/content-translations')return route.fulfill({json:{state:'unavailable',entries:[]}});
  if(path.startsWith('/api/'))throw Error('Unexpected fixture route '+path);
  const name=path==='/'?'index.html':path.slice(1);
  return route.fulfill({body:await fs.readFile(new URL(name,root)),contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.svg')?'image/svg+xml':'text/html'});
 });
 await page.goto(origin);await verifyWorkspaceAppearance(page);await page.getByRole('button',{name:/新建项目/}).click();
 await page.locator('[name=name]').fill('First lead');
 await page.locator('[name=saIds][value="sa-id"]').check();
 await page.locator('[name=saIds][value="second-sa"]').check();
 assert.equal(await page.locator('[name=vendor]').isVisible(),false);
 await page.getByRole('button',{name:'保存',exact:true}).click();await page.waitForSelector('#modal:not([open])',{state:'attached'});
 assert.deepEqual(submitted.saIds,['sa-id','second-sa']);assert.equal(submitted.name,'First lead');assert(!('bdId' in submitted));
 assert(!submitted.architectureDiagram);
 await page.getByRole('button',{name:/新建项目/}).click();await page.locator('[name=name]').fill('Diagram project');
 const file=page.getByLabel('技术架构图（可选）');assert(await file.isVisible());
 await file.setInputFiles({name:'project.png',mimeType:'image/png',buffer:image});
 await page.locator('#modal [data-language=en]').click();
 assert.equal(await page.getByLabel('Technical architecture diagram (optional)').inputValue().then(value=>value.endsWith('project.png')),true);
 await page.getByRole('button',{name:'Save',exact:true}).click();await page.waitForSelector('#modal:not([open])',{state:'attached'});
 assert.equal(submitted.architectureDiagram.language,'en');assert.equal(submitted.architectureDiagram.base64,image.toString('base64'));
 assert.match(submitted.architectureDiagram.requestKey,/^[0-9a-f-]{36}$/);
 await page.getByText('Diagram project',{exact:true}).first().click();
 await page.getByRole('button',{name:'View project diagrams'}).click();await page.locator('#practiceList .practice-item').waitFor();
 assert(filtered);assert(await page.locator('.practice-archive input').isChecked());
 await page.getByRole('button',{name:/Browser fixture/}).click();
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
 console.log('PASS: compact BD creation, optional diagram upload and scoped archive navigation, bilingual OCR links, geometric alignment and script-free offline report at phone width');
}finally{await browser.close()}
