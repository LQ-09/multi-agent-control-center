import React from 'react';
import {tr,useDisplayPreferences,setLanguage,setFontSize,fontSizes} from './i18n';
export function DisplayControls({compact=false}:{compact?:boolean}){
 const {language,fontSize}=useDisplayPreferences();
 return <div className={compact?'display-controls compact':'display-controls'}><label>{!compact&&tr('Language')}<select aria-label="界面语言 / Language" value={language} onChange={e=>setLanguage(e.target.value==='en'?'en':'zh')}><option value="zh">简体中文</option><option value="en">English</option></select></label><label>{!compact&&tr('Font size')}<select aria-label={tr('Font size')} value={fontSize} onChange={e=>setFontSize(Number(e.target.value))}>{fontSizes.map((size,i)=><option key={size} value={size}>{compact?'Aa':tr(['Standard','Large','Larger','Largest'][i])} {size}%</option>)}</select></label></div>
}
export function DisplaySettings(){return <section className="panel"><h2>{tr('Appearance')}</h2><DisplayControls/><p>{tr('Interface language only; task text, agent output and paths stay unchanged.')}</p><button onClick={()=>{setLanguage('zh');setFontSize(115)}}>{tr('Reset display')}</button></section>}
