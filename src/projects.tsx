import React, {useState} from 'react';
import {tr} from './i18n';
import {Project, Snapshot} from './types';

export function Projects({data,busy,action}:{data:Snapshot;busy:boolean;action:(op:string,args:unknown)=>Promise<unknown>}) {
 const [editing,setEditing]=useState<Project|null>(null),[name,setName]=useState(''),[path,setPath]=useState('');
 const [documents,setDocuments]=useState(''),[rules,setRules]=useState(''),[localPaths,setLocalPaths]=useState<Record<string,string>>({});
 const [error,setError]=useState('');
 const enabled=data.mode!=='demo'&&data.connected&&data.capabilities?.shared_workspaces;
 function edit(p:Project){setEditing(p);setName(p.name);setPath(p.repo_path);setDocuments(p.documents.join('\n'));setRules(p.rules)}
 async function save(e:React.FormEvent){e.preventDefault();setError('');try{
  await action('save_project',{id:editing?.id,revision:editing?.revision,name,repo_path:path,documents:documents.split('\n').map(s=>s.trim()).filter(Boolean),rules});
  setEditing(null);setName('');setPath('');setDocuments('');setRules('');
 }catch(e){setError(String(e))}}
 return <div className="projects-grid">
  <section className="panel"><h2>{tr('Projects and workspaces')}</h2><p>{tr('Register existing Git repositories. Original folders and native agent sessions stay in place. Tasks use separate worktrees from committed code.')}</p>
   {!enabled&&<div className="notice">{tr('Connect an updated backend to register or edit projects.')}</div>}
   {(data.projects||[]).map(p=><article className="project-card" key={p.id}>
    <div className="section-heading"><h3>{p.name}</h3><button disabled={busy||!enabled} onClick={()=>edit(p)}>{tr('Edit')}</button></div>
    <code>{p.repo_path}</code><p>{tr('Shared documents')}: {p.documents.join(', ')||tr('None selected')}</p>
    <small>{tr('Policy revision')}: {p.revision} · {tr('Registered commit')}: {p.base_commit.slice(0,12)}</small>
    {data.mode==='live'&&<div><label>{tr('Existing local clone for offline work')}<input aria-label={p.name+' '+tr('Local clone')} value={localPaths[p.id]??p.local_repo_path??''} onChange={e=>setLocalPaths({...localPaths,[p.id]:e.target.value})}/></label>
     <button disabled={busy||!enabled} onClick={()=>{setError('');void action('cache_project',{id:p.id,repo_path:localPaths[p.id]??p.local_repo_path??''}).catch(e=>setError(String(e)))}}>{tr('Verify and pair local clone')}</button>
     <p>{tr(p.offline_ready?'Local clone paired; offline tasks use the cached committed version.':'Offline execution requires a matching local clone and commit.')}</p></div>}
   </article>)}
   {!data.projects?.length&&<p>{tr('No registered projects yet.')}</p>}
  </section>
  <form className="panel" onSubmit={e=>void save(e)}><h2>{tr(editing?'Edit project':'Register project')}</h2>
   <label>{tr('Project name')}<input required maxLength={80} value={name} onChange={e=>setName(e.target.value)}/></label>
   <label>{tr('Git repository root on selected host')}<input required value={path} onChange={e=>setPath(e.target.value)}/></label>
   <label>{tr('Shared documents — one repository-relative path per line')}<textarea rows={3} value={documents} onChange={e=>setDocuments(e.target.value)} placeholder={'AGENTS.md\nREADME.md'}/></label>
   <label>{tr('Shared storage and reading rules')}<textarea rows={5} maxLength={4000} value={rules} onChange={e=>setRules(e.target.value)}/></label>
   <p>{tr('Rules and selected document contents are attached to every role, retry and restart, including text-only agents. Existing tasks keep their pinned project version.')}</p>
   <button className="primary" disabled={busy||!enabled}>{tr('Save project')}</button>
   {editing&&<button type="button" onClick={()=>{setEditing(null);setName('');setPath('');setDocuments('');setRules('')}}>{tr('Cancel')}</button>}
   {error&&<p role="alert" className="danger">{error}</p>}
  </form>
  <section className="panel project-worktrees"><h2>{tr('Task worktrees')}</h2><p>{tr('Each task has its own branch. Sequential roles share that worktree; restart creates a fresh one. Original repositories are never merged automatically.')}</p>
   {(data.workspaces||[]).map(w=><article className="project-card" key={w.id}><strong>{data.tasks.find(t=>t.id===w.task_id)?.title||w.task_id}</strong><p><code>{w.path}</code></p><small>{w.branch} · {w.base_commit.slice(0,12)}</small></article>)}
  </section>
 </div>
}

export function TaskContext({taskId,action}:{taskId:string;action:(op:string,args:unknown)=>Promise<unknown>}){
 const [context,setContext]=useState<unknown>();
 return <details onToggle={e=>{if(e.currentTarget.open)void action('project_context',{id:taskId}).then(setContext).catch(()=>{})}}>
  <summary>{tr('Attached project context')}</summary><pre>{context?JSON.stringify(context,null,2):tr('Context is generated when the task starts.')}</pre>
 </details>
}
