import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {chromium} from '@playwright/test';
import {verifyProjectEditingBrowser} from './project-edit-browser.mjs';
import {verifyContentCollaborationBrowser} from './content-collaboration-browser.mjs';
import {verifyMemberSettingsBrowser} from './member-settings-browser.mjs';
import {verifyNavigationBrowser} from './navigation-browser.mjs';
import {fixture} from './architecture-fixture.mjs';

const root=new URL('../public/',import.meta.url),origin='https://ppl-fixture.invalid';
const user={id:'bd-id',email:'bd@example.invalid',roleId:'bd',roleName:'BD',permissions:['project.read.own','project.create','project.biz.own','project.assign.sa.own','practice.read','practice.analyze']};
const image=await fs.readFile(new URL('../server/ocr-check.png',import.meta.url));
const labels=[{id:'L1',text:'Event ingestion',box:[100,200,300,120],confidence:94},{id:'L2',text:'Object storage',box:[600,200,300,120],confidence:96},{id:'L3',text:'Batch processing',box:[100,650,300,120],confidence:92},{id:'L4',text:'SQL analytics',box:[600,650,300,120],confidence:97}];
const result={...fixture,summary:'Ingestion, storage, processing and analytics (L1-L4)',target:{...fixture.target,summary:'Data flow and service mapping (L1-L4)'}};
const sample={id:'10000000-0000-4000-8000-000000000001',title:'Browser fixture',status:'succeeded',language:'en',owner_email:user.email,updated_at:'2026-01-01',created_at:'2026-01-01',result,translations:{zh:{status:'succeeded',result:{...result,summary:'数据接入、存储、处理与分析（L1-L4）'}}},ocrEvidence:{labels,connections:[]}};
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
 await verifyProjectEditingBrowser(browser);
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
 // Synthetic architecture bitmap: geometry is shared with the OCR fixture above.
 const diagramImage=Buffer.from(await page.evaluate(labels=>{
  const canvas=document.createElement('canvas');canvas.width=1200;canvas.height=600;
  const ctx=canvas.getContext('2d');ctx.fillStyle='#f8fbff';ctx.fillRect(0,0,1200,600);
  ctx.fillStyle='#1e3854';ctx.font='bold 28px Arial';ctx.fillText('REFERENCE DATA ARCHITECTURE',45,50);
  ctx.strokeStyle='#576f8a';ctx.lineWidth=4;
  function arrow(x1,y1,x2,y2){ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();const a=Math.atan2(y2-y1,x2-x1);ctx.beginPath();ctx.moveTo(x2,y2);ctx.lineTo(x2-14*Math.cos(a-.45),y2-14*Math.sin(a-.45));ctx.moveTo(x2,y2);ctx.lineTo(x2-14*Math.cos(a+.45),y2-14*Math.sin(a+.45));ctx.stroke()}
  arrow(480,156,720,156);arrow(300,192,300,390);arrow(900,192,900,390);arrow(480,426,720,426);
  for(const [i,label]of labels.entries()){
   const [x,y,w,h]=label.box.map((n,index)=>n*(index%2===0?1.2:.6));
   ctx.fillStyle=i%2?'#193956':'#fff';ctx.fillRect(x,y,w,h);
   ctx.strokeStyle='#94abc1';ctx.lineWidth=2;ctx.strokeRect(x,y,w,h);
   ctx.fillStyle=i%2?'#fff':'#243e58';ctx.font='24px Arial';ctx.fillText(label.text,x+24,y+44);
  }
  return canvas.toDataURL('image/png').split(',')[1];
 },labels),'base64');
 async function capture(name,locator=page.locator('.diagram-evidence').first()){
  if(process.env.PPL_TEST_ARTIFACTS){await fs.mkdir(process.env.PPL_TEST_ARTIFACTS,{recursive:true});await locator.screenshot({path:path.join(process.env.PPL_TEST_ARTIFACTS,name+'.png')})}
 }
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
  if(path.endsWith('/image')||path.endsWith('/drawing/preview'))return route.fulfill({contentType:'image/png',body:diagramImage});
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
 async function annotations(scope=page){
  const evidence=scope.locator('.diagram-evidence').first();
  const markers=evidence.locator('.diagram-highlight.is-cited');
  assert.equal(await markers.count(),4);
  const colors=await markers.evaluateAll(items=>items.map(el=>{const s=getComputedStyle(el);return {color:s.outlineColor,opacity:s.opacity}}));
  assert.equal(new Set(colors.map(c=>c.color)).size,4);assert(colors.every(c=>c.opacity==='1'));
  assert.deepEqual(await markers.locator('.diagram-marker').allTextContents(),['#1','#2','#3','#4']);
  const toggle=evidence.locator('input[type=checkbox]');
  await toggle.uncheck();assert((await markers.evaluateAll(items=>items.map(el=>getComputedStyle(el).opacity))).every(value=>value==='0'));
  await toggle.check();
 }
 async function mark(scope=page){
  const details=scope.locator('.practice-citations').first();await details.locator('summary').click();
  await details.locator('a.diagram-link').first().click();
  const metrics=await scope.locator('.diagram-highlight:target').evaluate(el=>{
   const rect=el.getBoundingClientRect(),img=el.parentElement.querySelector('img').getBoundingClientRect();
   const style=getComputedStyle(el);return {outline:style.outlineStyle,weight:style.outlineWidth,opacity:style.opacity,color:style.outlineColor,tint:style.backgroundColor,badge:getComputedStyle(el.querySelector('.diagram-marker')).backgroundColor,x:(rect.left-img.left)/img.width,y:(rect.top-img.top)/img.height,w:rect.width/img.width,h:rect.height/img.height};
  });
  assert.equal(metrics.weight,'4px');assert.equal(metrics.opacity,'1');assert.notEqual(metrics.tint,'rgba(0, 0, 0, 0)');assert.equal(metrics.badge,metrics.color);
  const badge=await details.locator('.diagram-link-badge').first().evaluate(el=>{const s=getComputedStyle(el);return {color:s.backgroundColor,text:el.textContent}});assert.equal(badge.color,metrics.color);assert.equal(badge.text,'#1');
  assert.equal(metrics.outline,'solid');for(const [k,v]of Object.entries({x:.1,y:.2,w:.3,h:.12}))assert(Math.abs(metrics[k]-v)<.012,k);
 }
 await annotations();await capture('diagram-annotations-desktop');await mark();await capture('diagram-annotations-selected');
 await page.locator('header [data-language=en]').click();
 await page.getByRole('tab',{name:/Solution comparison/i}).click();
 await page.setViewportSize({width:390,height:844});await mark();await capture('diagram-annotations-phone');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:/Export analysis report/i}).click();
 offline=await fs.readFile(await (await download).path(),'utf8');
 assert(offline.includes('data:image/png;base64,'));assert(!offline.includes('/api/practices/'));assert(!offline.includes('<script'));
 await page.goto(origin+'/offline');await annotations();await mark();await capture('diagram-annotations-offline');
 assert.deepEqual(errors,[]);
 console.log('PASS: compact BD creation, optional diagram upload and scoped archive navigation, bilingual color-numbered OCR links, visible and toggleable annotations, aligned highlights, and script-free offline report at phone width');
}finally{await browser.close()}
