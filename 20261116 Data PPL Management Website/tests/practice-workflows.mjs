import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {deflateRawSync} from 'node:zlib';

const received=[];
export function textModelReply(body,template) {
  for(const m of body.messages)assert.equal(typeof m.content,'string','text endpoint accepts text only');
  assert(!JSON.stringify(body).includes('data:image/'));
  if(body.messages.length===1){
    const nonce=JSON.parse(body.messages[0].content.match(/\{.*\}$/)[0]);
    return Response.json({choices:[{message:{content:JSON.stringify(nonce)}}]});
  }
  const input=JSON.parse(body.messages.at(-1).content);
  received.push(input);
  const output=structuredClone(template);
  output.summary='MySQL, Kafka and a data warehouse';
  output.components=['MySQL','Kafka','数据仓库'].map((s,i)=>({id:'c'+i,name:s,product:s,vendor:'Unconfirmed',layer:i===1?'ingestion':'storage',role:s,evidence:'OCR label',basis:'observed'}));
  output.mappings=output.components.map((c,i)=>({componentId:c.id,serviceIds:[['rds-mysql','kafka','dws'][i]],reason:'Compatible workload',validation:'Verify version and region',changes:'Verify connectors'}));
  output.flows=[{from:'c0',to:'c1',data:'Events',mode:'unknown',evidence:'Candidate line',basis:'observed'},{from:'c1',to:'c2',data:'Events',mode:'unknown',evidence:'Candidate line',basis:'observed'}];
  output.target.nodes=output.components.map((c,i)=>({id:'t'+i,serviceId:output.mappings[i].serviceIds[0],layer:c.layer,role:'Target '+c.product}));
  output.target.flows=[{from:'t0',to:'t1',data:'Events'},{from:'t1',to:'t2',data:'Ingest events'}];
  output.usedReferences=['R1','nonexistent'];
  return Response.json({choices:[{message:{content:JSON.stringify(output)}}]});
}

