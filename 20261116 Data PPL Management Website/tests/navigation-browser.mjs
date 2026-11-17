import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

export async function verifyNavigationBrowser(browser) {
  const origin='https://nav-fixture.invalid',root=new URL('../public/',import.meta.url);
  const initial=['practices','home','projects','poc','library','reports','admin','maas','audit'];
  let setting={order:initial,_version:0};
  const errors=[],contexts=[];
  async function open(role,touch=false){
    const context=await browser.newContext({viewport:touch?{width:390,height:844}:{width:1280,height:900},hasTouch:touch,isMobile:touch});
    contexts.push(context);
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    const permissions=role==='admin'?['practice.read','project.read.all','resource.read','report.view','member.manage','audit.view']:['project.read.own'];
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url()),path=url.pathname;
      if(url.origin!==origin)return route.abort();
      if(path==='/api/me')return route.fulfill({json:{user:{id:role,email:role+'@example.invalid',roleId:role,roleName:role,permissions},source:{}}});
      if(path==='/api/workspace')return route.fulfill({json:{navigation:setting,projects:[],roles:[],resources:[],members:[]}});
      if(path==='/api/navigation')return route.fulfill({json:setting});
      if(path==='/api/admin/navigation'){
        const body=route.request().postDataJSON();
        if(body._version!==setting._version)return route.fulfill({status:409,json:{error:'conflict'}});
        assert.equal(role,'admin');setting={order:body.order,_version:body._version+1};
        return route.fulfill({json:setting});
      }
      if(path.startsWith('/api/'))throw Error('Unexpected fixture route '+path);
      const name=path==='/'?'index.html':path.slice(1);
      return route.fulfill({body:await fs.readFile(new URL(name,root)),contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html'});
    });
    await page.goto(origin);await page.locator('#nav [data-menu-id]').first().waitFor();return page;
  }
  const order=page=>page.locator('#nav [data-menu-id]').evaluateAll(rows=>rows.map(row=>row.dataset.menuId));
  async function dragFirst(page,id,touch=false){
    const source=page.locator('[data-menu-id="'+id+'"] [data-nav-grip]');
    const start=await source.boundingBox(),first=await page.locator('.nav-sort-row').first().boundingBox();
    const x=Math.round(start.x+start.width/2),y=Math.round(start.y+start.height/2),end=Math.ceil(first.y+4);
    if(touch){
      const cdp=await page.context().newCDPSession(page);
      await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
      await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:end}]});
      await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
      await cdp.detach();
    }else{
      await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x,end,{steps:8});await page.mouse.up();
    }
    await page.waitForFunction(firstId=>document.querySelector('.nav-sort-row').dataset.menuId===firstId,id);
  }
  try{
    const admin=await open('admin');assert.deepEqual(await order(admin),initial);
    await admin.locator('#navEdit').click();
    assert(await admin.locator('#navSave').isDisabled());
    await dragFirst(admin,'poc');
    await admin.locator('[data-menu-id="poc"] [data-nav-grip]').press('ArrowDown');
    assert.equal((await order(admin))[1],'poc');
    await admin.locator('#navCancel').click();assert.deepEqual(await order(admin),initial);assert.equal(setting._version,0);
    await admin.locator('#navEdit').click();await dragFirst(admin,'projects');
    await admin.locator('#navSave').click();await admin.locator('#navEdit').waitFor();
    const saved=['projects',...initial.filter(id=>id!=='projects')];
    assert.deepEqual(setting.order,saved);
    await admin.reload();await admin.locator('#navEdit').waitFor();assert.deepEqual(await order(admin),saved);
    await admin.locator('header [data-language=en]').click();
    await admin.getByRole('button',{name:'Reorder',exact:true}).click();
    await admin.getByRole('button',{name:'Move down · Projects',exact:true}).click();
    // A second admin saves from a different device while this editor is open.
    const mobile=await open('admin',true);await mobile.locator('#navEdit').tap();await dragFirst(mobile,'poc',true);
    await mobile.locator('#navSave').tap();await mobile.locator('#navEdit').waitFor();
    assert.equal(setting.order[0],'poc');
    await admin.getByRole('button',{name:'Save order',exact:true}).click();
    await admin.getByText('Another administrator saved a new order.',{exact:false}).waitFor();
    assert.deepEqual(await order(admin),setting.order);assert(await admin.locator('#navSave').isDisabled());
    await admin.locator('#navCancel').click();
    const member=await open('bd');assert(await member.locator('#navEdit').isHidden());
    assert.deepEqual(await order(member),setting.order.filter(id=>['home','projects','poc'].includes(id)));
    assert.deepEqual(errors,[]);
    console.log('PASS: admin drag, touch, arrow buttons and keyboard, cancel, save/reload, bilingual menu, concurrent edits and member view');
  }finally{for(const context of contexts)await context.close()}
}
