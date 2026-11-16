import assert from 'node:assert/strict';
import {translationEntries,translationBatch,translationMessages,acceptTranslations,translatedResult,resultLanguage} from '../server/architecture-languages.mjs';
import {targetDrawing} from '../server/architecture-drawing.mjs';

const primary={summary:'保存原始数据',readability:'clear',limitations:['方向待确认'],vendors:[{name:'AWS',products:['Amazon S3'],evidence:'图中标签 L1',basis:'observed',confidence:'high'}],
 components:[{id:'c1',name:'数据接入',vendor:'AWS',product:'Amazon S3',layer:'ingestion',role:'保存原始数据',evidence:'图中标签 L1',basis:'observed'}],
 flows:[{from:'c1',to:'c1',data:'审计事件',mode:'stream',evidence:'方向待确认',basis:'inferred',directionConfirmed:false}],
 risks:[],mappings:[{componentId:'c1',serviceIds:['obs'],reason:'保存原始数据',changes:'验证接口',validation:'图中标签 L1'}],
 target:{summary:'保存原始数据',nodes:[{id:'t1',serviceId:'obs',layer:'storage',role:'保存原始数据'},{id:'t2',serviceId:'dli',layer:'processing',role:'处理事件'}],flows:[{from:'t1',to:'t2',data:'审计事件'}]},
 comparison:[],migration:[],questions:['验证接口']};
const strings={'保存原始数据':'Store raw data','方向待确认':'Direction requires confirmation','图中标签 L1':'Diagram label L1','数据接入':'Data ingestion','审计事件':'Audit events','验证接口':'Validate the interface','处理事件':'Process events'};
const entries=translationEntries(primary,'en');
assert.equal(entries.length,Object.keys(strings).length);
assert.deepEqual(translationBatch(entries,{},8192),entries);
const body=JSON.parse(translationMessages(entries,'en')[1].content);
assert.equal(Object.keys(body).length,entries.length);assert.ok(!Object.values(body).includes('c1'));assert.ok(!Object.values(body).includes('obs'));
const full=Object.fromEntries([...entries].reverse().map(e=>[e.key,strings[e.text]]));
const progress=acceptTranslations(JSON.stringify(full),entries,'en');
assert.deepEqual(translationBatch(entries,progress,8192),[]);
const first=entries[0];
const partial=acceptTranslations(JSON.stringify({...full,[first.key]:first.text}),entries,'en');
assert.deepEqual(translationBatch(entries,partial,8192),[first]);
assert.throws(()=>translatedResult(primary,entries,partial),e=>e.modelCode==='TRANSLATION_INVALID');
const english=translatedResult(primary,entries,progress);
assert.equal(english.summary,'Store raw data');assert.equal(primary.summary,'保存原始数据');
assert.equal(english.flows[0].directionConfirmed,false);assert.equal(english.flows[0].basis,'inferred');
assert.equal(english.components[0].id,primary.components[0].id);assert.deepEqual(english.mappings[0].serviceIds,['obs']);
assert.deepEqual(english.vendors[0].products,['Amazon S3']);
assert.equal(english.target.flows[0].data,'Audit events');assert.equal(english.target.flows[0].from,'t1');
assert.doesNotMatch(JSON.stringify(english),/\p{Script=Han}/u);
const enDiagram=targetDrawing(english.target,'en'),zhDiagram=targetDrawing(primary.target,'zh');
for(const file of [enDiagram.xml,enDiagram.svg]){assert.ok(file.includes('Store raw data'));assert.ok(file.includes('Audit events'));assert.doesNotMatch(file,/\p{Script=Han}/u)}
for(const file of [zhDiagram.xml,zhDiagram.svg])assert.ok(file.includes('保存原始数据'));
const reverseEntries=translationEntries(english,'zh'),reverseTexts=Object.fromEntries(Object.entries(strings).map(([a,b])=>[b,a]));
const zh=acceptTranslations(JSON.stringify(Object.fromEntries(reverseEntries.map(e=>[e.key,reverseTexts[e.text]??e.text]))),reverseEntries,'zh');
assert.deepEqual(translatedResult(english,reverseEntries,zh),primary);
assert.equal(resultLanguage(null,'zh'),'zh');assert.equal(resultLanguage('en','zh'),'en');assert.throws(()=>resultLanguage('fr','zh'));
console.log('PASS: bilingual prose, stable graph and evidence, validated batch recovery, both draw.io languages');