export async function verifyPracticeWorkflows({app,call,cookie,viewerCookie,page,query,records,origin}) {
  await app.practices.stop();
  const get=async p=>(await call('practices'+p,'GET',undefined,cookie)).body;
  const post=(p,b)=>call('practices'+p,'POST',b,cookie);
  const before=await get('/config');
  assert.equal((await post('/config',{...before,model:'text-fixture',inputMode:'ocr',apiKey:''})).body.ready,false);
  await query('DELETE FROM architecture_usage WHERE owner_email=?',['i18n@test.local']);
  assert.equal((await post('/test',{})).body.ready,true,'real OCR and the text provider connection test');
  const base=(await fs.readFile(new URL('../server/ocr-check.png',import.meta.url))).toString('base64');
  const variant=async label=>page.evaluate(async({base,label})=>{
    const canvas=document.createElement('canvas');canvas.width=960;canvas.height=260;
    const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,960,260);
    if(label!=='BLANK'){
      const img=new Image();img.src='data:image/png;base64,'+base;await img.decode();ctx.drawImage(img,0,0);
      ctx.fillStyle='#182b43';ctx.font='26px Arial';ctx.fillText(label,25,45);
    }
    return canvas.toDataURL().split(',')[1];
  },{base,label});
  async function analyze(name,image,nominate=false){
    const body={requestKey:crypto.randomUUID(),title:name,businessType:'数据库',language:'en',targetRegion:'Santiago',context:'Review Kafka and MySQL',name:'fixture.png',mime:'image/png',base64:image,inputMode:'ocr',referenceRequested:nominate};
    const queued=await post('',body);assert.equal(queued.status,202,JSON.stringify(queued.body));records.push(queued.body.id);
    assert.equal(await app.practices.runNext(),true);return get('/'+queued.body.id);
  }
  const first=await analyze('Reviewed MySQL fixture A',base,true);
  assert.equal(first.status,'succeeded',first.errorMessage);assert.equal(first.inputMode,'ocr');
  assert.equal(first.referenceRequested,true);assert.equal(first.reference,null);assert.equal((await get('/references')).total,0);
  assert.deepEqual(first.ocrEvidence.labels.map(l=>l.text.toLowerCase()).sort(),['kafka','mysql','数据仓库'].sort());
  assert.equal(first.result.flows[0].directionConfirmed,true);assert.equal(first.result.flows[1].directionConfirmed,false);
  const publish=async(item,summary)=>post('/'+item.id+'/reference',{_version:item.version,publish:true,reviewed:true,title:'Reviewed '+item.id.slice(0,8),summary,mappings:item.referenceCandidates.filter(x=>x.service==='kafka')});
  assert.equal((await publish(first,'Kafka replication, review A')).status,200);
  assert.equal((await publish(first,'Stale review')).status,409);
  const second=await analyze('Reviewed MySQL fixture B',await variant('Second architecture'));
  assert.equal(second.sources.length,1);assert.equal(second.sources[0].used,true);assert.equal(second.sources[0].id,first.id);
  assert(!JSON.stringify(received.at(-1).reviewedCases).includes('fixture.png'));assert.deepEqual(Object.keys(received.at(-1).reviewedCases[0]).sort(),['alias','mappings','summary']);
  assert.deepEqual(received.at(-1).reviewedCases[0].mappings,[{product:'kafka',service:'kafka'}]);
  assert.equal((await publish(second,'Kafka replication, review B')).status,200);
  const library=await get('/references');assert.equal(library.total,2);assert(Number(library.patterns.find(x=>x.service_id==='kafka').cases_used)===2);
  assert.equal((await get('/references?q=nonexistent')).total,0);
  assert.equal((await get('/references?product=kafka&service=kafka')).total,2);
  const duplicate=await analyze('Same original file',base);
  assert(!duplicate.sources.some(x=>x.id===first.id));assert.equal((await publish(duplicate,'Duplicate')).status,409);
  const current=await get('/'+first.id);assert.equal((await post('/'+first.id+'/reference',{_version:current.version,publish:false})).status,200);
  assert.equal((await get('/'+second.id)).sources[0].available,false);
  assert.equal((await get('/references')).patterns.length,0);
  const secondNow=await get('/'+second.id);
  const archive=await post('/'+second.id+'/archive',{_version:secondNow.version});assert.equal(archive.status,200);
  const third=await analyze('Current MySQL architecture',await variant('Third architecture'));
  assert.equal(third.sources.length,0);
  assert.equal((await post('/'+second.id+'/restore',{_version:archive.body.version})).status,200);
  const attempts=received.length,empty=await analyze('Unreadable architecture',await variant('BLANK'));assert.equal(empty.error_code,'OCR_NO_TEXT');assert.equal(received.length,attempts);
  const path='/'+third.id+'/drawing',initial=await get(path);
  assert.equal(initial.version,0);for(const n of third.result.target.nodes)assert(initial.xml.includes('id="n-'+n.id+'"'));
  assert(initial.xml.includes('RDS for MySQL')&&initial.xml.includes('DMS for Kafka')&&initial.xml.includes('GaussDB(DWS)'));
  assert(initial.xml.includes('source="n-t0" target="n-t1"'));
  assert.equal((await call('practices'+path)).status,401);
  assert.equal((await call('practices'+path,'GET',undefined,viewerCookie)).status,403);
  const preview=await variant('Edited architecture');const modified=initial.xml.replace('Target MySQL','Approved MySQL design');
  const graph=modified.match(/<mxGraphModel[\s\S]*<\/mxGraphModel>/)[0];
  const compressed='<mxfile><diagram id="target">'+deflateRawSync(Buffer.from(encodeURIComponent(graph))).toString('base64')+'</diagram></mxfile>';
  const editor=initial.editorOrigin;
  // Exercise the official init/load/save/export protocol deterministically without sending a test case to a third party.
  const editorEvents=[];
  page.on('console',m=>{if(m.type()==='error')editorEvents.push(m.text().slice(0,160))});
  page.on('pageerror',e=>editorEvents.push(e.message.slice(0,160)));
  await page.route(editor+'/**',route=>route.fulfill({contentType:'text/html',body:`<button id="save">Edit and save</button><script>
    let xml;const send=d=>parent.postMessage(JSON.stringify(d),${JSON.stringify(origin)});
    addEventListener('message',e=>{if(e.origin!==${JSON.stringify(origin)})return;const d=JSON.parse(e.data);
      if(d.action==='load'){xml=d.xml;document.body.dataset.loaded=xml.includes('RDS for MySQL')}
      if(d.action==='export')send({event:'export',format:'png',data:'data:image/png;base64,'+${JSON.stringify(preview)}})
    });document.querySelector('#save').onclick=()=>send({event:'save',exit:true,xml:${JSON.stringify(compressed)}});send({event:'init'});</script>`}));
  await page.locator('#nav button').filter({hasText:'Best practices'}).click();
  await page.getByRole('button',{name:'Reference library',exact:true}).click();await page.getByRole('heading',{name:'Reviewed cases'}).waitFor();
  await page.getByRole('button',{name:'Reviewed MySQL fixture B',exact:true}).click();
  await page.getByRole('heading',{name:'Reviewed MySQL fixture B'}).waitFor();
  await page.locator('.practice-item').filter({hasText:'Current MySQL architecture'}).click();
  await page.getByRole('tab',{name:'Solution comparison'}).click();
  await page.getByRole('button',{name:'Edit in draw.io'}).click();
  const frame=page.frameLocator('.drawio-editor iframe');try{await frame.locator('body[data-loaded=true]').waitFor({timeout:10000})}catch(e){
    console.log('Editor diagnostic',editorEvents,page.frames().map(f=>f.url().split('?')[0]),await page.locator('.drawio-status').allTextContents(),await page.locator('#toast').allTextContents());
    throw e;
  }
  await frame.locator('#save').click();await page.locator('.drawio-editor').waitFor({state:'detached'});
  const edited=await get(path);assert.equal(edited.version,1);assert(edited.xml.includes('Approved MySQL design'));assert(!edited.xml.includes(compressed));
  const dl=page.waitForEvent('download');await page.getByRole('link',{name:'Download .drawio'}).click();
  const file=await dl;assert(file.suggestedFilename().endsWith('.drawio'));assert.equal(await fs.readFile(await file.path(),'utf8'),edited.xml);
  const report=page.waitForEvent('download');await page.getByRole('button',{name:'Export analysis report'}).click();
  const html=await fs.readFile(await (await report).path(),'utf8');assert(html.includes(preview));assert(!html.includes('onclick='));
  assert.equal((await post(path,{version:0,xml:initial.xml,preview})).status,409);
  assert.equal((await post(path,{version:1,xml:'<mxfile/>',preview})).status,400);
  assert.equal((await get(path)).xml,edited.xml);
  await page.reload();await page.locator('#nav button').filter({hasText:'Best practices'}).click();await page.locator('.practice-item').filter({hasText:'Current MySQL architecture'}).click();await page.getByRole('tab',{name:'Solution comparison'}).click();
  await page.locator('.target-preview').waitFor();assert((await page.locator('.target-preview').getAttribute('src')).endsWith('v=1'));
  console.log('PASS: real bilingual OCR, confirmed and unknown flow directions, text-only requests, opt-in/RDS retrieval and withdrawal, recurring mappings, draw.io protocol, compressed input, saved preview, offline export, and revision conflicts.');
}
