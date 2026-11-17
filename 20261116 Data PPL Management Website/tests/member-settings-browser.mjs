import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

export async function verifyMemberSettingsBrowser(browser) {
  const origin='https://member-settings.invalid',root=new URL('../public/',import.meta.url);
  const admin={id:'admin-id',email:'admin@example.invalid',displayName:'管理员甲',profileVersion:1,roleId:'admin',roleName:'管理员',
    permissions:['project.read.all','project.create','project.assign','member.manage','role.manage','resource.read','practice.read']};
  const member={id:'sa-id',email:'member@example.invalid',displayName:'管理员预填',profileVersion:1,roleId:'sa',roleName:'SA',
    mustChangePassword:true,permissions:['project.read.own','project.tech.own','practice.read']};
  const members=[{email:member.email,user_id:member.id,display_name:member.displayName,role_id:'sa',enabled:1,version:1}];
  const roles=[{id:'sa',name:'SA',permissions:member.permissions,builtin:true,_version:1}];
  let current=admin,memberBody,passwordBody;const deletedRoles=[];
  const errors=[],context=await browser.newContext({viewport:{width:1280,height:900},locale:'zh-CN'});
  const page=await context.newPage();page.setDefaultTimeout(12000);
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),p=url.pathname,method=route.request().method();
    if(url.origin!==origin)return route.abort();
    const body=()=>route.request().postDataJSON(),reply=json=>route.fulfill({json});
    if(p==='/api/auth/status')return reply({authenticated:!!current,...current});
    if(p==='/api/me')return reply({user:current,permissions:{},source:{}});
    if(p==='/api/workspace')return reply({projects:[],members,resources:[],roles:[]});
    if(p==='/api/admin')return reply({members,roles,permissions:{}});
    if(p==='/api/admin/role'){
      const b=body();
      if(method==='POST'){
        const role={id:'custom-'+roles.length,name:b.name,permissions:b.permissions,builtin:false,_version:1,memberCount:0};
        roles.push(role);return reply(role);
      }
      assert.equal(method,'DELETE');
      const index=roles.findIndex(r=>r.id===b.id);assert(index>=0);
      assert.equal(b._version,roles[index]._version);assert(!roles[index].builtin);
      deletedRoles.push(b.id);roles.splice(index,1);return reply({ok:true});
    }
    if(p==='/api/admin/member'){
      memberBody=body();members.push({email:memberBody.email,user_id:'new-id',display_name:memberBody.displayName,role_id:'sa',version:1,enabled:1});
      return reply({ok:true,accountCreated:true,initialPassword:'Synthetic-initial-password'});
    }
    if(p==='/api/auth/profile'){
      if(method==='POST'){const b=body();assert.equal(b._version,current.profileVersion);current.displayName=b.displayName;current.profileVersion++}
      return reply({displayName:current.displayName,_version:current.profileVersion});
    }
    if(p==='/api/auth/login'){current=member;return reply({ok:true,...member})}
    if(p==='/api/auth/password'){
      passwordBody=body();assert.equal(passwordBody._version,member.profileVersion);
      member.displayName=passwordBody.displayName;member.profileVersion++;member.mustChangePassword=false;current=null;
      return reply({ok:true});
    }
    if(p==='/api/practices/config')return reply({_version:1,inputMode:'ocr',enabled:true,tested:true,endpoint:'https://maas.example.invalid/v1',model:'Example model',region:'test',apiKeySet:true,dailyLimit:20,maxTokens:8192,analysisTimeoutMinutes:10});
    if(p.startsWith('/api/'))throw Error('Unexpected fixture route '+p);
    const name=['/','/settings','/settings/maas'].includes(p)?'index.html':p==='/login'?'login.html':p.slice(1);
    await route.fulfill({body:await fs.readFile(new URL(name,root)),
      contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.svg')?'image/svg+xml':'text/html'});
  });
  async function screenshot(name) {
    if(!process.env.PPL_TEST_ARTIFACTS)return;
    await fs.mkdir(process.env.PPL_TEST_ARTIFACTS,{recursive:true});
    await page.screenshot({path:path.join(process.env.PPL_TEST_ARTIFACTS,name+'.png'),animations:'disabled'});
  }
  try {
    await page.goto(origin);
    await page.locator('#nav [data-menu-id=admin]').click();
    await page.getByRole('heading',{name:'团队成员',exact:true}).waitFor();
    assert.equal(await page.locator('#roles').getByRole('button',{name:'删除',exact:true}).count(),0);
    await page.getByRole('button',{name:'新增角色',exact:true}).click();
    await page.getByLabel('角色名称 *',{exact:true}).fill('临时 <角色>');
    await page.getByRole('button',{name:'保存',exact:true}).click();
    const customRow=page.locator('#roles .listrow').filter({hasText:'临时 <角色>'});
    await customRow.getByRole('button',{name:'删除',exact:true}).click();
    await page.getByRole('heading',{name:'删除角色',exact:true}).waitFor();
    await page.getByRole('button',{name:'取消',exact:true}).click();
    assert.equal(deletedRoles.length,0);
    await customRow.getByRole('button',{name:'删除',exact:true}).click();
    await page.locator('#modal [data-language=en]').click();
    await page.getByRole('button',{name:'Confirm deletion',exact:true}).click();
    await customRow.waitFor({state:'detached'});
    assert.equal(deletedRoles.length,1);
    await page.reload();await page.locator('#nav [data-menu-id=admin]').click();
    assert.equal(await page.locator('#roles').getByText('临时 <角色>',{exact:true}).count(),0);
    roles.push({id:'occupied-role',name:'Occupied role',permissions:[],builtin:false,_version:1,memberCount:1});
    await page.reload();await page.locator('#nav [data-menu-id=admin]').click();
    await page.locator('#roles .listrow').filter({hasText:'Occupied role'}).getByRole('button',{name:'Delete',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'Confirm deletion',exact:true}).count(),0);
    await page.getByText('Members still use this role. Assign them to another role before deleting it.',{exact:true}).waitFor();
    await page.setViewportSize({width:390,height:844});
    await screenshot('role-in-use-en');
    const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('main *')].map(el=>({tag:el.tagName,id:el.id,css:el.className,right:el.getBoundingClientRect().right})).filter(el=>el.right>innerWidth+1).slice(0,15)}));
    assert(layout.scroll<=layout.width,JSON.stringify(layout));
    await page.getByRole('button',{name:'Close',exact:true}).click();
    await page.setViewportSize({width:1280,height:900});
    await page.locator('header [data-language=zh]').click();
    assert.equal(await page.locator('.dictionary-card').count(),0);
    assert.equal(await page.getByRole('button',{name:'配置 MaaS',exact:true}).count(),0);
    assert.match(await page.locator('#profile').innerText(),/管理员甲/);
    assert(!((await page.locator('#profile').innerText()).includes(admin.email)));
    await page.getByRole('button',{name:'新增成员',exact:true}).click();
    await page.locator('[name=email]').fill('new@example.invalid');
    await page.getByLabel('展示名',{exact:true}).fill('新成员 <研发>');
    await page.getByRole('button',{name:'保存',exact:true}).click();
    await page.getByRole('heading',{name:'账号初始密码',exact:true}).waitFor();
    assert.equal(memberBody.displayName,'新成员 <研发>');
    await page.locator('#modal .formactions button').last().click();
    assert.match(await page.locator('#members').innerText(),/新成员 <研发>/);
    assert.equal(await page.locator('#members 研发').count(),0);
    await page.getByRole('button',{name:'个人资料',exact:true}).first().click();
    await page.getByLabel('展示名 *',{exact:true}).fill('管理员 <平台>');
    await page.getByRole('button',{name:'保存',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#profile').textContent.includes('管理员 <平台>'));
    await page.reload();
    assert.match(await page.locator('#profile').innerText(),/管理员 <平台>/);
    await page.locator('#nav [data-menu-id=maas]').click();
    assert.equal(await page.locator('#workspacePageTitle').innerText(),'设置');
    assert.equal(new URL(page.url()).pathname,'/settings');
    assert(await page.getByRole('tab',{name:'数据字典',exact:true}).isVisible());
    assert(await page.locator('.dictionary-card').count()>5);
    await screenshot('settings-dictionaries-zh');
    await page.getByRole('tab',{name:'AI 配置',exact:true}).click();
    assert.equal(await page.locator('.dictionary-card').count(),0);
    await page.getByRole('button',{name:'配置 MaaS',exact:true}).waitFor();
    await screenshot('settings-ai-zh');
    await page.getByRole('button',{name:'配置 MaaS',exact:true}).click();
    assert.equal(await page.locator('#form [name=model]').inputValue(),'Example model');
    await page.getByRole('button',{name:'取消',exact:true}).click();
    await page.locator('header [data-language=en]').click();
    await page.getByRole('tab',{name:'AI configuration',exact:true}).waitFor();
    assert.equal(await page.locator('#workspacePageTitle').innerText(),'Settings');
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.getByRole('tab',{name:'Data dictionaries',exact:true}).click();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.getByRole('tab',{name:'AI configuration',exact:true}).click();
    await page.setViewportSize({width:1280,height:900});
    await page.reload();
    await page.getByRole('button',{name:'Configure MaaS',exact:true}).waitFor();
    await page.goto(origin+'/settings/maas');
    await page.locator('#modal[open]').waitFor();
    await page.getByRole('button',{name:'Cancel',exact:true}).click();
    await page.goto(origin);
    await page.getByRole('button',{name:'New project',exact:true}).click();
    assert.match(await page.locator('[name=saId]').innerText(),/管理员预填 · member@example.invalid/);
    await page.getByRole('button',{name:'Cancel',exact:true}).click();
    current=null;
    await page.goto(origin+'/login');
    await page.getByLabel('Email',{exact:true}).fill(member.email);
    await page.getByLabel('Password',{exact:true}).fill('Synthetic-initial-password');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await page.getByLabel('Display name *',{exact:true}).waitFor();
    assert.equal(await page.getByLabel('Display name *',{exact:true}).inputValue(),'管理员预填');
    await page.reload();
    assert.equal(await page.getByLabel('Display name *',{exact:true}).inputValue(),'管理员预填');
    await page.setViewportSize({width:390,height:844});
    await page.getByLabel('Display name *',{exact:true}).fill('Ana 林 <SA>');
    await page.locator('#newPassword').fill('Synthetic-personal-password');
    await page.locator('#repeat').fill('Synthetic-personal-password');
    await page.locator('[data-language=zh]').click();
    assert.equal(await page.getByLabel('展示名 *',{exact:true}).inputValue(),'Ana 林 <SA>');
    await page.locator('[data-language=en]').click();
    await page.getByLabel('Current password',{exact:true}).fill('Synthetic-initial-password');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await screenshot('first-login-en');
    await page.getByRole('button',{name:'Save new password',exact:true}).click();
    await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();
    assert.equal(passwordBody.displayName,'Ana 林 <SA>');
    await page.getByLabel('Password',{exact:true}).fill('Synthetic-personal-password');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await page.locator('#nav [data-menu-id=home]').waitFor();
    assert.equal(await page.locator('#nav [data-menu-id=maas]').count(),0);
    assert.equal(await page.locator('#nav [data-menu-id=admin]').count(),0);
    assert.match(await page.locator('#profile').innerText(),/Ana 林 <SA>/);
    await page.getByRole('button',{name:'My profile',exact:true}).first().click();
    assert.equal(await page.getByLabel('Display name *',{exact:true}).inputValue(),'Ana 林 <SA>');
    assert.deepEqual(errors,[]);
    console.log('PASS: member display name, profile edits, first-sign-in name confirmation, phone layout, settings tabs, legacy AI link and role-filtered navigation');
  } finally {await context.close()}
}
