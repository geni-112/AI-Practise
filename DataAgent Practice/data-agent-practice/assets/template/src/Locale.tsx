import {useSyncExternalStore} from 'react';
import {Globe2} from 'lucide-react';
import {getLocale,subscribeLocale,setLocale,LOCALES,LANGUAGE_LABELS,t,type Locale} from './i18n';

export function useLocale() {return useSyncExternalStore(subscribeLocale,getLocale,()=> 'zh-CN' as Locale);}
export default function LanguageSwitcher() {
  const locale=useLocale();
  return <label className="language-switcher" title={t('切换语言')}>
    <Globe2 size={17} aria-hidden="true"/>
    <select aria-label={t('切换语言')} value={locale} onChange={event=>setLocale(event.target.value as Locale)}>
      {LOCALES.map(value=><option key={value} value={value}>{LANGUAGE_LABELS[value]}</option>)}
    </select>
  </label>;
}
