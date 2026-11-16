import assert from 'node:assert/strict';
import {callModel, DEFAULT_ANALYSIS_MINUTES, parseModelJSON, validateAnalysis} from '../server/architecture-model.mjs';

const config={endpoint:'https://api-ap-southeast-1.modelarts-maas.com/openai/v1/chat/completions',model:'glm-5.3',analysisTimeoutMinutes:11,maxTokens:8192};
const content='{"summary":"云端架构"}';
const usage={prompt_tokens:92,completion_tokens:180,total_tokens:272};
const packet=value=>'data: '+(typeof value==='string'?value:JSON.stringify(value))+'\r\n\r\n';
function streamResponse(events){
 const input=Buffer.from(': heartbeat\r\n\r\n'+events.map(packet).join(''));
 const stream=new ReadableStream({start(controller){
  for(let i=0;i<input.length;i+=5)controller.enqueue(input.subarray(i,i+5));
  controller.close();
 }});
 return new Response(stream,{headers:{'Content-Type':'text/event-stream; charset=utf-8','x-request-id':'trace-42'}});
}
const fragment=text=>({choices:[{delta:{content:text}}]});
const finish=reason=>({choices:[{delta:{},finish_reason:reason}]});
let request;
const run=(events,options={})=>callModel(config,[],{stream:true,fetchImpl:async (url,init)=>{
 request=JSON.parse(init.body);return streamResponse(events);
},...options});

const timeoutCalls=[];
const realTimeout=AbortSignal.timeout;
try{
 AbortSignal.timeout=ms=>{timeoutCalls.push(ms);return realTimeout.call(AbortSignal,ms)};
 const result=await run([{choices:[{delta:{reasoning_content:'private reasoning'}}]},fragment(content.slice(0,10)),fragment(content.slice(10)),finish('stop'),{choices:[],usage},'[DONE]']);
 assert.deepEqual(result,{content,usage});
 assert.equal(timeoutCalls[0],11*60_000);
 assert.equal(request.stream,true);assert.deepEqual(request.stream_options,{include_usage:true});assert.equal(request.reasoning_effort,'low');assert.equal(request.max_tokens,8192);
 const buffered=await callModel({endpoint:'https://api.modelarts-maas.com/v2/chat/completions',model:'another-model'},[],{fetchImpl:async (_,init)=>{
  const body=JSON.parse(init.body);
  assert.equal(body.stream,false);assert.equal(body.max_completion_tokens,8192);assert.equal(body.reasoning_effort,undefined);
  return Response.json({choices:[{message:{content:'ok'}}]});
 }});
 assert.equal(buffered.content,'ok');assert.equal(timeoutCalls[1],DEFAULT_ANALYSIS_MINUTES*60_000);
}finally{AbortSignal.timeout=realTimeout}
await assert.rejects(run([fragment(content)]),e=>e.modelCode==='MAAS_STREAM_INTERRUPTED'&&e.requestId==='trace-42');
await assert.rejects(run([fragment(content),finish('length'),'[DONE]']),e=>e.modelCode==='MODEL_OUTPUT_TRUNCATED');
await assert.rejects(callModel(config,[],{fetchImpl:async()=>new Response('upstream private details',{status:504})}),e=>e.modelCode==='MAAS_UPSTREAM_TIMEOUT'&&e.httpStatus===504&&!e.message.includes('private'));
await assert.rejects(callModel(config,[],{timeoutMs:5,fetchImpl:async(_,init)=>new Promise((resolve,reject)=>{
 const hold=setTimeout(()=>resolve(Response.json({choices:[]})),100);
 init.signal.addEventListener('abort',()=>{clearTimeout(hold);reject(init.signal.reason)},{once:true});
})}),e=>e.modelCode==='MAAS_TIMEOUT');

const minimal={summary:'Minimal review',readability:'partial',limitations:[],vendors:[],components:[],flows:[],risks:[],mappings:[],target:{summary:'Target',nodes:[],flows:[]},comparison:[],migration:[],questions:[]};
assert.deepEqual(validateAnalysis(minimal),minimal);
const checks=[
 [{...minimal,questions:null},'$.questions','type'],
 [{...minimal,summary:undefined},'$.summary','missing'],
 [{...minimal,readability:'unrecognized'},'$.readability','enum'],
 [{...minimal,migration:[{step:'1',actions:['do'],acceptance:'ok'}]},'$.migration[0].actions','type'],
 [{...minimal,target:{summary:'x',nodes:[{id:'n',serviceId:'unlisted',layer:'storage',role:'x'}],flows:[]}},'$.target.nodes[0].serviceId','catalog'],
 [{...minimal,flows:[{from:'missing',to:'t2',data:'x',mode:'stream',basis:'inferred',evidence:'x'}]},'$.flows[0].from','reference']
];
for(const [value,path,issue] of checks)assert.throws(()=>validateAnalysis(value),e=>e.modelCode==='INVALID_MODEL_RESPONSE'&&e.validationPath===path&&e.validationIssue===issue);
assert.throws(()=>parseModelJSON('bad response'),e=>e.validationPath==='$'&&e.validationIssue==='invalid_json');
console.log('PASS: field-level, sanitized diagnostics for invalid architecture output');

console.log('PASS: configurable analysis deadline, streamed UTF-8 completions, usage, interruption, truncation and gateway timeouts');
