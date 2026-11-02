import {tr} from './i18n';
import React,{useEffect,useState,useRef} from 'react';
type Status={current:string;busy:boolean;status:{phase?:string;version?:string;notes?:string;received?:number;total?:number;error?:string}|null};
const autoKey='acc-auto-updates';
const enabled=()=>localStorage.getItem(autoKey)==='true';
export function autoUpdateRunner(invoke:<T>(cmd:string,args?:unknown)=>Promise<T>,idle:()=>boolean,isEnabled=enabled,clock=Date.now){
 let checking=false,nextCheck=0,available=false;
 return async()=>{
  if(checking||!isEnabled())return;
  checking=true;
  try{
   const state=await invoke<Status>('update_status');
   if(state.busy)return;
   if(clock()>=nextCheck){
    nextCheck=clock()+3600000;
    const result=await invoke<NonNullable<Status['status']>>('app_update',{install:false});
    available=Boolean(result.version);
   }
   if(available&&isEnabled()&&idle()){
    available=false;
    await invoke('app_update',{install:true});
   }
  }catch{/* The existing update status displays errors; retry at the next hourly check. */}
  finally{checking=false;}
 };
}
export function useAutoUpdates(idle:boolean){
 const ready=useRef(idle);ready.current=idle;
 useEffect(()=>{
  if(!window.__TAURI__)return;
  const tick=autoUpdateRunner((cmd,args)=>window.__TAURI__!.core.invoke(cmd,args),()=>ready.current);
  const run=()=>{void tick()};run();
  const timer=setInterval(run,60000);window.addEventListener('acc-auto-updates',run);
  return()=>{clearInterval(timer);window.removeEventListener('acc-auto-updates',run)};
 },[]);
}
export function Updates(){
 const [automatic,setAutomatic]=useState(enabled);
 function toggle(value:boolean){localStorage.setItem(autoKey,String(value));setAutomatic(value);window.dispatchEvent(new Event('acc-auto-updates'));}

 const [state,setState]=useState<Status|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false);
 const invoke=<T,>(cmd:string,args:unknown={})=>window.__TAURI__!.core.invoke<T>(cmd,args);
 useEffect(()=>{let live=true;const poll=()=>void invoke<Status>('update_status').then(s=>{if(live)setState(s)}).catch(e=>{if(live)setError(String(e))});poll();const timer=setInterval(poll,500);return()=>{live=false;clearInterval(timer)}},[]);
 async function update(install:boolean){setError('');setPending(true);try{await invoke('app_update',{install})}catch(e){setError(String(e))}finally{setPending(false)}}
 const status=state?.status,busy=pending||state?.busy;
 return <section className="panel" style={{marginBottom:24}}><h2>{tr("App updates")}</h2><p>{tr("Current version: ")}{state?.current||'…'}{tr(". Updates preserve your settings and task data.")}</p><p>{tr("Pause or finish tasks before updating. The app restarts after installation.")}</p><label><input type="checkbox" checked={automatic} onChange={e=>toggle(e.target.checked)}/>{tr("Automatic updates")}</label><p className="muted">{tr("When enabled, check at startup and hourly; install and restart automatically when tasks are idle. Remote workers are updated separately.")}</p><div className="toolbar"><button disabled={busy} onClick={()=>void update(false)}>{tr("Check for updates")}</button>{status?.version&&<button className="primary" disabled={busy} onClick={()=>void update(true)}>{tr("Install ")}{status.version}{tr(" and restart")}</button>}</div><p role="status">{tr(status?.phase||'')}{status?.received!=null&&` ${Math.round(status.received/1024/1024)} MB${status.total?' / '+Math.round(status.total/1024/1024)+' MB':''}`}</p>{status?.notes&&<p>{status.notes}</p>}{(error||status?.error)&&<p role="alert" className="danger">{tr(error||status?.error||'')}{tr("You can retry; task data is preserved.")}</p>}<small>{tr("Updates come from this project's GitHub Releases and require a valid signature.")}</small></section>
}
