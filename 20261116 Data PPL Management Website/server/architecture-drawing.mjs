import {SaxesParser} from 'saxes';
import {authError} from './auth.mjs';
import {validateImage} from './architecture-model.mjs';
import {readPracticeInput} from './architecture-memory.mjs';
import citations from '../public/practice-citations.js';
import {resultLanguage,resultForDrawing} from './architecture-languages.mjs';
import {LAYERS,SERVICE_CATALOG} from './architecture-catalog.mjs';

const zhLayers=['数据源','数据接入','数据存储','计算处理','数据服务','治理与安全','运维','网络'];
const enLayers=['Sources','Ingestion','Storage','Processing','Serving','Governance & security','Operations','Network'];
const colors=['#edf4fa','#e9f2f6','#eaf0fc','#f1eef9','#faf0ef','#eef3f1','#f1f2f6','#edf2f6'];
const xml=s=>String(s).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;').replace(/\n/g,'&#10;');
const clip=(value,width)=>{
  let size=0,out='';
  for(const c of value){size+=c.codePointAt(0)>255?1.8:1;if(size>width)return out+'…';out+=c}
  return out;
};

export function targetDrawing(target,language,evidence=null) {
  if(!target?.nodes.length)return null;
  const labels=citations.index(evidence);
  const readable=value=>citations.format(value,labels,language).text;
  const layerNames=language==='en'?enLayers:zhLayers;
  const used=LAYERS.filter(layer=>target.nodes.some(n=>n.layer===layer));
  const nodes=new Map(),w=244,h=98,column=322,row=146;
  let maxRow=0;
  for(const [i,layer] of used.entries()){
    const group=target.nodes.filter(n=>n.layer===layer);
    maxRow=Math.max(maxRow,group.length);
    for(const [j,n] of group.entries()){
      const name=SERVICE_CATALOG.find(s=>s.id===n.serviceId).name;
      nodes.set(n.id,{...n,name,role:readable(n.role),caption:layerNames[LAYERS.indexOf(layer)],fill:colors[LAYERS.indexOf(layer)],x:32+i*column,y:54+j*row});
    }
  }
  const width=used.length*column+36,height=maxRow*row+82;
  const vertex=[],edges=[],shapes=[],paths=[];
  for(const n of nodes.values()){
    const label=[n.caption,n.name,n.role].join('\n');
    const style='rounded=1;whiteSpace=wrap;html=0;align=left;verticalAlign=middle;spacing=10;fontFamily=Arial;fontSize=14;fontColor=#273a50;strokeColor=#98adc2;fillColor='+n.fill+';';
    vertex.push(`<mxCell id="n-${xml(n.id)}" value="${xml(label)}" style="${style}" vertex="1" parent="1"><mxGeometry x="${n.x}" y="${n.y}" width="${w}" height="${h}" as="geometry"/></mxCell>`);
    shapes.push(`<g><title>${xml(label)}</title><rect x="${n.x}" y="${n.y}" width="${w}" height="${h}" rx="10" fill="${n.fill}" stroke="#98adc2"/>`+
      [[n.caption,23,13,'#536980'],[clip(n.name,28),51,15,'#243a52'],[clip(n.role,30),77,13,'#435a71']].map(([text,dy,size,fill])=>`<text x="${n.x+12}" y="${n.y+dy}" font-size="${size}" fill="${fill}">${xml(text)}</text>`).join('')+'</g>');
  }
  for(const [i,f] of target.flows.entries()){
    const a=nodes.get(f.from),b=nodes.get(f.to),caption=readable(f.data);
    const start={x:a.x+w,y:a.y+h/2},end={x:b.x,y:b.y+h/2};
    const lane=12+(i%6)*5;
    const pts=b.x===a.x+column?
      [{x:start.x+lane,y:start.y},{x:start.x+lane,y:end.y}]:
      [{x:start.x+lane,y:start.y},{x:start.x+lane,y:18+(i%6)*4},{x:end.x-lane,y:18+(i%6)*4},{x:end.x-lane,y:end.y}];
    const edgeStyle='html=0;rounded=0;endArrow=block;endFill=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;strokeColor=#657e99;fontFamily=Arial;fontSize=12;labelBackgroundColor=#ffffff;';
    edges.push(`<mxCell id="e-${i+1}" value="${xml(caption)}" edge="1" parent="1" source="n-${xml(f.from)}" target="n-${xml(f.to)}" style="${edgeStyle}"><mxGeometry relative="1" as="geometry"><Array as="points">`+pts.map(p=>`<mxPoint x="${p.x}" y="${p.y}"/>`).join('')+'</Array></mxGeometry></mxCell>');
    const poly=[start,...pts,end].map(p=>p.x+','+p.y).join(' ');
    paths.push(`<g><title>${xml(caption)}</title><polyline points="${poly}" fill="none" stroke="#657e99" stroke-width="2" marker-end="url(#arrow)"/></g>`);
  }
  const model=`<mxGraphModel grid="1" gridSize="10" page="0" pageWidth="${width}" pageHeight="${height}"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${vertex.join('')}${edges.join('')}</root></mxGraphModel>`;
  return {
    xml:`<mxfile host="app.diagrams.net" compressed="false"><diagram id="huawei-target" name="${language==='en'?'Huawei Cloud architecture':'华为云目标架构'}">${model}</diagram></mxfile>`,
    svg:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" font-family="Arial, Microsoft YaHei, sans-serif"><defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#657e99"/></marker></defs><rect width="100%" height="100%" fill="#fff"/>${paths.join('')}${shapes.join('')}</svg>`
  };
}

const invalid=()=>authError(400,'请使用单页、可编辑的 draw.io 架构图');
function validateDrawing(value) {
  if(typeof value!=='string'||!value.length||Buffer.byteLength(value)>450000)throw invalid();
  const parser=new SaxesParser(),stack=[];
  let pages=0,graphs=0,cells=0,nodes=0;
  parser.on('doctype',()=>{throw invalid()});
  parser.on('processinginstruction',()=>{throw invalid()});
  parser.on('opentag',tag=>{
    const name=tag.name,parent=stack.at(-1);
    if(!stack.length&&name!=='mxfile'||stack.length>=64||/^(script|iframe|foreignObject|style)$/i.test(name))throw invalid();
    if(name==='diagram'){if(parent!=='mxfile')throw invalid();pages++}
    if(name==='mxGraphModel'){if(parent!=='diagram')throw invalid();graphs++}
    if(name==='mxCell'){if(++cells>4000)throw invalid();if(tag.attributes.vertex==='1')nodes++}
    stack.push(name);
  });
  parser.on('closetag',()=>stack.pop());
  try{parser.write(value).close()}catch{throw invalid()}
  if(pages!==1||graphs!==1||!nodes)throw invalid();
  return value;
}

export async function drawingVersions(c,id) {
  const versions={zh:0,en:0};
  const {rows}=await c.query('SELECT language,version FROM architecture_language_drawings WHERE analysis_id=?',[id]);
  for(const row of rows)versions[row.language]=Number(row.version);
  return versions;
}
export async function drawingRoute(c,request,user,row,operation,url,editorOrigin) {
  if(row.status!=='succeeded')throw authError(404,'暂无可编辑的目标架构');
  const language=resultLanguage(url.searchParams.get('lang'),row.language);
  const result=await resultForDrawing(c,row,language);
  if(!result.target.nodes.length)throw authError(404,'暂无可编辑的目标架构');
  if(request.method==='GET'){
    const generate=async()=>{
      const target=result.target;
      const hasRefs=target.nodes.some(n=>/L[1-9]/.test(n.role))||target.flows.some(f=>/L[1-9]/.test(f.data));
      const evidence=hasRefs?(await readPracticeInput(c,row.id)).evidence:null;
      return targetDrawing(target,language,evidence);
    };
    if(operation==='drawing/preview'){
      const saved=(await c.query('SELECT preview_png FROM architecture_language_drawings WHERE analysis_id=? AND language=?',[row.id,language])).rows[0];
      const payload=saved?saved.preview_png:(await generate()).svg;
      return new Response(payload,{headers:{'Content-Type':saved?'image/png':'image/svg+xml','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'}});
    }
    const saved=(await c.query('SELECT diagram_xml,version FROM architecture_language_drawings WHERE analysis_id=? AND language=?',[row.id,language])).rows[0];
    const body={language,xml:saved?.diagram_xml||(await generate()).xml,version:saved?.version||0,editorOrigin};
    if(url.searchParams.get('download')==='1')return new Response(body.xml,{headers:{'Content-Type':'application/octet-stream','Content-Disposition':'attachment; filename="huawei-cloud-'+row.id+'-'+language+'.drawio"','Cache-Control':'private, no-store'}});
    return Response.json(body);
  }
  if(request.method!=='POST'||operation!=='drawing')throw authError(405,'请使用 POST');
  if(!row.canMaintain)throw authError(403,'当前账号仅可查看此分析');
  const b=await request.json();
  if(b.language!=null && b.language!==language)throw authError(409,'图纸语言已改变，请重新打开编辑器');
  const diagram=validateDrawing(b.xml),preview=validateImage(b.preview,'image/png');
  const lock=(await c.query('SELECT archived_at FROM architecture_analyses WHERE id=? FOR UPDATE',[row.id])).rows[0];
  if(lock.archived_at)throw authError(409,'请先恢复归档记录');
  const version=(await drawingVersions(c,row.id))[language];
  if(b.version!==version)throw authError(409,'目标架构图已被更新，请重新打开');
  if(version)await c.query('UPDATE architecture_language_drawings SET diagram_xml=?,preview_png=?,version=version+1,updated_by=?,updated_at=now() WHERE analysis_id=? AND language=?',[diagram,preview,user.email,row.id,language]);
  else await c.query('INSERT INTO architecture_language_drawings(analysis_id,language,diagram_xml,preview_png,updated_by) VALUES(?,?,?,?,?)',[row.id,language,diagram,preview,user.email]);
  return Response.json({version:version+1,language});
}
