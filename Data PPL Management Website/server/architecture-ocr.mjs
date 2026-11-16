import fs from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {modelError} from './architecture-model.mjs';

export const OCR_TIMEOUT_MS = 62_000;

export async function recognizeDiagram(bytes, env) {
  let response;
  try {
    response=await fetch(env.OCR_ENDPOINT || 'http://ocr:8091/extract',{
      method:'POST',redirect:'error',signal:AbortSignal.timeout(OCR_TIMEOUT_MS),
      headers:{'Content-Type':'application/octet-stream'},body:bytes
    });
    const data=await response.json();
    if (!response.ok) throw modelError(['INVALID_IMAGE','OCR_TIMEOUT','OCR_BUSY'].includes(data.code)?data.code:'OCR_UNAVAILABLE');
    if (!Array.isArray(data.labels)||!Array.isArray(data.connections)||data.labels.length>100||data.connections.length>80) throw modelError('OCR_UNAVAILABLE');
    return data;
  } catch(error) {
    if(error.modelCode) throw error;
    throw modelError(error.name==='TimeoutError'?'OCR_TIMEOUT':'OCR_UNAVAILABLE');
  }
}

export async function textProbe(env) {
  const bytes=await fs.readFile(new URL('ocr-check.png',import.meta.url));
  const scan=await recognizeDiagram(bytes,env);
  const labels=scan.labels.map(l=>l.text.toLowerCase()).join(' ');
  if (!labels.includes('mysql') || !labels.includes('kafka')) throw modelError('OCR_UNAVAILABLE');
  const code=randomUUID().slice(0,8);
  return {code,messages:[{role:'user',content:'Return only this JSON object verbatim: '+JSON.stringify({code})}]};
}

const fold=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
export function verifyFlowDirections(result,evidence) {
  const assigned=new Map();
  for(const l of evidence.labels) {
    const label=fold(l.text);
    const hits=result.components.filter(c=>[c.product,c.name].some(s=>{
      const name=fold(s);return name.length>=2&&label.length>=2&&(label===name||name.length>=4&&label.includes(name));
    }));
    if(hits.length===1)assigned.set(l.id,hits[0].id);
  }
  const observed=new Set();
  for(const link of evidence.connections) {
    if(!['a-to-b','b-to-a'].includes(link.direction))continue;
    const ends=[assigned.get(link.a),assigned.get(link.b)];
    if(ends.every(Boolean))observed.add((link.direction==='b-to-a'?ends.reverse():ends).join(':'));
  }
  for(const f of result.flows) {
    f.directionConfirmed=observed.has(f.from+':'+f.to);
    if(!f.directionConfirmed&&f.basis==='observed') f.basis='inferred';
  }
}
