import React,{useEffect,useState} from 'react';
import {rpc,Provider} from './types';
import {tr} from './i18n';
export type Selection={model:string;effort:string};
export type AgentDefaults={roles:string[];codex:Selection;claude:Selection};
export const initialDefaults:AgentDefaults={roles:['codex','codex','codex'],codex:{model:'',effort:''},claude:{model:'',effort:''}};
export type Model={id:string;name:string;efforts:string[];default_effort?:string;default?:boolean};
type Meter={label:string;scope:string;remaining_percent:number;resets_at:string|null};
export type Account={status:string;models_source?:string;models_error?:string;models_checked_at?:string;models_stale?:boolean;cli_path?:string;reason?:string;plan?:string;account?:string;checked_at?:string;meters:Meter[];models:Model[];cli_model?:string;cli_effort?:string;ordinary_usage_allowed?:boolean};
type Host={refreshing?:boolean;error?:string;agents:Record<string,Account>};
export type AgentStatus={environment?:string;hosts:Record<string,Host>};
export function useAgentStatus(environment:string){
 const [status,setStatus]=useState<AgentStatus>({hosts:{}}),[error,setError]=useState('');
 useEffect(()=>{let active=true;setStatus({hosts:{}});setError('');const poll=()=>void rpc<AgentStatus>('agent_status').then(v=>{if(active){setStatus(v);setError('')}}).catch(e=>{if(active){setStatus({hosts:{}});setError(String(e))}});poll();const timer=setInterval(poll,15000);return()=>{active=false;clearInterval(timer)}},[environment]);
 // Refresh starts background probes. The regular poll retrieves their result without blocking tasks.
 const refresh=()=>void rpc('agent_status',{refresh:true}).catch(e=>setError(String(e)));
 return {status,error,refresh};
}
export function resetCountdown(reset:string|null,now=Date.now()){
 if(!reset||!Number.isFinite(Date.parse(reset)))return tr('Reset time unavailable');
 const minutes=Math.ceil((Date.parse(reset)-now)/60000);
 if(minutes<=0)return tr('Reset due — awaiting refreshed usage');
 const days=Math.floor(minutes/1440),hours=Math.floor(minutes%1440/60),mins=minutes%60;
 return tr('Resets in')+' '+(days?days+tr('d '):'')+(hours?hours+tr('h '):'')+mins+tr('m');
}
export function orderedMeters(meters:Meter[]){return [...meters].sort((a,b)=>a.remaining_percent-b.remaining_percent)}
function UsageMeters({meters,now}:{meters:Meter[];now:number}){
 const sorted=orderedMeters(meters);
 const render=(m:Meter,i:number)=><div className="usage-meter" key={i}><span>{tr(m.label)}{m.scope&&' · '+m.scope}</span><strong>{m.remaining_percent}% {tr('remaining')}</strong><progress max={100} value={m.remaining_percent}/><small>{resetCountdown(m.resets_at,now)}</small>{m.resets_at&&<small>{tr('Resets')} {new Date(m.resets_at).toLocaleString()}</small>}</div>;
 return <>{sorted.slice(0,1).map(render)}{sorted.length>1&&<details><summary>{tr('Other quota windows')}</summary>{sorted.slice(1).map(render)}</details>}</>;
}
export function UsageSidebar({status,error,refresh,providers,settings}:{status:AgentStatus;error:string;refresh:()=>void;providers:Provider[];settings:()=>void}){
 const [now,setNow]=useState(Date.now());
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer)},[]);
 return <section className="usage-sidebar"><div className="usage-heading"><strong>{tr('Account usage')}</strong><button onClick={refresh} title={tr('Refresh usage')}>↻</button></div><div className="usage-scroll">
 {Object.entries(status.hosts).map(([host,data])=><div key={host}><small>{tr(host==='local'?'This computer':'Remote')}{data.refreshing&&' · '+tr('Refreshing…')}</small>{data.error&&<p>{tr(data.error)}</p>}{['codex','claude'].map(agent=>{const a=data.agents[agent],stale=!!a?.checked_at&&Date.now()-Date.parse(a.checked_at)>300000;return <details className="usage-account" key={agent} open><summary>{agent==='codex'?'Codex':'Claude Code'} <span>{a?.plan||''}</span></summary>{a?.account&&<small>{tr('Account')} #{a.account}</small>}{stale&&<p>{tr('Stale usage — refresh before deciding')}</p>}{a?.ordinary_usage_allowed===false&&<p>{tr('Included usage is currently restricted')}</p>}{a?.meters?.length?<UsageMeters meters={a.meters} now={now}/>:<p>{tr(a?.reason||'Reading usage…')}</p>}{a?.checked_at&&<small>{tr('Checked')} {new Date(a.checked_at).toLocaleTimeString()}</small>}</details>})}</div>)}
 {providers.map(p=><div className="usage-account" key={p.id}><strong>{p.name}</strong><small>{p.model}</small><p>{tr('API quota unavailable — check provider billing')}</p></div>)}
 {!Object.keys(status.hosts).length&&!error&&<p>{tr('Usage is available for real execution environments')}</p>}{error&&<p>{tr('Usage query failed; no remaining quota is assumed')}</p>}
 </div><small>{tr('Account quotas may be shared across models. No automatic switching.')}</small><button onClick={settings}>{tr('Default models and effort')}</button></section>
}
function catalog(status:AgentStatus,host:string,agent:string){return status.hosts[host]?.agents[agent]?.models||[]}
export function AgentOptions({agent,value,onChange,models=[],ident}:{agent:string;value:Selection;onChange:(v:Selection)=>void;models?:Model[];ident:string}){
 if(agent.startsWith('api:'))return <small>{tr('Model and reasoning effort come from the provider profile.')}</small>;
 const model=models.find(m=>m.id===value.model),efforts=model?.efforts||[];
 return <div className="model-options"><label>{tr('Model')}<select id={ident+'-models'} value={value.model} onChange={e=>onChange({model:e.target.value,effort:''})}><option value="">{tr('CLI default')}</option>{value.model&&!model&&<option value={value.model} disabled>{value.model} — {tr('Not in current model list')}</option>}{models.map(m=><option key={m.id} value={m.id}>{m.name} · {m.id}</option>)}</select></label><label>{tr('Reasoning effort')}<select value={value.effort} disabled={!model||!efforts.length} onChange={e=>onChange({...value,effort:e.target.value})}><option value="">{tr('CLI default')}</option>{value.effort&&!efforts.includes(value.effort)&&<option value={value.effort} disabled>{value.effort} — {tr('Unsupported')}</option>}{efforts.map(x=><option key={x} value={x}>{tr(x)}</option>)}</select></label><small>{tr(models.length?'Select a model to see its supported effort levels.':'Model list unavailable. Refresh usage or use CLI default.')}</small></div>
}
export function modelsFor(status:AgentStatus,remote:boolean,split:boolean,index:number,agent:string){return catalog(status,remote&&(!split||index===1)?'remote':'local',agent)}
export function AgentSettings({saved,status,remote,busy,action}:{saved:AgentDefaults;status:AgentStatus;remote:boolean;busy:boolean;action:(op:string,args:unknown)=>Promise<unknown>}){
 const [value,setValue]=useState(saved),[note,setNote]=useState(''),[modelHost,setModelHost]=useState(remote?'remote':'local');
 useEffect(()=>setModelHost(remote?'remote':'local'),[remote]);
 useEffect(()=>setValue(saved),[JSON.stringify(saved)]);
 return <section className="panel agent-settings"><h2>{tr('Default models and effort')}</h2><button disabled={busy} onClick={()=>void action('agent_status',{refresh:true}).catch(()=>{})}>{tr('Refresh model lists')}</button><label>{tr('Model list host')}<select value={modelHost} onChange={e=>setModelHost(e.target.value)}><option value="local">{tr('This computer')}</option>{remote&&<option value="remote">{tr('Remote')} · {status.environment}</option>}</select></label><p>{tr('Models are queried from the selected CLI host, cached for 5 minutes. Refresh does not query the ChatGPT app model menu.')}</p><p>{tr('Defaults apply to new tasks only. Each task stores its own selection; changing defaults does not alter queued work.')}</p><div className="role-fields">{['Planner','Executor','Reviewer'].map((role,i)=><label key={role}>{tr(role)}<select value={value.roles[i]} onChange={e=>setValue({...value,roles:value.roles.map((v,j)=>j===i?e.target.value:v)})}><option value="codex">Codex</option><option value="claude">Claude Code</option></select></label>)}</div><div className="agent-default-grid">{(['codex','claude'] as const).map(agent=>{const native=status.hosts[modelHost]?.agents[agent];return <div key={agent}><h3>{agent==='codex'?'Codex':'Claude Code'}</h3><AgentOptions ident={'default-'+agent} agent={agent} value={value[agent]} onChange={v=>setValue({...value,[agent]:v})} models={catalog(status,modelHost,agent)}/><small>{native?.models_source||tr('Awaiting model discovery')}{native?.models_checked_at&&' · '+new Date(native.models_checked_at).toLocaleString()}</small>{native?.cli_path&&<small className="model-source-path">{native.cli_path}</small>}{(native?.models_error||status.hosts[modelHost]?.error)&&<p role="status">{tr(native?.models_error||status.hosts[modelHost]?.error||'')}</p>}{native?.models_stale&&<p>{tr('Cached model list — last refresh failed; explicit selections require fresh validation.')}</p>}{native?.cli_model&&<p>{tr('Detected CLI model')}: {native.cli_model} · {native.cli_effort||tr('CLI default')}</p>}</div>})}</div><button className="primary" disabled={busy} onClick={()=>void action('save_agent_defaults',value).then(()=>setNote('Agent defaults saved')).catch(()=>{})}>{tr('Save agent defaults')}</button>{note&&<p role="status">{tr(note)}</p>}</section>
}
