/* Stable values keep project records and report calculations consistent. */
const DICTIONARY_SCHEMA = [
  {field:'type',name:'业务类别',extensible:true,required:true,items:[['大数据','大数据','Big Data'],['数据库','数据库','Database']]},
  {field:'cloud',name:'云类别',extensible:true,items:[['公有云','公有云','Public cloud'],['混合云','混合云','Hybrid cloud']]},
  {field:'repo',name:'代表处',extensible:true,allowCustom:true,items:[]},
  {field:'industry',name:'行业',extensible:true,allowCustom:true,items:[]},
  {field:'vendor',name:'现网厂家',extensible:true,allowCustom:true,items:[]},
  {field:'bdName',name:'BD 展示姓名',extensible:true,allowCustom:true,items:[]},
  {field:'saName',name:'SA 展示姓名',extensible:true,allowCustom:true,items:[]},
  {field:'confidence',name:'把握度',extensible:true,allowCustom:true,items:[]},
  {field:'stage',name:'当前阶段',required:true,items:[['0','线索收集','Lead discovery'],['1','需求确认','Requirements'],['2','方案交流','Solution discussion'],['3','POC 准备','POC preparation'],['4','POC 验证','POC validation'],['5','商务推进','Commercial engagement'],['6','已签约','Signed'],['7','交付中','Delivery'],['8','持续运营 / 完成','Operations / completed']]},
  {field:'status',name:'推进状态',required:true,items:[['正常','正常','On track'],['挂起','挂起','On hold'],['丢单','丢单','Lost']]},
  {field:'risk',name:'阻塞标记',required:true,items:[['false','正常','On track'],['true','存在阻塞','Blocked']]},
  {field:'milestoneState',name:'里程碑状态',required:true,items:[['未开展','未开展','Not started'],['进行中','进行中','In progress'],['已完成','已完成','Completed'],['不适用','不适用','Not applicable']]},
  {field:'revenueKind',name:'收入类型',required:true,items:[['EI','EI','EI'],['专业服务','专业服务','Professional services']]}
];
function defaultDictionary(definition){return {...definition,id:'dictionary:'+definition.field,_version:0,allowCustom:!!definition.allowCustom,items:definition.items.map(([value,zh,en])=>({value,zh,en,enabled:true}))}}
