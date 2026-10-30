import {useSyncExternalStore} from 'react';
import chinese from './zh.json';
export type Language='zh'|'en';
export const fontSizes=[100,115,130,150] as const;
const dictionary:Record<string,string>=chinese;
function read(key:string){try{return localStorage.getItem(key)}catch{return null}}
export function normalizeLanguage(value:unknown):Language{return value==='en'?'en':'zh'}
export function normalizeFontSize(value:unknown):number{const n=Number(value);return fontSizes.some(x=>x===n)?n:115}
let language=normalizeLanguage(read('acc-language'));
let fontSize=normalizeFontSize(read('acc-font-size'));
const listeners=new Set<()=>void>();
function apply(){document.documentElement.lang=language==='zh'?'zh-CN':'en';document.documentElement.style.setProperty('--font-scale',String(fontSize/100))}
apply();
function save(key:string,value:string){try{localStorage.setItem(key,value)}catch{/* Display still works if persistent storage is unavailable. */}}
export function setLanguage(value:Language){language=normalizeLanguage(value);save('acc-language',language);apply();listeners.forEach(f=>f())}
export function setFontSize(value:number){fontSize=normalizeFontSize(value);save('acc-font-size',String(fontSize));apply();listeners.forEach(f=>f())}
export function translate(text:string,locale:Language){return locale==='zh'?(dictionary[text]??text):text}
export function tr(text:string){return translate(text,language)}
export function useDisplayPreferences(){useSyncExternalStore(callback=>{listeners.add(callback);return()=>{listeners.delete(callback)}},()=>language+':'+fontSize,()=>language+':'+fontSize);return{language,fontSize}}
