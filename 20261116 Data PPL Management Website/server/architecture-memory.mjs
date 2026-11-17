import {createHash} from 'node:crypto';
import {authError} from './auth.mjs';
import {SERVICE_CATALOG} from './architecture-catalog.mjs';

const validServices = new Set(SERVICE_CATALOG.map(s => s.id));
const common = new Set('the for and from with into this that use used uses using review verify validate confirm source target region recommended proposed data cloud architecture platform service solution huawei aws amazon microsoft google azure apache project current native storage query 数据 架构 客户 平台 服务 存储 分析 业务 云端 数据库 确认 复核 验证'.split(' '));
const canonical = { 'amazon s3':'s3', 'amazon athena':'athena', 'apache kafka':'kafka',
  'amazon redshift':'redshift', 'azure synapse analytics':'synapse', 'google bigquery':'bigquery',
  'apache spark':'spark', 'apache flink':'flink', 'postgres':'postgresql', 'ms sql server':'sql server' };

export function normalizedTerms(...strings) {
  const terms = new Set();
  for (const source of strings) {
    const words = String(source || '').normalize('NFKC').toLowerCase().match(/[a-z][a-z0-9+#.-]{1,39}|[\u3400-\u9fff]{2,32}/gu) || [];
    for (const word of words) {
      if (!common.has(word)) terms.add(word);
      if (/^[\u3400-\u9fff]{4,}$/u.test(word)) {
        for (let i = 0; i < word.length - 2; i++) {
          const part = word.slice(i, i+3);
          if (!common.has(part)) terms.add(part);
        }
      }
    }
  }
  return [...terms].slice(0,100);
}

function productName(component) {
  const name = (component.product || component.name || '').normalize('NFKC').trim().toLowerCase();
  if (!name || /^(unknown|n\/a|未知|待确认|不明)$/.test(name)) return '';
  return (canonical[name] || name).slice(0,100);
}

export function mappingCandidates(result) {
  const candidates = new Map();
  for (const mapping of result.mappings || []) {
    const component = result.components.find(c => c.id === mapping.componentId);
    if (!component || component.basis === 'unknown') continue;
    const product = productName(component);
    if (!product) continue;
    for (const service of mapping.serviceIds.filter(id => validServices.has(id))) {
      candidates.set(product+'\n'+service, {product, service});
    }
  }
  return [...candidates.values()];
}

async function caseMappings(client, ids) {
  if (!ids.length) return [];
  const marks=ids.map(()=>'?').join(',');
  return (await client.query(`SELECT analysis_id,product,service_id FROM architecture_case_mappings WHERE analysis_id IN (${marks}) ORDER BY product,service_id`,ids)).rows;
}

export async function readPracticeInput(client, id) {
  const row=(await client.query('SELECT * FROM architecture_inputs WHERE analysis_id=?',[id])).rows[0];
  return {
    inputMode:row?.input_mode || 'vision', digest:row?.image_digest,
    referenceRequested:!!row?.reference_requested,
    evidence:row?.evidence_json ? JSON.parse(row.evidence_json) : null,
    sources:row?.sources_json ? JSON.parse(row.sources_json) : []
  };
}

export async function caseDetails(client, row) {
  const input=await readPracticeInput(client,row.id);
  const saved=(await client.query('SELECT c.summary,c.reviewed_by,c.reviewed_at,pub.title FROM architecture_cases c LEFT JOIN architecture_case_publications pub USING(analysis_id) WHERE c.analysis_id=?',[row.id])).rows[0];
  const mappings=saved ? (await caseMappings(client,[row.id])).map(x=>({product:x.product,service:x.service_id})) : [];
  const sources=[];
  for (const source of input.sources) {
    const ref=(await client.query('SELECT pub.title'+visibleCases+' WHERE c.analysis_id=? AND a.archived_at IS NULL',[source.id])).rows[0];
    sources.push({id:source.id,alias:source.alias,used:source.used===true,terms:source.terms,title:ref?.title || '',available:!!ref});
  }
  return {inputMode:input.inputMode,referenceRequested:input.referenceRequested,ocrEvidence:input.evidence,
    sources,reference:saved ? {...saved,mappings} : null};
}

export async function saveReference(client, user, row, body, files) {
  if (!user.permissions.includes('practice.manage')) throw authError(403,'仅案例审核人可发布或撤下团队案例');
  if (body._version!==row.version) throw authError(409,'架构分析已更新，请刷新');
  if (typeof body.publish!=='boolean') throw authError(400,'参考案例内容无效');
  const input=await readPracticeInput(client,row.id);
  if (body.publish) {
    if (row.status!=='succeeded' || row.archived_at) throw authError(409,'请先完成分析并恢复归档记录');
    const title=typeof body.title==='string'?body.title.trim():'';
    if(!title || title.length>200 || body.reviewed!==true)throw authError(400,'请填写公开案例标题并确认已脱敏');
    const result=JSON.parse(row.result_json);
    const summary=typeof body.summary==='string' ? body.summary.trim() : '';
    if (!summary || summary.length>1000 || !Array.isArray(body.mappings) || body.mappings.length>150) throw authError(400,'参考案例内容无效');
    const candidates=mappingCandidates(result);
    const selected=candidates.filter(m=>body.mappings.some(b=>b?.product===m.product&&b.service===m.service));
    if (selected.length!==body.mappings.length) throw authError(400,'参考案例内容无效');
    let digest=input.digest;
    if (!digest) {
      const file=await files.get(row.image_key);
      if (!file) throw authError(404,'文件不存在');
      digest=createHash('sha256').update(Buffer.from(await new Response(file.body).arrayBuffer())).digest('hex');
    }
    const duplicate=(await client.query('SELECT analysis_id FROM architecture_cases WHERE image_digest=? FOR UPDATE',[digest])).rows[0];
    if (duplicate&&duplicate.analysis_id!==row.id) throw authError(409,'相同架构图已收录为参考案例');
    // Update by analysis ID only; the image uniqueness constraint also protects concurrent new submissions.
    if ((await client.query('SELECT analysis_id FROM architecture_cases WHERE analysis_id=? FOR UPDATE',[row.id])).rows.length) {
      await client.query('UPDATE architecture_cases SET summary=?,reviewed_by=?,reviewed_at=now() WHERE analysis_id=?',[summary,user.email,row.id]);
    } else {
      await client.query('INSERT INTO architecture_cases(analysis_id,image_digest,summary,reviewed_by) VALUES(?,?,?,?)',[row.id,digest,summary,user.email]);
    }
    await client.query('INSERT INTO architecture_case_publications(analysis_id,title) VALUES(?,?) ON DUPLICATE KEY UPDATE title=VALUES(title)',[row.id,title]);
    await client.query('DELETE FROM architecture_case_mappings WHERE analysis_id=?',[row.id]);
    for(const m of selected) await client.query('INSERT INTO architecture_case_mappings(analysis_id,product,service_id) VALUES(?,?,?)',[row.id,m.product,m.service]);
    await client.query('DELETE FROM architecture_case_terms WHERE analysis_id=?',[row.id]);
    const terms=normalizedTerms(...selected.map(m=>m.product),summary,...selected.map(m=>m.service));
    if(terms.length)await client.query('INSERT INTO architecture_case_terms(term,analysis_id) VALUES '+terms.map(()=>'(?,?)').join(','),terms.flatMap(t=>[t,row.id]));
    await client.query('INSERT INTO architecture_inputs(analysis_id,input_mode,image_digest,reference_requested) VALUES(?,?,?,1) ON DUPLICATE KEY UPDATE image_digest=VALUES(image_digest),reference_requested=1',[row.id,input.inputMode,digest]);
  } else {
    await client.query('DELETE FROM architecture_cases WHERE analysis_id=?',[row.id]);
    await client.query('UPDATE architecture_inputs SET reference_requested=0 WHERE analysis_id=?',[row.id]);
  }
  if((await client.query('UPDATE architecture_analyses SET version=version+1 WHERE id=? AND version=?',[row.id,row.version])).rowCount!==1)throw authError(409,'架构分析已更新，请刷新');
}

const visibleCases=' FROM architecture_cases c JOIN architecture_case_publications pub ON pub.analysis_id=c.analysis_id JOIN architecture_analyses a ON a.id=c.analysis_id ';
export async function publicCase(client,id) {
  const item=(await client.query('SELECT c.analysis_id AS id,pub.title,c.summary,c.reviewed_at,a.business_type'+visibleCases+'WHERE c.analysis_id=? AND a.archived_at IS NULL',[id])).rows[0];
  if(!item)throw authError(404,'参考案例不存在');
  const mappings=await caseMappings(client,[id]);
  return {...item,mappings:mappings.map(m=>({product:m.product,service:m.service_id}))};
}
export async function relevantCases(client, job, evidence, digest) {
  const terms=normalizedTerms(...(evidence?.labels || []).map(l=>l.text),job.title,job.context_text);
  if(!terms.length)return [];
  const sql=`SELECT c.analysis_id,c.summary,GROUP_CONCAT(t.term ORDER BY t.term) AS matches ${visibleCases}
    JOIN architecture_case_terms t ON t.analysis_id=c.analysis_id
    WHERE a.archived_at IS NULL AND c.analysis_id<>? AND c.image_digest<>? AND t.term IN (${terms.map(()=>'?').join(',')})
    GROUP BY c.analysis_id,c.summary,c.reviewed_at,a.business_type
    ORDER BY COUNT(*) DESC,(a.business_type=?) DESC,c.reviewed_at DESC,c.analysis_id LIMIT 3`;
  const hits=(await client.query(sql,[job.id,digest||'',...terms,job.business_type])).rows;
  const mappings=await caseMappings(client,hits.map(c=>c.analysis_id));
  return hits.map((c,i)=>({id:c.analysis_id,alias:'R'+(i+1),terms:c.matches.split(',').slice(0,8),summary:c.summary,
    mappings:mappings.filter(m=>m.analysis_id===c.analysis_id).slice(0,12).map(m=>({product:m.product,service:m.service_id}))}));
}

export async function referenceLibrary(client, url) {
  const page=Math.max(1,Math.min(10000,parseInt(url.searchParams.get('page'),10)||1));
  const query=(url.searchParams.get('q')||'').trim().slice(0,80);
  const product=url.searchParams.get('product')||'', service=url.searchParams.get('service')||'';
  const filters=['a.archived_at IS NULL'], args=[];
  if(query){filters.push('(LOCATE(?,pub.title)>0 OR LOCATE(?,c.summary)>0)');args.push(query,query)}
  if(product&&service){filters.push('EXISTS (SELECT 1 FROM architecture_case_mappings m WHERE m.analysis_id=c.analysis_id AND m.product=? AND m.service_id=?)');args.push(product,service)}
  const from=visibleCases+' WHERE '+filters.join(' AND ');
  const total=Number((await client.query('SELECT COUNT(*) AS n'+from,args)).rows[0].n);
  const items=(await client.query('SELECT a.id,pub.title,a.business_type,c.summary,c.reviewed_at'+from+' ORDER BY c.reviewed_at DESC,c.analysis_id LIMIT 12 OFFSET '+((page-1)*12),args)).rows;
  const patterns=(await client.query(`SELECT m.product,m.service_id,COUNT(*) AS cases_used FROM architecture_case_mappings m
    JOIN architecture_analyses a ON a.id=m.analysis_id JOIN architecture_case_publications pub ON pub.analysis_id=m.analysis_id WHERE a.archived_at IS NULL
    GROUP BY m.product,m.service_id HAVING COUNT(*)>=2 ORDER BY cases_used DESC,m.product,m.service_id LIMIT 24`)).rows;
  return {items,page,total,patterns};
}
