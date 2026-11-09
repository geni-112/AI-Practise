import {useLocale} from './Locale';
import {FONT_FAMILIES,t} from './i18n';
import {useEffect,useRef} from 'react';
import * as echarts from 'echarts/core';
import {BarChart,LineChart,PieChart} from 'echarts/charts';
import {GridComponent,TooltipComponent,LegendComponent,AriaComponent} from 'echarts/components';
import {CanvasRenderer} from 'echarts/renderers';
import type {Row} from './lib';

echarts.use([BarChart,LineChart,PieChart,GridComponent,TooltipComponent,LegendComponent,AriaComponent,CanvasRenderer]);

export default function Chart({data,type='bar',horizontal=false,height=280,onSelect,valueType='money'}:{data:Row[];type?:string;horizontal?:boolean;height?:number;onSelect?:(name:string)=>void;valueType?:string}) {
  const locale=useLocale();
  const fontFamily=FONT_FAMILIES[locale];
  const ref=useRef<HTMLDivElement>(null);
  const onSelectRef=useRef(onSelect);
  onSelectRef.current=onSelect;
  const signature=JSON.stringify(data);

  useEffect(()=>{
    if(!ref.current)return;
    const chart=echarts.init(ref.current);
    const names=data.map(d=>d.name);
    const colors=['#FF441F','#FF9475','#8060B2','#E7AA48','#617CB1','#C27893'];
    const formatter=(v:number)=>valueType==='money'
      ?(Math.abs(v)>=1000?'$'+(v/1000).toFixed(0)+'k':'$'+v)
      :valueType==='ratio'?v+'×':valueType==='percent'?v+'%':v;
    const compact=ref.current.clientWidth<400;
    const option:Record<string,any>={
      animationDuration:window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:350,
      color:colors,
      textStyle:{fontFamily,fontSize:14,color:'#606572'},
      aria:{enabled:true,label:{enabled:true,description:t('图表数据：{0}',[data.map(d=>`${t(d.name)}: ${formatter(Number(d.value))}`).join('; ')])}},
      tooltip:{trigger:type==='pie'?'item':'axis',confine:true,backgroundColor:'#FFFFFF',borderColor:'#E6E7EB',padding:12,textStyle:{color:'#25262B',fontSize:14,fontFamily},valueFormatter:(v:number)=>valueType==='money'?'$'+Number(v).toLocaleString(locale,{maximumFractionDigits:2}):formatter(v)},
      grid:{left:horizontal?12:16,right:22,top:22,bottom:16,containLabel:true},
      xAxis:{type:horizontal?'value':'category',data:horizontal?undefined:names,axisLine:{show:false},axisTick:{show:false},axisLabel:{fontSize:13,color:'#606572',margin:14,formatter:horizontal?formatter:(name:string)=>t(name),hideOverlap:true,rotate:!horizontal&&compact&&names.length>4?24:0},splitLine:{show:horizontal,lineStyle:{color:'#ECECF1',type:'dashed'}}},
      yAxis:{type:horizontal?'category':'value',data:horizontal?names:undefined,inverse:horizontal,axisLine:{show:false},axisTick:{show:false},axisLabel:{fontSize:13,color:'#606572',margin:12,formatter:horizontal?(name:string)=>t(name):formatter,overflow:'truncate',width:compact?85:115},splitLine:{show:!horizontal,lineStyle:{color:'#ECECF1',type:'dashed'}}},
      series:[{
        type:type==='line'?'line':'bar',data:data.map((d,i)=>({value:d.value,itemStyle:{color:type==='line'?'#FF441F':colors[i%colors.length],borderRadius:horizontal?[0,5,5,0]:[5,5,0,0]}})),
        barMaxWidth:40,smooth:.3,symbol:'circle',symbolSize:7,lineStyle:{width:3,color:'#FF441F'},itemStyle:{color:'#FF441F'},
        areaStyle:type==='line'?{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(255,68,31,.16)'},{offset:1,color:'rgba(255,68,31,0)'}])}:undefined,
      }],
    };
    if(type==='pie'){
      delete option.xAxis;delete option.yAxis;
      option.legend={formatter:(name:string)=>t(name),bottom:0,left:12,right:12,icon:'circle',itemWidth:9,itemHeight:9,itemGap:14,textStyle:{fontSize:13,color:'#606572'}};
      option.series=[{type:'pie',radius:['45%','68%'],center:['50%','40%'],avoidLabelOverlap:true,padAngle:3,itemStyle:{borderRadius:6},label:{show:false},data:data.map(d=>({name:d.name,value:d.value}))}];
    }
    chart.setOption(option);
    chart.on('click',(p:any)=>onSelectRef.current?.(p.name));
    const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);
    return()=>{observer.disconnect();chart.dispose();};
  },[signature,type,horizontal,valueType,locale]);

  return <div ref={ref} style={{height,width:'100%'}} role="img" aria-label={data.map(d=>`${d.name}: ${Number(d.value).toFixed(2)}`).join(', ')}/>;
}
