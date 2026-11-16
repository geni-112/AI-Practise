import {chromium} from '@playwright/test';
import {createApplication,httpServer} from '../server/index.mjs';
import {transaction} from '../server/database.mjs';
import {hashPassword} from '../server/auth.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {INITIAL_PASSWORD} from './test-credentials.mjs';
const env={INITIAL_ACCOUNT_PASSWORD:INITIAL_PASSWORD,DB_HOST:'127.0.0.1',DB_PORT:'13306',DB_USER:'navigator_test',DB_PASSWORD:'test-password-only',DB_NAME:'navigator_i18n_test',ADMIN_EMAIL:'i18n@test.local',APP_ORIGIN:'http://127.0.0.1:3101'};
const app=await createApplication({env});
assert.equal(env.DB_HOST,'127.0.0.1');assert.equal(env.DB_NAME,'navigator_i18n_test');
await transaction(app.pool,async c=>{
 await c.query("DELETE FROM records WHERE kind IN ('project','resource','report','dictionary')");
 await c.query('DELETE FROM login_limits');
 await c.query('UPDATE members SET user_id=COALESCE(user_id,$1) WHERE email=$2',[randomUUID(),env.ADMIN_EMAIL]);
 await c.query('INSERT INTO accounts(email,password_hash) VALUES($1,$2) ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash)',[env.ADMIN_EMAIL,await hashPassword('Bilingual-test-password')]);await c.query('UPDATE account_password_state SET must_change_password=0 WHERE email=$1',[env.ADMIN_EMAIL]);
 await c.query('INSERT INTO records(id,kind,payload) VALUES($1,$2,$3)',['branch-fixture','resource',JSON.stringify({id:'branch-fixture',title:'Branch source fixture',type:'大数据',body:'Public source reference',url:'https://github.com/geni-112/AI-Practise',sourceBranches:[{branch:'main',path:'chatbi',commit:'1234567890123456789012345678901234567890',url:'https://github.com/geni-112/AI-Practise/tree/main/chatbi'}]})]);
});
const server=httpServer(app);await new Promise(r=>server.listen(3101,'127.0.0.1',r));
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},locale:'zh-CN'}),errors=[],missing=[];
page.on('pageerror',e=>errors.push(e.message));
async function untranslated(label){await page.waitForTimeout(100);const texts=await page.evaluate(()=>{const out=[],w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){const e=n.parentElement;if(!e||e.closest('[data-user-content],[data-language],script,style,textarea')||!e.getClientRects().length)continue;if(/[\u3400-\u9fff]/.test(n.nodeValue))out.push(n.nodeValue.trim())}document.querySelectorAll('[placeholder],[aria-label]').forEach(e=>{if(e.closest('[data-user-content],[data-language]')||!e.getClientRects().length)return;for(const a of ['placeholder','aria-label'])if(/[\u3400-\u9fff]/.test(e.getAttribute(a)||''))out.push(a+': '+e.getAttribute(a))});return [...new Set(out)].filter(Boolean)});if(texts.length)missing.push({label,texts})}
try{
 await page.goto(env.APP_ORIGIN+'/login');
 await page.getByRole('button',{name:'English',exact:true}).click();
 await page.getByRole('heading',{name:'Sign in to your workspace'}).waitFor();
 await untranslated('login');
 await page.getByLabel('Email',{exact:true}).fill(env.ADMIN_EMAIL);await page.getByLabel('Password',{exact:true}).fill('Bilingual-test-password');
 await page.getByRole('button',{name:'Sign in →'}).click();await page.getByRole('button',{name:'＋ New project',exact:true}).waitFor();
 assert.equal(await page.locator('#nav button').filter({hasText:'Lead discovery'}).count(),0);
 assert.match(await page.locator('.brand').innerText(),/Data PPL Management/);
 assert(await page.locator('.subtitle').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=15));
 await untranslated('home');await page.screenshot({path:'artifacts/bilingual-home-en.png',fullPage:true});
 await page.getByRole('button',{name:'＋ New project',exact:true}).click();
 await page.locator('input[name=name]').fill('全部');await page.locator('input[name=customer]').fill('正常');await page.locator('input[name=repo]').fill('数据库');
 await page.locator('input[name=saName]').fill('架构师甲');await page.locator('input[name=vendor]').fill('Oracle');await page.locator('input[name=scenario]').fill('金融风控');await page.locator('textarea[name=notes]').fill('验证技术方案');await page.locator('input[name=eiPlan]').fill('1.25');await page.locator('select[name=stage]').selectOption('3');await page.locator('select[name=milestone3]').selectOption('已完成');
 await page.locator('select[name=type]').selectOption('数据库');await page.locator('select[name=cloud]').selectOption('公有云');
 await page.locator('#modal [data-language=zh]').click();assert.equal(await page.locator('input[name=name]').inputValue(),'全部');
 await page.locator('#modal [data-language=en]').click();assert.equal(await page.locator('select[name=type]').inputValue(),'数据库');
 await untranslated('project form');await page.locator('#modal').evaluate(e=>e.scrollTop=0);await page.screenshot({path:'artifacts/project-form-en.png',fullPage:true});
 await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
 const workspace=await page.evaluate(()=>fetch('/api/workspace').then(r=>r.json()));assert(workspace.projects.some(p=>p.name==='全部'&&p.customer==='正常'&&p.type==='数据库'&&p.repo==='数据库'&&p.cloud==='公有云'&&p.saName==='架构师甲'&&p.vendor==='Oracle'&&p.notes==='验证技术方案'&&p.eiPlan===1.25&&p.milestones['POC 资源']==='已完成'));
 await page.locator('#nav button').filter({hasText:'POC center'}).click();assert.equal(await page.locator('#results tbody tr').filter({hasText:'全部'}).count(),1);
 await page.locator('#results tbody tr').filter({hasText:'全部'}).click();await page.locator('select[name=stage]').selectOption('0');await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});assert.equal(await page.locator('#results tbody tr').filter({hasText:'全部'}).count(),0);

 await page.reload();assert.equal(await page.locator('html').getAttribute('lang'),'en');
 await page.getByRole('button',{name:'Projects',exact:false}).first().click();await untranslated('projects');
 await page.locator('tbody tr').filter({hasText:'全部'}).first().click();await untranslated('edit project');
 await page.getByRole('button',{name:'＋ Add revenue entry'}).click();
 assert.equal(await page.locator('[data-kind] option').nth(1).textContent(),'Professional services');assert.equal(await page.locator('[data-kind] option').nth(1).getAttribute('value'),'专业服务');
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.locator('tbody tr').filter({hasText:'全部'}).first().click();
 await page.locator('input[name=next]').fill('用户输入保持中文');await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
 await page.locator('tbody tr').filter({hasText:'全部'}).first().click();await untranslated('system progress log');await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.evaluate(async()=>{
  const r=await fetch('/api/files',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'bilingual.txt',type:'数据库',base64:btoa('Synthetic bilingual test')})});if(!r.ok)throw Error('Upload failed');
  const w=await fetch('/api/workspace').then(r=>r.json()),p=w.projects.find(p=>p.name==='全部');
  const send=(action,version)=>fetch(`/api/projects/${p.id}/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({_version:version})});
  if(!(await send('archive',p._version)).ok)throw Error('Archive failed');if(!(await send('restore',p._version+1)).ok)throw Error('Restore failed');
 });
 await page.reload();await page.getByRole('button',{name:'＋ New project',exact:true}).waitFor();
 for(const name of ['POC center','Resources','Reports','Members & roles','Activity log']){
  await page.locator('#nav button').filter({hasText:name}).click();
  if(name==='Reports')await page.locator('.reporthead').waitFor();
  if(name==='Members & roles')await page.locator('#roles .listrow').first().waitFor();
  await untranslated(name);
  if(name==='Resources'){await page.getByRole('heading',{name:'Branch source fixture'}).click();await page.locator('.resource-branches summary').click();assert.equal(await page.locator('.resource-branches a').getAttribute('href'),'https://github.com/geni-112/AI-Practise/tree/main/chatbi');await untranslated('source branches');await page.getByRole('button',{name:'Cancel',exact:true}).click();await page.getByRole('button',{name:'＋ New resource'}).click();await untranslated('resource form');await page.getByRole('button',{name:'Cancel',exact:true}).click()}
  if(name==='Members & roles'){
   await page.locator('.dictionary-card').filter({hasText:'Current vendor'}).getByRole('button',{name:'Manage options'}).click();await page.getByRole('button',{name:'＋ Add option'}).click();await page.locator('[data-property=zh]').fill('甲厂');await page.locator('[data-property=en]').fill('Vendor A');await untranslated('dictionary form');await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});await page.locator('.dictionary-card').filter({hasText:'Current vendor'}).getByRole('button',{name:'Manage options'}).click();assert.equal(await page.locator('[data-property=en]').inputValue(),'Vendor A');await page.getByRole('button',{name:'Cancel',exact:true}).click();await page.screenshot({path:'artifacts/admin-dictionaries-en.png',fullPage:true});
   await page.getByRole('button',{name:'＋ Add member'}).click();await untranslated('member form');await page.getByRole('button',{name:'Cancel',exact:true}).click();
   await page.getByRole('button',{name:'＋ New role'}).click();await untranslated('role form');await page.getByRole('button',{name:'Cancel',exact:true}).click();
  }
 }
 await page.locator('#nav button').filter({hasText:'Projects'}).click();await page.getByRole('button',{name:'＋ New project',exact:true}).click();assert.equal(await page.locator('#dictionary-list-vendor option').first().getAttribute('value'),'Vendor A');await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByRole('button',{name:'Open user guide ↗'}).click();await untranslated('guide');
 await page.locator('#nav button').filter({hasText:'Reports'}).click();await page.locator('.reporthead').waitFor();
 const original=await page.locator('#summaryEdit').inputValue();assert.match(original,/opportunities/);
 await page.locator('#summaryEdit').fill('不要翻译我的业务总结');await page.locator('header [data-language=zh]').click();assert.equal(await page.locator('#summaryEdit').inputValue(),'不要翻译我的业务总结');
 await page.locator('header [data-language=en]').click();assert.equal(await page.locator('#summaryEdit').inputValue(),'不要翻译我的业务总结');
 await page.frameLocator('#templateFrame').locator('.cell').filter({hasText:'不要翻译我的业务总结'}).waitFor();
 await page.locator('#templateZoom').selectOption('fit');await page.locator('#templateViewport').scrollIntoViewIfNeeded();await page.screenshot({path:'artifacts/report-template-page-en.png',fullPage:true});
 const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'↓ Export Excel'}).click();const download=await downloadPromise;await download.saveAs('artifacts/template-work/browser-report.xlsx');assert((await fs.stat('artifacts/template-work/browser-report.xlsx')).size>40000);
 const sheets=await page.evaluate(()=>reportSheets(report));assert.equal(sheets[0].name,'Summary');assert(sheets[2].rows.some(row=>row[2]==='全部'&&row[3]==='Database'));
 await page.getByRole('button',{name:'Change password',exact:true}).click();await untranslated('password form');await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.setViewportSize({width:390,height:844});await page.locator('#nav button').filter({hasText:'Overview'}).click();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'English mobile layout does not overflow');
 await page.screenshot({path:'artifacts/bilingual-mobile-en.png',fullPage:true});
 await page.setViewportSize({width:1440,height:1000});await page.locator('header [data-language=zh]').click();assert.match(await page.locator('.brand').innerText(),/数据专项管理平台/);await page.screenshot({path:'artifacts/platform-home-zh.png',fullPage:true});await page.locator('header [data-language=en]').click();
 await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByRole('heading',{name:'Sign in to your workspace'}).waitFor();
 assert.deepEqual(errors,[]);console.log(JSON.stringify({missingTranslations:missing},null,2));
 assert.deepEqual(missing,[],'Every visible interface string is translated');
 console.log('PASS: bilingual navigation, forms, reports, exports, persisted preference, mobile layout, unchanged user content and canonical values, unsaved input preserved');
}finally{await browser.close();await new Promise(r=>server.close(r));await app.pool.end()}
