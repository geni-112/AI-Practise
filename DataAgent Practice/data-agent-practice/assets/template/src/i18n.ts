import catalog from './messages.json';

export const LOCALES = ['zh-CN','en-US','es-ES'] as const;
export type Locale = typeof LOCALES[number];
export const LANGUAGE_LABELS: Record<Locale,string> = {'zh-CN':'简体中文','en-US':'English (US)','es-ES':'Español'};
export const FONT_FAMILIES: Record<Locale,string> = {
  'zh-CN':'"Microsoft YaHei", "微软雅黑", "PingFang SC", "Noto Sans SC", sans-serif',
  'en-US':'Arial, Helvetica, sans-serif',
  'es-ES':'Verdana, "Segoe UI", Arial, sans-serif',
};
const messages: Record<string,string[]> = catalog;
export const isLocale = (value: unknown): value is Locale => LOCALES.includes(value as Locale);
function storedLocale(): Locale {
  try {const value=localStorage.getItem('nexo-locale');return isLocale(value)?value:'zh-CN';}
  catch {return 'zh-CN';}
}
let locale: Locale = storedLocale();
const listeners = new Set<()=>void>();
export const getLocale = () => locale;
export const subscribeLocale = (listener:()=>void) => {listeners.add(listener);return ()=>{listeners.delete(listener);};};
function applyLocale() {
  if(typeof document==='undefined')return;
  document.documentElement.lang=locale;
  document.documentElement.style.setProperty('--font-sans',FONT_FAMILIES[locale]);
  document.title=locale==='es-ES'?'NEXO · Agente de datos':'NEXO · Data Agent';
}
export function setLocale(next:Locale) {
  if(!isLocale(next))return;
  locale=next;
  try {localStorage.setItem('nexo-locale',next);}catch {/* Preference persistence is optional. */}
  applyLocale();listeners.forEach(listener=>listener());
}
const reverse = new Map<string,string>();
for(const [key,values] of Object.entries(messages))for(const value of values)if(!reverse.has(value))reverse.set(value,key);
const escapeRegExp=(value:string)=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const templates: {key:string;expression:RegExp;slots:number[]}[]=[];
for(const [key,values] of Object.entries(messages)) {
  if(!/\{\d+\}/.test(key))continue;
  for(const source of [key,...values]) {
    const slots:number[]=[];let expression='',start=0;
    for(const match of source.matchAll(/\{(\d+)\}/g)) {
      expression+=escapeRegExp(source.slice(start,match.index))+'(.*?)';slots.push(Number(match[1]));start=match.index!+match[0].length;
    }
    expression+=escapeRegExp(source.slice(start));
    templates.push({key,expression:new RegExp('^'+expression+'$','s'),slots});
  }
}
function render(key:string,values:readonly unknown[]=[]) {
  const variants=messages[key];
  const text=!variants?key:locale==='zh-CN'?(variants[2]||key):variants[locale==='en-US'?0:1];
  return text.replace(/\{(\d+)\}/g,(original,index)=>values[Number(index)]==null?original:String(values[Number(index)]));
}
export function canonicalText(message:string) {return messages[message]?message:reverse.get(message)||message;}
export function t(message:string|number|null|undefined,values?:readonly unknown[]):string {
  if(message==null)return '';
  const text=String(message),key=text.trim();
  const leading=text.match(/^\s*/)?.[0]||'',trailing=text.match(/\s*$/)?.[0]||'';
  if(!key)return text;
  const canonical=messages[key]?key:reverse.get(key);
  if(canonical)return leading+render(canonical,values)+trailing;
  for(const template of templates) {
    const match=key.match(template.expression);
    if(match){const args:unknown[]=[];template.slots.forEach((slot,i)=>args[slot]=match[i+1]);return leading+render(template.key,args)+trailing;}
  }
  return text;
}
export const formatNumber=(value:number,options?:Intl.NumberFormatOptions)=>new Intl.NumberFormat(locale,options).format(value);
export const formatDate=(value:string,options?:Intl.DateTimeFormatOptions)=>new Date(value).toLocaleString(locale,options);
applyLocale();
if(typeof window!=='undefined')window.addEventListener('storage',event=>{
  if(event.key==='nexo-locale'&&isLocale(event.newValue)&&event.newValue!==locale){locale=event.newValue;applyLocale();listeners.forEach(listener=>listener());}
});
