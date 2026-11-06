import React,{useState} from 'react';
import {Step} from './types';
import {tr} from './i18n';
import {handoffSummary} from './task-timeline';

export function graphLayout(steps:Step[]){
 const ordered=[...steps].sort((a,b)=>a.position-b.position);
 const ranks=new Map<string,number>();const lanes=new Map<number,number>();
 const nodes=ordered.map((step,i)=>{
  let deps:string[];
  try{deps=step.dependencies?JSON.parse(step.dependencies):ordered.slice(0,i).slice(-1).map(s=>s.id)}catch{deps=[]}
  const rank=deps.length?Math.max(...deps.map(id=>ranks.get(id)??-1))+1:0;
  ranks.set(step.id,rank);const lane=lanes.get(rank)||0;lanes.set(rank,lane+1);
  return {step,deps,x:lane*252+16,y:rank*172+16};
 });
 return {nodes,width:Math.max(1,...lanes.values())*252+16,height:(Math.max(0,...ranks.values())+1)*172};
}
export function TaskGraph({steps}:{steps:Step[]}){
 const [selected,setSelected]=useState<string|null>(null);
 const {nodes,width,height}=graphLayout(steps);const chosen=steps.find(s=>s.id===selected);
 const succeeded=new Set(steps.filter(s=>s.status==='Succeeded').map(s=>s.id));
 const title=(s:Step)=>s.node_key||tr(s.role);
 return <section className="panel task-graph"><div className="graph-heading"><h3>{tr('Task graph')}</h3><span>{steps.filter(s=>s.status==='Running').length} / 3 {tr('agents running')}</span></div>
  <p className="muted">{tr('Arrows show dependencies. Branches can run together; joins wait for their inputs. Click a node for details.')}</p>
  {steps.length===1&&<p>{tr('The planner will add the task branches here.')}</p>}
  <div className="graph-scroll" tabIndex={0} aria-label={tr('Task graph')}><div className="graph-canvas" style={{width,height}}>
   <svg width={width} height={height} aria-hidden="true"><defs><marker id="graph-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="currentColor"/></marker></defs>
    {nodes.flatMap(n=>n.deps.map(dep=>{const from=nodes.find(x=>x.step.id===dep);if(!from)return null;const x=from.x+110,y=from.y+132,tx=n.x+110,ty=n.y;return <path key={dep+n.step.id} className={selected===dep||selected===n.step.id?'graph-edge active':'graph-edge'} d={`M${x},${y} C${x},${y+20} ${tx},${ty-20} ${tx},${ty}`} markerEnd="url(#graph-arrow)"/>}))}
   </svg>
   {nodes.map(({step:s,deps,x,y})=><button key={s.id} className={`graph-node ${s.status.toLowerCase()} ${selected===s.id?'selected':''}`} style={{left:x,top:y}} onClick={()=>setSelected(s.id)} aria-pressed={selected===s.id}>
    <strong>{title(s)}</strong><small>{tr(s.role)} · {s.agent}</small><span className="graph-instruction">{s.instruction||tr('Plan task assignments')}</span><small className="graph-status">{s.status==='Pending'?tr(deps.every(id=>succeeded.has(id))?'Ready · waiting for slot/resource':'Waiting for dependencies'):tr(s.status)}</small>
   </button>)}
  </div></div>
  {chosen&&<div className="graph-detail"><strong>{title(chosen)} · {tr(chosen.status)}</strong><p>{chosen.instruction||tr('Plan task assignments')}</p><small>{chosen.agent} · {chosen.host} · {chosen.model||tr('CLI default')} · {tr(chosen.access||'read-only')}</small><p>{tr('Depends on')}: {(nodes.find(n=>n.step.id===chosen.id)?.deps||[]).map(id=>steps.find(s=>s.id===id)).filter((s):s is Step=>!!s).map(title).join(', ')||tr('None')}</p>{chosen.error&&<p className="danger">{chosen.error}</p>}{chosen.output&&<><p>{handoffSummary(chosen.output)}</p><details><summary>{tr('Full output')}</summary><pre>{chosen.output}</pre></details></>}</div>}
 </section>;
}
