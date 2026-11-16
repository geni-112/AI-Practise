import {inflateRawSync,deflateRawSync} from 'node:zlib';
export {monthlyTemplateModel,monthlyTemplateWorkbook,monthlyTemplatePreview,templateUnzip};

function reportRevenue(project,period,prior=false){
 const year=Number(period.slice(0,4))-(prior?1:0),end=String(year)+period.slice(4);
 const rows=(project.actuals||[]).filter(a=>a.month.startsWith(String(year)+'-')&&a.month<=end);
 return rows.length?rows.reduce((sum,a)=>sum+a.amount,0):null;
}
function enrichReportRevenue(snapshot,projects){
 const selected=new Map(projects.map(p=>[p.id,p]));
 for(const p of snapshot.projects){const source=selected.get(p.id);if(!source)continue;p.ytdActual=reportRevenue(source,snapshot.period);p.priorYtdActual=reportRevenue(source,snapshot.period,true);p.risk=source.risk;p.pipelineDate=source.pipelineDate;}
 for(const group of snapshot.groups){
  const members=snapshot.projects.filter(p=>(p.repo||'未填写')===group.repo),sum=key=>{const values=members.map(p=>p[key]).filter(v=>v!==null&&v!==undefined);return values.length?values.reduce((a,b)=>a+b,0):null};
  group.ytdActual=sum('ytdActual');group.priorYtdActual=sum('priorYtdActual');group.yoy=group.ytdActual!==null&&group.priorYtdActual!==null&&group.priorYtdActual!==0?group.ytdActual/group.priorYtdActual-1:null;
  group.newYtd=members.filter(p=>p.pipelineDate?.startsWith(snapshot.period.slice(0,4)+'-')&&p.pipelineDate.slice(0,7)<=snapshot.period).length;
 }
 return snapshot;
}
function reportTemplateEdits(body,report){
 if(body.summary!==undefined&&(typeof body.summary!=='string'||body.summary.length>20000))fail(400,'月报总述格式无效');
 if(body.support!==undefined&&(!Array.isArray(body.support)||body.support.length>5||body.support.some(v=>typeof v!=='string'||v.length>2000)))fail(400,'支撑阵型最多填写五行，每行不超过 2000 字');
 if(body.contact!==undefined&&(typeof body.contact!=='string'||body.contact.length>500))fail(400,'联系人格式无效');
 report.summaryGenerated=body.summaryGenerated===true||!body.summary;
 if(!report.summaryGenerated)report.summary=body.summary;
 report.support=body.support||[];report.contact=body.contact||'';
}
async function reportTemplateResponse(db,user,body){
 requireP(user,'report.view');if(body.format==='xlsx')requireP(user,'report.export');
 if(!['html','xlsx'].includes(body.format))fail(400,'报表格式无效');
 let report;
 if(body.id&&body.id!=='current'){report=await get(db,String(body.id),'report');if(!report)fail(404,'报表不存在');}
 else{
  if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(body.period||''))fail(400,'请选择月份');
  report=buildReport(reportProjects(user,await all(db,'project')),body.period,body.type||'全部',body.repo||'全部');
  if(!has(user,'report.generate')){report.projects=[];report.updates=[];}
  if(has(user,'report.archive')&&has(user,'finance.read'))reportTemplateEdits(body,report);
 }
 const visible=reportForUser(user,report),dicts=report.dictionarySnapshot||await dictionaries(db),model=monthlyTemplateModel(visible,dicts,body.language);
 if(body.format==='html')return j({...monthlyTemplatePreview(model),summary:model.values.A3});
 return new Response(monthlyTemplateWorkbook(model),{headers:{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','Content-Disposition':`attachment; filename="Data-PPL-${report.period}.xlsx"`,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
}

const templateEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
function templateUnzip(bytes){
 const entries=[];let end=bytes.length-22;while(end>=0&&bytes.readUInt32LE(end)!==0x06054b50)end--;
 if(end<0)throw Error('Invalid report template');
 let offset=bytes.readUInt32LE(end+16),count=bytes.readUInt16LE(end+10);
 for(let i=0;i<count;i++){
  if(bytes.readUInt32LE(offset)!==0x02014b50)throw Error('Invalid template directory');
  const method=bytes.readUInt16LE(offset+10),size=bytes.readUInt32LE(offset+20),nameLength=bytes.readUInt16LE(offset+28),extraLength=bytes.readUInt16LE(offset+30),commentLength=bytes.readUInt16LE(offset+32),local=bytes.readUInt32LE(offset+42);
  const name=bytes.subarray(offset+46,offset+46+nameLength).toString('utf8'),start=local+30+bytes.readUInt16LE(local+26)+bytes.readUInt16LE(local+28),compressed=bytes.subarray(start,start+size);
  entries.push({name,data:method===8?inflateRawSync(compressed):compressed});offset+=46+nameLength+extraLength+commentLength;
 }
 return entries;
}
function templateCrc(bytes){let crc=0xffffffff;for(const byte of bytes){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^(crc&1?0xedb88320:0)}return(crc^0xffffffff)>>>0}
function templateZip(entries){
 const bodies=[],central=[];let offset=0;
 for(const entry of entries){const name=Buffer.from(entry.name),raw=Buffer.from(entry.data),body=deflateRawSync(raw),crc=templateCrc(raw),header=Buffer.alloc(30+name.length),directory=Buffer.alloc(46+name.length);
  header.writeUInt32LE(0x04034b50);header.writeUInt16LE(20,4);header.writeUInt16LE(0x800,6);header.writeUInt16LE(8,8);header.writeUInt16LE(33,12);header.writeUInt32LE(crc,14);header.writeUInt32LE(body.length,18);header.writeUInt32LE(raw.length,22);header.writeUInt16LE(name.length,26);name.copy(header,30);
  directory.writeUInt32LE(0x02014b50);directory.writeUInt16LE(20,4);directory.writeUInt16LE(20,6);directory.writeUInt16LE(0x800,8);directory.writeUInt16LE(8,10);directory.writeUInt16LE(33,14);directory.writeUInt32LE(crc,16);directory.writeUInt32LE(body.length,20);directory.writeUInt32LE(raw.length,24);directory.writeUInt16LE(name.length,28);directory.writeUInt32LE(offset,42);name.copy(directory,46);
  bodies.push(header,body);central.push(directory);offset+=header.length+body.length;
 }
 const end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50);end.writeUInt16LE(entries.length,8);end.writeUInt16LE(entries.length,10);end.writeUInt32LE(central.reduce((sum,b)=>sum+b.length,0),12);end.writeUInt32LE(offset,16);return Buffer.concat([...bodies,...central,end]);
}
const templateCol=ref=>[...ref.match(/^[A-Z]+/)[0]].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0);
const templateRow=ref=>Number(ref.match(/\d+$/)[0]);
function templateRef(col,row){let result='';for(;col;col=Math.floor((col-1)/26))result=String.fromCharCode(65+(col-1)%26)+result;return result+row}
function templateLabel(dicts,field,value,lang){const item=dicts.find(d=>d.field===field)?.items.find(i=>i.value===String(value));return item?(lang==='en'?(item.en||item.zh):item.zh):String(value??'')}
function templateMoney(value,lang){return value===null||value===undefined?'—':Number(value).toLocaleString(lang==='en'?'en-US':'zh-CN',{maximumFractionDigits:3})}
function templateLines(text,width,fontSize){let lines=0;for(const line of String(text??'').split('\n')){const units=[...line].reduce((n,c)=>n+(/[^\u0000-\u00ff]/.test(c)?1:0.55),0);lines+=Math.max(1,Math.ceil(units*fontSize/(Math.max(40,width)-8)))}return lines}
function monthlyTemplateModel(report,dicts,language='zh'){
 const lang=language==='en'?'en':'zh',en=lang==='en',year=Number(report.period.slice(0,4)),month=Number(report.period.slice(5)),label=(field,value)=>templateLabel(dicts,field,value,lang);
 const category=report.type==='全部'?(en?'Data':'数据'):label('type',report.type),projects=report.projects||[],extra=Math.max(0,projects.length-18),rows={},cells=[],values={};
 for(const [key,height]of Object.entries(REPORT_LAYOUT.rows))rows[Number(key)>=38?Number(key)+extra:key]=height;
 for(let i=0;i<extra;i++)rows[38+i]=REPORT_LAYOUT.rows['37'];
 const shiftRef=ref=>templateRef(templateCol(ref),templateRow(ref)>=38?templateRow(ref)+extra:templateRow(ref));
 for(const cell of REPORT_LAYOUT.cells)cells.push({...cell,ref:shiftRef(cell.ref)});
 for(let i=0;i<extra;i++)for(const cell of REPORT_LAYOUT.cells.filter(c=>templateRow(c.ref)===37))cells.push({...cell,ref:templateRef(templateCol(cell.ref),38+i),value:''});
 const merges=REPORT_LAYOUT.merges.map(range=>range.split(':').map(shiftRef).join(':'));
 for(let i=0;i<extra;i++)merges.push(`F${38+i}:J${38+i}`,`K${38+i}:L${38+i}`);
 const s=report.stats,missing=en?'Not recorded':'待补齐',money=value=>templateMoney(value,lang);
 values.A1=en?`LATAM Cloud ${category} Monthly Report · ${report.period}`:`拉美云${category}专项拓展月报-${String(year).slice(-2)}年${month}月`;
 values.A2=en?'1. Business summary':'一、业务总述';values.A5=en?`2. New opportunities in ${year}`:`二、${String(year).slice(-2)}年新机会点拓展情况`;
 const defaultSummary=en?
  `1. Revenue: recorded YTD revenue ${report.financeHidden?'Not authorized':money(s.ytdActual)} M USD. Year-on-year: ${s.yoy==null?missing:(s.yoy*100).toFixed(1)+'%'}.\n\n2. Opportunities and key projects: ${s.projects} opportunities across ${s.customers} customers; ${s.newProjects} new this month. ${s.poc} are in POC preparation or validation. ${s.blocked} are on hold or blocked.\n\n3. Progress: ${s.updates} updates recorded this month. Recorded monthly revenue: ${report.financeHidden?'Not authorized':money(s.monthlyActual)} M USD. Missing revenue is not zero.`:
  `1. 收入完成情况：截至${month}月，年内已录入实际收入${report.financeHidden?'未授权':money(s.ytdActual)} M USD，同比${s.yoy==null?'待补齐同期数据':(s.yoy*100).toFixed(1)+'%'}。\n\n2. 机会点及重点项目进展：台账共${s.projects}个机会点、${s.customers}个客户，本月新增入管道${s.newProjects}个。当前 POC 准备及验证项目${s.poc}个，挂起或阻塞项目${s.blocked}个。\n\n3. 本月推进：共记录${s.updates}条更新；本月已录入实际收入${report.financeHidden?'未授权':money(s.monthlyActual)} M USD。收入仅统计已录入部分，未填不视为零。`;
 values.A3=report.summaryGenerated?defaultSummary:(report.summary||defaultSummary);
 values.E19=en?`${year} Jan–${month} revenue (M USD)`:`${String(year).slice(-2)}年1-${month}月收入（M USD）`;
 const headers=en?['Office','Project','Current vendor','Use case',values.E19,'Executive alignment','Technical discussion','Solution design','POC','Contract / revenue','Progress']:['代表处','项目','现网厂家','业务场景',values.E19,'高层对标','技术交流','方案设计','PoC','合同签订及收入','进展'];headers.forEach((text,i)=>values[templateRef(i+1,19)]=text);
 rows[19]=Math.max(rows[19],...headers.map((text,i)=>templateLines(text,REPORT_LAYOUT.columns[i],16)*20+6));
 for(let index=0;index<Math.max(18,projects.length);index++){
  const row=20+index,p=projects[index];for(let col=1;col<=12;col++)values[templateRef(col,row)]='';if(!p)continue;
  const progress=p.next||p.weekly||p.notes||'';const rowValues={A:label('repo',p.repo),B:p.name,C:label('vendor',p.vendor),D:p.scenario||'',E:report.financeHidden?'':p.ytdActual??'',K:progress};for(const [col,value]of Object.entries(rowValues))values[col+row]=value;
  rows[row]=Math.max(rows[row]||34,...Object.entries(rowValues).filter(([col])=>col!=='E').map(([col,value])=>templateLines(value,col==='K'?REPORT_LAYOUT.columns[10]+REPORT_LAYOUT.columns[11]:REPORT_LAYOUT.columns[templateCol(col)-1],14)*19+8));
 }
 rows[3]=Math.max(rows[3],templateLines(values.A3,REPORT_LAYOUT.width,16)*22+28);
 values['A'+(39+extra)]=en?'4. Support team':'四、支撑阵型';
 const supportLabels=en?['Overseas product PE','LATAM product contact','Overseas service support','Regional support center']:['产品海外PE','拉美产品接口人','营销服海外支持','地区部支撑中心'];supportLabels.forEach((v,i)=>values['B'+(40+extra+i)]=v);
 for(let i=0;i<5;i++){const row=40+extra+i;values['C'+row]=(report.support||[])[i]||'';rows[row]=Math.max(rows[row],templateLines(values['C'+row],REPORT_LAYOUT.width-REPORT_LAYOUT.columns[0]-REPORT_LAYOUT.columns[1],16)*21+6)}
 values['A'+(45+extra)]=report.contact||(en?'For questions, contact the platform administrator.':'* 如有疑问，请联系平台管理员。');
 const groups=(report.groups||[]).map(g=>({...g,label:g.repoMissing?(en?'Not recorded':'未填写'):label('repo',g.repo)}));
 const list=items=>items.length?items.slice(0,5).map(p=>{const text=`${label('repo',p.repo)} ${p.name}`;return text.length>28?text.slice(0,27)+'…':text}).join('\n')+(items.length>5?`\n${en?'More in table:':'其余见明细：'}${items.length-5}`:''):(en?'No projects':'暂无项目');
 const captions={10:en?`Pipeline development · ${projects.filter(p=>p.stage<3).length} projects`:`管道拓展中 · ${projects.filter(p=>p.stage<3).length} 个项目`,11:en?`POC / commercial · ${projects.filter(p=>p.stage>=3&&p.stage<6).length} projects`:`POC 与商务推进 · ${projects.filter(p=>p.stage>=3&&p.stage<6).length} 个项目`,12:en?`Signed / delivery · ${projects.filter(p=>p.stage>=6).length} projects`:`签约与交付 · ${projects.filter(p=>p.stage>=6).length} 个项目`,53:list(projects.filter(p=>p.stage<=1)),55:list(projects.filter(p=>p.stage===2||p.stage===5)),50:list(projects.filter(p=>[3,4].includes(p.stage))),45:list(projects.filter(p=>p.stage===6)),44:report.financeHidden?(en?'Not authorized':'未授权'):list(projects.filter(p=>(p.ytdActual??0)>0))};
 if(en)Object.assign(captions,{19:'Executive alignment',20:'Technical discussion',21:'Solution design',22:'POC',23:'Contract signing',24:'Revenue'});
 const chartTitles={revenue:en?`Jan–${month} ${category} revenue and year-on-year by office`:`1-${month}月 各代表处${category}收入及同比情况`,opportunities:en?`Jan–${month} ${category} opportunities by office`:`1-${month}月${category}机会点数量情况`};
 return {report,lang,en,year,month,category,projects,extra,rows,cells,merges,values,groups,captions,chartTitles,width:REPORT_LAYOUT.width,height:Object.values(rows).reduce((a,b)=>a+b,0)};
}
function templateCellXml(ref,value,style){
 const attrs=`r="${ref}"${style===undefined?'':` s="${style}"`}`;
 if(value===null||value===undefined||value==='')return `<c ${attrs}/>`;
 if(typeof value==='number')return `<c ${attrs}><v>${Number(value.toFixed(6))}</v></c>`;
 if(ref==='A3')return `<c ${attrs} t="inlineStr"><is><r><rPr><sz val="12"/><rFont val="微软雅黑"/></rPr><t xml:space="preserve">${templateEscape(value)}</t></r></is></c>`;
 return `<c ${attrs} t="inlineStr"><is><t xml:space="preserve">${templateEscape(value)}</t></is></c>`;
}
function templateChartScale(model,kind){
 const values=model.groups.flatMap(g=>kind==='revenue'?[g.priorYtdActual,g.ytdActual]:[g.newYtd??g.count]).filter(v=>v!==null&&v!==undefined),largest=Math.max(0,...values);
 const step=kind==='opportunities'?Math.max(1,Math.ceil(largest/4)):Math.max(0.001,Math.pow(10,Math.floor(Math.log10(Math.max(largest,0.01)/4)))*Math.ceil(Math.max(largest,0.01)/4/Math.pow(10,Math.floor(Math.log10(Math.max(largest,0.01)/4)))));
 const growth=model.groups.map(g=>g.yoy).filter(v=>v!==null&&v!==undefined),low=Math.min(0,...growth),high=Math.max(0,...growth);
 return {max:step*4,yoyMin:Math.floor(low*1.1*5)/5,yoyMax:Math.max(0.2,Math.ceil(high*1.1*5)/5)};
}
function templateChartXml(xml,model,kind){
 xml=xml.replace(/<c:extLst>[\s\S]*?<\/c:extLst>/g,''); // Remove obsolete source-workbook chart filters and broken external formula references.
 const groups=model.groups,rows=groups.length||1,last=rows+1,cats=groups.length?groups.map(g=>g.label):[model.en?'No data':'暂无数据'];
 const cache=(name,values)=>`<c:${name}>${name==='numCache'?'<c:formatCode>General</c:formatCode>':''}<c:ptCount val="${values.length}"/>${values.map((v,i)=>v===null||v===undefined||v===''?'':`<c:pt idx="${i}"><c:v>${templateEscape(v)}</c:v></c:pt>`).join('')}</c:${name}>`;
 const reference=(col,values,strings=false)=>`<c:${strings?'strRef':'numRef'}><c:f>_MonthlyData!$${col}$2:$${col}$${last}</c:f>${cache(strings?'strCache':'numCache',values)}</c:${strings?'strRef':'numRef'}>`;
 let seriesIndex=0;
 xml=xml.replace(/<c:title>[\s\S]*?<\/c:title>/,title=>{let first=true;return title.replace(/<a:t>[\s\S]*?<\/a:t>/g,()=>`<a:t>${first?(first=false,templateEscape(model.chartTitles[kind])):''}</a:t>`)});
 xml=xml.replace(/<c:ser>[\s\S]*?<\/c:ser>/g,series=>{
  const index=seriesIndex++,col=kind==='opportunities'?'E':['B','C','D'][index];
  const values=kind==='opportunities'?(groups.length?groups.map(g=>g.newYtd??g.count):[0]):groups.length?groups.map(g=>model.report.financeHidden?null:index===0?g.priorYtdActual:index===1?g.ytdActual:g.yoy):[null];
  series=series.replace(/<c:cat>[\s\S]*?<\/c:cat>/,`<c:cat>${reference('A',cats,true)}</c:cat>`).replace(/<c:val>[\s\S]*?<\/c:val>/,`<c:val>${reference(col,values)}</c:val>`);
  if(!series.includes('<c:cat>'))series=series.replace('<c:val>',`<c:cat>${reference('A',cats,true)}</c:cat><c:val>`);
  if(kind==='revenue'){const title=index===0?`${model.year-1} 1-${model.month}`:index===1?`${model.year} 1-${model.month}`:(model.en?'Year-on-year':'同比增长');series=series.replace(/<c:tx>[\s\S]*?<\/c:tx>/,`<c:tx><c:strRef><c:f>_MonthlyData!$${col}$1</c:f>${cache('strCache',[title])}</c:strRef></c:tx>`)}
  return series;
 });
 const scale=templateChartScale(model,kind);
 xml=xml.replace(/<c:valAx>[\s\S]*?<\/c:valAx>/g,axis=>{
  const right=axis.includes('<c:axPos val="r"'),min=right?scale.yoyMin:0,max=right?scale.yoyMax:scale.max;
  axis=axis.replace(/<c:(?:min|max)\b[^>]*\/>/g,'').replace('</c:scaling>',`<c:max val="${max}"/><c:min val="${min}"/></c:scaling>`);
  if(right)axis=axis.replace(/<c:numFmt\b[^>]*\/>/,'<c:numFmt formatCode="0%" sourceLinked="0"/>');
  return axis;
 });
 if(kind==='opportunities')xml=xml.replace(/<c:varyColors\b[^>]*\/>/g,'<c:varyColors val="0"/>').replace(/<c:ser>[\s\S]*?<\/c:ser>/g,series=>{
  series=series.replace(/<c:dPt>[\s\S]*?<\/c:dPt>/g,'');
  const fill='<c:spPr><a:solidFill><a:srgbClr val="FFC000"/></a:solidFill><a:ln><a:noFill/></a:ln></c:spPr>';
  return series.includes('<c:spPr>')?series.replace(/<c:spPr>[\s\S]*?<\/c:spPr>/,fill):series.replace(/(<c:order\b[^>]*\/>)/,'$1'+fill);
 });
 return xml;
}
function templateDrawingXml(xml,model){
 xml=xml.replace(/<xdr:(twoCellAnchor|oneCellAnchor)\b[^>]*>[\s\S]*?<\/xdr:\1>/g,anchor=>{
  const id=anchor.match(/<xdr:cNvPr\b[^>]*\bid="(\d+)"/)?.[1];if(!Object.hasOwn(model.captions,id))return anchor;
  const text=model.captions[id],body=anchor.match(/<xdr:txBody>([\s\S]*?)<\/xdr:txBody>/)?.[1];if(!body)return anchor;
  const properties=body.match(/<a:rPr\b[^>]*(?:\/>|>[\s\S]*?<\/a:rPr>)/)?.[0]||'<a:rPr lang="zh-CN" sz="1200"/>';
  const paragraph=body.match(/<a:pPr\b[^>]*(?:\/>|>[\s\S]*?<\/a:pPr>)/)?.[0]||'';
  const paragraphs=text.split('\n').map(line=>`<a:p>${paragraph}<a:r>${properties}<a:t>${templateEscape(line)}</a:t></a:r></a:p>`).join('');
  return anchor.replace(/<xdr:txBody>[\s\S]*?<\/xdr:txBody>/,`<xdr:txBody>${body.replace(/<a:p>[\s\S]*?<\/a:p>/g,'')}${paragraphs}</xdr:txBody>`);
 });
 const pictures=model.projects.map((p,index)=>{const proto=REPORT_LAYOUT.pictures[p.risk?'red':'blue'],phase=p.stage<=1?5:p.stage===2?6:[3,4].includes(p.stage)?8:p.stage===5?8:9;let raw=proto.xml,id=1000+index;
  raw=raw.replace(/(<xdr:cNvPr\b[^>]*\bid=")\d+/,(_,prefix)=>prefix+id).replace(/(<xdr:cNvPr\b[^>]*\bname=")[^"]+/,(_,prefix)=>prefix+`Project ${index+1}`);
  raw=raw.replace(/<xdr:from>[\s\S]*?<\/xdr:from>/,`<xdr:from><xdr:col>${phase}</xdr:col><xdr:colOff>450000</xdr:colOff><xdr:row>${19+index}</xdr:row><xdr:rowOff>40000</xdr:rowOff></xdr:from>`);
  raw=raw.replace(/<xdr:to>[\s\S]*?<\/xdr:to>/,`<xdr:to><xdr:col>${phase}</xdr:col><xdr:colOff>${450000+Math.round(proto.width*9525)}</xdr:colOff><xdr:row>${19+index}</xdr:row><xdr:rowOff>${40000+Math.round(proto.height*9525)}</xdr:rowOff></xdr:to>`);return raw;
 }).join('');return xml.replace('</xdr:wsDr>',pictures+'</xdr:wsDr>');
}
function monthlyTemplateWorkbook(model){
 const entries=templateUnzip(Buffer.from(REPORT_XLSX,'base64')),get=name=>entries.find(e=>e.name===name),set=(name,text)=>get(name).data=Buffer.from(text);
 let sheet=get('xl/worksheets/sheet1.xml').data.toString();
 const rowTemplates=new Map([...sheet.matchAll(/<row\b[^>]*\br="(\d+)"[^>]*>[\s\S]*?<\/row>/g)].map(m=>[Number(m[1]),m[0]]));
 let sheetData='';
 for(let row=1;row<=45+model.extra;row++){
  const source=row>=38+model.extra?row-model.extra:row>=38?37:row;
  let raw=rowTemplates.get(source);if(!raw)continue;
  raw=raw.replace(/\br="\d+"/,`r="${row}"`).replace(/\bht="[^"]*"/,`ht="${model.rows[row]*0.75}"`);if(!/\bht=/.test(raw))raw=raw.replace('<row ',`<row ht="${model.rows[row]*0.75}" customHeight="1" `);
  raw=raw.replace(/<c\b[^>]*\/>|<c\b[^>]*>[\s\S]*?<\/c>/g,cell=>{const old=cell.match(/\br="([A-Z]+)\d+"/)[1],ref=old+row,style=cell.match(/\bs="(\d+)"/)?.[1],value=Object.hasOwn(model.values,ref)?model.values[ref]:model.cells.find(c=>c.ref===ref)?.value;return templateCellXml(ref,value,style)});sheetData+=raw;
 }
 sheet=sheet.replace(/<sheetData>[\s\S]*?<\/sheetData>/,`<sheetData>${sheetData}</sheetData>`).replace(/<mergeCells\b[^>]*>[\s\S]*?<\/mergeCells>/,`<mergeCells count="${model.merges.length}">${model.merges.map(ref=>`<mergeCell ref="${ref}"/>`).join('')}</mergeCells>`).replace(/<dimension ref="[^"]+"\/>/,`<dimension ref="A1:L${45+model.extra}"/>`);set('xl/worksheets/sheet1.xml',sheet);
 set('xl/drawings/drawing1.xml',templateDrawingXml(get('xl/drawings/drawing1.xml').data.toString(),model));
 set('xl/charts/chart1.xml',templateChartXml(get('xl/charts/chart1.xml').data.toString(),model,'opportunities'));set('xl/charts/chart2.xml',templateChartXml(get('xl/charts/chart2.xml').data.toString(),model,'revenue'));
 const rows=[['Office',`${model.year-1} 1-${model.month}`,`${model.year} 1-${model.month}`,'YoY','Opportunities'],...(model.groups.length?model.groups.map(g=>[g.label,model.report.financeHidden?'':g.priorYtdActual??'',model.report.financeHidden?'':g.ytdActual??'',model.report.financeHidden?'':g.yoy??'',g.newYtd??g.count]):[[model.en?'No data':'暂无数据','','','',0]])];
 const source=rows.map((values,i)=>`<row r="${i+1}">${values.map((value,j)=>{const ref=templateRef(j+1,i+1);if(i>0&&j===3)return `<c r="${ref}" t="${value===''?'str':'n'}"><f>IF(OR(B${i+1}=&quot;&quot;,C${i+1}=&quot;&quot;,B${i+1}=0),&quot;&quot;,C${i+1}/B${i+1}-1)</f><v>${value}</v></c>`;return templateCellXml(ref,value)}).join('')}</row>`).join('');set('xl/worksheets/sheet2.xml',`<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${source}</sheetData></worksheet>`);
 return templateZip(entries);
}
function templateChartHtml(model,kind,width,height){
 const groups=model.groups,margin={left:55,right:kind==='revenue'?58:30,top:42,bottom:70},w=width-margin.left-margin.right,h=height-margin.top-margin.bottom,plot=groups.length?groups:[{label:model.en?'No data':'暂无数据',count:0,newYtd:0}];
 const money=kind==='revenue',numbers=plot.flatMap(g=>money?[g.priorYtdActual,g.ytdActual]:[g.newYtd??g.count]).filter(v=>v!==null&&v!==undefined),scale=templateChartScale(model,kind),max=scale.max;
 let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect x="0.5" y="0.5" width="${width-1}" height="${height-1}" fill="white" stroke="#d9d9d9"/><g font-family="Microsoft YaHei,Arial,sans-serif" fill="#222"><text x="${width/2}" y="23" text-anchor="middle" font-size="18" font-weight="bold">${templateEscape(model.chartTitles[kind])}</text>`;
 for(let i=0;i<=4;i++){const y=margin.top+h-i*h/4;svg+=`<line x1="${margin.left}" y1="${y}" x2="${width-margin.right}" y2="${y}" stroke="#ddd"/><text x="${margin.left-10}" y="${y+5}" text-anchor="end" font-size="13">${Number((max*i/4).toFixed(3))}</text>`}
 const step=w/plot.length;plot.forEach((g,index)=>{const x=margin.left+step*(index+0.5),values=money?[g.priorYtdActual,g.ytdActual]:[g.newYtd??g.count];values.forEach((value,j)=>{if(value===null||value===undefined||model.report.financeHidden&&money)return;const bw=Math.min(45,step/(money?3:1.5)),bh=value/max*h,xx=x+(money?(j===0?-bw:0):-bw/2);svg+=`<rect x="${xx}" y="${margin.top+h-bh}" width="${bw}" height="${bh}" fill="${money?(j===0?'#4f81bd':'#c0504d'):'#ffc000'}"/>`;if(!money)svg+=`<text x="${x}" y="${margin.top+h-bh-7}" text-anchor="middle" font-size="13">${value}</text>`});svg+=`<text x="${x}" y="${margin.top+h+23}" text-anchor="middle" font-size="13">${templateEscape(g.label.slice(0,14))}</text>`});
 if(money){
  const growth=plot.map((g,i)=>g.yoy==null?null:[margin.left+step*(i+0.5),margin.top+h-(g.yoy-scale.yoyMin)/(scale.yoyMax-scale.yoyMin)*h]);
  growth.forEach((point,i)=>{if(point&&i&&growth[i-1])svg+=`<line x1="${growth[i-1][0]}" y1="${growth[i-1][1]}" x2="${point[0]}" y2="${point[1]}" stroke="#c00000" stroke-width="2"/>`});
  for(let i=0;i<=4;i++)svg+=`<text x="${width-margin.right+8}" y="${margin.top+h-i*h/4+5}" font-size="12">${Math.round((scale.yoyMin+(scale.yoyMax-scale.yoyMin)*i/4)*100)}%</text>`;
  svg+=`<text x="${width/2}" y="${height-14}" text-anchor="middle" font-size="13"><tspan fill="#4f81bd">■ ${model.year-1}</tspan><tspan fill="#c0504d">　■ ${model.year}</tspan><tspan fill="#c00000">　— ${model.en?'YoY':'同比增长'}</tspan></text>`;
 }
 if(!numbers.length||model.report.financeHidden&&money)svg+=`<text x="${width/2}" y="${height/2}" text-anchor="middle" font-size="16" fill="#6b7280">${model.report.financeHidden?(model.en?'Not authorized':'未授权'):(model.en?'No recorded revenue':'暂无已录入收入')}</text>`;
 return svg+'</g></svg>';
}
function monthlyTemplatePreview(model){
 const left=col=>REPORT_LAYOUT.columns.slice(0,col-1).reduce((a,b)=>a+b,0),top=row=>Object.entries(model.rows).filter(([r])=>+r<row).reduce((sum,[,v])=>sum+v,0),cellMap=new Map(model.cells.map(c=>[c.ref,c])),covered=new Set(),merges=new Map();
 for(const range of model.merges){const [first,last]=range.split(':'),c1=templateCol(first),c2=templateCol(last),r1=templateRow(first),r2=templateRow(last);merges.set(first,{c1,c2,r1,r2});for(let row=r1;row<=r2;row++)for(let col=c1;col<=c2;col++)if(templateRef(col,row)!==first)covered.add(templateRef(col,row))}
 let content='';
 for(const cell of model.cells){if(covered.has(cell.ref))continue;const col=templateCol(cell.ref),row=templateRow(cell.ref),merge=merges.get(cell.ref)||{c1:col,c2:col,r1:row,r2:row},style=REPORT_LAYOUT.styles[cell.style],width=left(merge.c2+1)-left(col),height=top(merge.r2+1)-top(row),value=Object.hasOwn(model.values,cell.ref)?model.values[cell.ref]:cell.value;
  const border={...style.borders};for(const [edge,ref]of [['right',templateRef(merge.c2,row)],['bottom',templateRef(col,merge.r2)]]){const s=REPORT_LAYOUT.styles[cellMap.get(ref)?.style];if(s?.borders[edge])border[edge]=s.borders[edge]}
  let css=`left:${left(col)}px;top:${top(row)}px;width:${width}px;height:${height}px;background:${style.fill};font-family:'${style.font}','Microsoft YaHei',Arial,sans-serif;font-size:${cell.ref==='A3'?12:style.size}pt;font-weight:${style.bold?'bold':'normal'};font-style:${style.italic?'italic':'normal'};color:${style.color};text-align:${style.align==='general'?'left':style.align};align-items:${style.vertical==='center'?'center':style.vertical==='top'?'flex-start':'flex-end'};`;
  for(const [edge,b]of Object.entries(border))css+=`border-${edge}:${['medium','thick'].includes(b.style)?2:1}px solid ${b.color};`;
  content+=`<div class="cell" style="${css}"><div style="width:100%;white-space:${style.wrap||cell.ref==='A3'?'pre-wrap':'pre'}">${typeof value==='number'?templateMoney(value,model.lang):templateEscape(value)}</div></div>`;
 }
 for(const shape of REPORT_LAYOUT.shapes){
  const y=top(shape.row+1)+(shape.y-Object.entries(REPORT_LAYOUT.rows).filter(([r])=>+r<shape.row+1).reduce((sum,[,v])=>sum+v,0)),text=Object.hasOwn(model.captions,shape.id)?model.captions[shape.id]:shape.text;
  const position=`left:${shape.x}px;top:${y}px;width:${shape.width}px;height:${shape.height}px;`;
  if(shape.chart){content+=`<div class="drawing" style="${position}">${templateChartHtml(model,shape.chart,shape.width,shape.height)}</div>`;continue}
  if(shape.kind==='cxnSp'){content+=`<div class="drawing" style="left:${shape.x}px;top:${y}px;width:${shape.width}px;border-top:4px solid #bfbfbf"></div>`;continue}
  if(shape.geometry==='ellipse'){content+=`<div class="drawing" style="${position}background:#d9d9d9;border-radius:50%"></div>`;continue}
  const arrow=shape.geometry==='homePlate'&&Number(shape.id)<19;
  content+=`<div class="drawing text-shape" style="${position}font-size:${shape.fontSize}pt;font-weight:${shape.bold?'bold':'normal'};justify-content:${shape.anchor==='ctr'?'center':'flex-start'};text-align:${shape.align==='ctr'?'center':'left'};${arrow?'border:1px solid #e5e7eb;clip-path:polygon(0 0,93% 0,100% 50%,93% 100%,0 100%);':''}">${templateEscape(text)}</div>`;
 }
 model.projects.forEach((p,index)=>{const proto=REPORT_LAYOUT.pictures[p.risk?'red':'blue'],col=p.stage<=1?6:p.stage===2?7:[3,4].includes(p.stage)?9:p.stage===5?9:10;content+=`<img alt="" class="drawing" src="${proto.image}" style="left:${left(col)+47.24}px;top:${top(20+index)+4.2}px;width:${proto.width}px;height:${proto.height}px">`});
 const html=`<!doctype html><html lang="${model.en?'en':'zh-CN'}"><head><meta charset="UTF-8"><title>${templateEscape(model.values.A1)}</title><style>*{box-sizing:border-box}body{margin:0;background:#fff}.sheet{position:relative;background:#fff;width:${model.width}px;height:${model.height}px}.cell{position:absolute;display:flex;padding:1px 3px;overflow:hidden;line-height:1.2}.drawing{position:absolute}.text-shape{font-family:'Microsoft YaHei',Arial,sans-serif;display:flex;flex-direction:column;white-space:pre-wrap;line-height:1.25;padding:8px 10px;overflow:hidden}@media print{@page{size:A3 landscape;margin:8mm}body{zoom:0.6}}</style></head><body><div class="sheet">${content}</div></body></html>`;
 return {html,width:model.width,height:model.height};
}
