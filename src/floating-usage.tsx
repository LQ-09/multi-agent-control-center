import React,{useEffect,useState,useRef} from 'react';
import {useAgentStatus,orderedMeters,resetCountdown,Account,AgentStatus} from './agent-controls';
import {tr,useDisplayPreferences,setLanguage,setFontSize} from './i18n';
export async function usageWindow(action:string){
 if(!window.__TAURI__)throw new Error('Native window unavailable');
 return window.__TAURI__.core.invoke('usage_window',{action});
}
export function quotaColor(value:number|null){return value===null?'#8a8a8a':value>70?'#269b60':value>=30?'#df9225':'#df4949'}
export function QuotaRing({agent,value}:{agent:string;value:number|null}){
 const color=quotaColor(value),length=2*Math.PI*32;
 return <svg viewBox="0 0 80 80" width="80" height="80" role="img" aria-label={`${agent}: ${value===null?tr('Unknown'):value+'% '+tr('remaining')}`}>
 <circle cx="40" cy="40" r="32" fill="none" stroke="var(--line)" strokeWidth="6"/>
 <circle cx="40" cy="40" r="32" fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" strokeDasharray={`${length*(value===null?0:value/100)} ${length}`} transform="rotate(-90 40 40)" style={{transition:'stroke-dasharray .5s,stroke .5s'}}/>
 <g stroke="currentColor" fill="none" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">{agent==='codex'?<><path d="M31 31 23 40 31 49M49 31 57 40 49 49M44 29 36 51"/></>:<>{Array.from({length:12},(_,i)=><path key={i} d="M40 24V32" transform={`rotate(${i*30} 40 40)`}/>)}<circle cx="40" cy="40" r="5"/></>}</g>
 </svg>
}
export function visibleAccounts(agents:Record<string,Account>){return Object.entries(agents).filter(([agent,a])=>['codex','claude'].includes(agent)&&a.reason!=='CLI not found on this host.')}
export function AccountTile({agent,account,now}:{agent:string;account:Account;now:number}){
 const [expanded,setExpanded]=useState(false),meters=orderedMeters(account.meters||[]),meter=meters[0];
 const stale=!!account.checked_at&&now-Date.parse(account.checked_at)>300000;
 return <article className="float-account"><button className="float-ring-button" onClick={()=>setExpanded(!expanded)} aria-expanded={expanded} title={tr('Other quota windows')}>
 <span className="float-agent-name">{agent==='codex'?'Codex':'Claude'}<span className="float-disclosure">{expanded?'−':'+'}</span></span>
 <QuotaRing agent={agent} value={meter?.remaining_percent??null}/>
 <b style={{color:quotaColor(meter?.remaining_percent??null)}}>{meter?<>{meter.remaining_percent}<span>%</span></>:<span className="float-unknown">{tr('Unavailable')}</span>}</b></button>

 {(stale||account.ordinary_usage_allowed===false)&&<small className="float-warning">{tr(stale?'Usage needs refresh':'Usage restricted')}</small>}
 {expanded&&<div className="float-details"><small>{account.plan} {account.account&&'#'+account.account}</small>{!meter&&<p>{tr(account.reason||'Reading usage…')}</p>}{meters.map((m,i)=><p key={i}>{tr(m.label)} · {m.scope}<br/>{m.remaining_percent}% · {resetCountdown(m.resets_at,now)}</p>)}{account.checked_at&&<small>{tr('Checked')} {new Date(account.checked_at).toLocaleTimeString()}</small>}</div>}
 </article>
}
// Upgrade guidance belongs in Settings, not the desktop quota widget.
export function visibleUsageHosts(status:AgentStatus){
 return Object.entries(status.hosts).filter(([,data])=>data.error!=='Update the remote worker to v0.6 for account and model controls.');
}
export function mergedUsageAccounts(status:AgentStatus){
 const rows=new Map<string,{key:string;agent:string;account:Account}>();
 const checked=(a:Account)=>Number.isFinite(Date.parse(a.checked_at||''))?Date.parse(a.checked_at!):0;
 for(const [host,data] of visibleUsageHosts(status)){
  for(const [agent,account] of visibleAccounts(data.agents)){
   const key=account.account?agent+':account:'+account.account:agent+':host:'+host;
   const previous=rows.get(key);
   if(!previous||checked(account)>checked(previous.account))rows.set(key,{key,agent,account});
  }
 }
 return [...rows.values()];
}
export function usageZoom(value:number){return Number.isFinite(value)?Math.min(1.5,Math.max(.65,value)):1}
export function FloatingUsage(){
 useDisplayPreferences();
 const [zoom,setZoom]=useState(()=>usageZoom(Number(localStorage.getItem('acc-usage-zoom')||1)));
 const changeZoom=(delta:number)=>setZoom(previous=>{const next=usageZoom(Math.round((previous+delta)*100)/100);localStorage.setItem('acc-usage-zoom',String(next));return next});
 const panel=useRef<HTMLDivElement>(null);
 const {status,error,refresh}=useAgentStatus('floating'),[now,setNow]=useState(Date.now()),[windowError,setError]=useState('');
 useEffect(()=>{document.body.classList.add('floating-body');document.documentElement.classList.add('floating-html');const timer=setInterval(()=>setNow(Date.now()),1000);
 const sync=(e:StorageEvent)=>{if(e.key==='acc-language')setLanguage(e.newValue==='en'?'en':'zh');if(e.key==='acc-font-size')setFontSize(Number(e.newValue));if(e.key==='acc-theme')document.documentElement.dataset.theme=e.newValue||'light'};
 window.addEventListener('storage',sync);return()=>{clearInterval(timer);window.removeEventListener('storage',sync);document.documentElement.classList.remove('floating-html');document.body.classList.remove('floating-body')}},[]);
 useEffect(()=>{
  const element=panel.current;if(!element)return;
  let active=true,last=0,chain=Promise.resolve();
  const resize=()=>{const height=Math.ceil(element.offsetHeight);if(height===last)return;last=height;
   chain=chain.then(async()=>{if(!active)return;try{const scale=await window.__TAURI__?.core.invoke<number>('fit_usage',{height,width:element.offsetWidth,zoom});if(active&&scale)element.style.zoom=String(scale)}catch(e){if(active)setError(String(e))}});
  };
  const observer=new ResizeObserver(resize);observer.observe(element);resize();
  return()=>{active=false;observer.disconnect()};
 },[zoom]);
 const hosts=visibleUsageHosts(status),accounts=mergedUsageAccounts(status);
 const control=(action:string)=>void usageWindow(action).catch(e=>setError(String(e)));
 return <div ref={panel} className="floating-usage"><div className="float-toolbar"><span className="float-drag" onMouseDown={e=>{if(e.button===0)control('drag')}} title={tr('Drag to move')}>⠿</span><button onClick={()=>changeZoom(-.1)} disabled={zoom<=.65} title="−">−</button><button onClick={()=>changeZoom(.1)} disabled={zoom>=1.5} title="+">+</button><button onClick={refresh} title={tr('Refresh usage')}>↻</button><button onClick={()=>control('main')} title={tr('Open main window')}>↗</button><button onClick={()=>control('hide')} title={tr('Hide floating usage')}>×</button></div>
 <div className="float-content"><div className="float-accounts">{accounts.map(({key,agent,account})=><AccountTile key={key} agent={agent} account={account} now={now}/>)}</div>{hosts.filter(([,data])=>data.error).map(([host,data])=><p key={host}>{tr(data.error!)}</p>)}{hosts.length>0&&!accounts.length&&!hosts.some(([,data])=>data.error)&&<p className="float-empty">{tr(hosts.some(([,data])=>data.refreshing)?'Reading usage…':'No connected agents')}</p>}
 {!hosts.length&&<p>{tr(error?'Usage query failed; no remaining quota is assumed':'Usage is available for real execution environments')}</p>}{windowError&&<p role="alert">{windowError}</p>}
 </div></div>
}
