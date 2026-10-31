import React,{useState} from 'react';
import {Task,Step,Artifact,rpc} from './types';
import {tr} from './i18n';
export function TaskActions({task,steps,busy,control}:{task:Task;steps:Step[];busy:boolean;control:(t:Task,a:string)=>void}){
 const unsafe=steps.some(s=>s.lease!=null||s.status==='Running'||/unknown|unconfirmed/i.test(s.error||''));
 const pending=['Queued','Running','Planning'].includes(task.status);
 const retry=steps.some(s=>['Blocked','Failed'].includes(s.status));
 const button=(label:string,action:string,disabled=false)=><button disabled={busy||disabled} onClick={()=>control(task,action)}>{tr(label)}</button>;
 if(task.archived)return <div className="controls">{button('Restore task','restore')}</div>;
 return <div className="controls">
 {['Draft','Paused'].includes(task.status)&&!retry&&button(task.status==='Paused'?'Continue task':'▶ Run task','run',unsafe)}
 {['Blocked','Failed','Paused'].includes(task.status)&&retry&&button('↻ Retry blocked step','retry',unsafe)}
 {pending&&button('Ⅱ Pause','pause')}
 {!['Completed','Cancelled'].includes(task.status)&&button('Cancel','cancel')}
 {!pending&&button('Restart all steps','restart',unsafe)}
 {!pending&&button('Delete to trash','archive',unsafe)}
 {unsafe&&<small>{tr('Waiting for the previous process to stop or be reconciled.')}</small>}
 </div>;
}
export function ArtifactList({items,open}:{items:Artifact[];open:(a:Artifact)=>void}){
 const [versions,setVersions]=useState<Record<string,Artifact[]>>({}),[error,setError]=useState('');
 return <>{error&&<p role="alert">{error}</p>}{items.map(a=><div key={a.id}>
 <button className="artifact-row" onClick={()=>open(a)}><span>▧</span><div><strong>{a.task_title} · {a.name}</strong><small>{a.summary}</small><small>{new Date(a.created).toLocaleString()} · SHA-256 {a.sha256.slice(0,12)}</small></div></button>
 {(a.versions||0)>1&&<details onToggle={e=>{if(e.currentTarget.open&&!versions[a.id])void rpc<Artifact[]>('artifact_versions',{id:a.id}).then(rows=>setVersions(v=>({...v,[a.id]:rows}))).catch(e=>setError(String(e)))}}><summary>{tr('Previous versions')} ({a.versions})</summary>{versions[a.id]?.map(v=><button key={v.id} onClick={()=>open(v)}>{new Date(v.created).toLocaleString()} · {v.sha256.slice(0,12)}</button>)}</details>}
 </div>)}{!items.length&&<p>{tr('No handoffs yet.')}</p>}</>;
}
