import React,{useEffect,useState} from 'react';
type Status={current:string;busy:boolean;status:{phase?:string;version?:string;notes?:string;received?:number;total?:number;error?:string}|null};
export function Updates(){
 const [state,setState]=useState<Status|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false);
 const invoke=<T,>(cmd:string,args:unknown={})=>window.__TAURI__!.core.invoke<T>(cmd,args);
 useEffect(()=>{let live=true;const poll=()=>void invoke<Status>('update_status').then(s=>{if(live)setState(s)}).catch(e=>{if(live)setError(String(e))});poll();const timer=setInterval(poll,500);return()=>{live=false;clearInterval(timer)}},[]);
 async function update(install:boolean){setError('');setPending(true);try{await invoke('app_update',{install})}catch(e){setError(String(e))}finally{setPending(false)}}
 const status=state?.status,busy=pending||state?.busy;
 return <section className="panel" style={{marginBottom:24}}><h2>App updates · 软件更新</h2><p>Current version: {state?.current||'…'}. Updates preserve your settings and task data.</p><p>更新前请暂停或结束任务。安装成功后 App 会自动重启。</p><div className="toolbar"><button disabled={busy} onClick={()=>void update(false)}>检查更新 / Check for updates</button>{status?.version&&<button className="primary" disabled={busy} onClick={()=>void update(true)}>安装 {status.version} 并重启</button>}</div><p role="status">{status?.phase}{status?.received!=null&&` ${Math.round(status.received/1024/1024)} MB${status.total?' / '+Math.round(status.total/1024/1024)+' MB':''}`}</p>{status?.notes&&<p>{status.notes}</p>}{(error||status?.error)&&<p role="alert" className="danger">{error||status?.error}。可重试；任务数据不会被删除。</p>}<small>首次从旧版升级需覆盖安装一次。更新来自本项目 GitHub Releases，安装前必须通过签名校验。</small></section>
}
