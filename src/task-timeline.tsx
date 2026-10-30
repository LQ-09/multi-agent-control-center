import React from 'react';
import {Step} from './types';
import {tr} from './i18n';
export function handoffSummary(output:string){
 let text=output;
 const match=output.match(/<acc_result>([\s\S]*?)<\/acc_result>/);
 if(match){try{const result=JSON.parse(match[1]);if(typeof result.summary==='string')text=result.summary}catch{}}
 const line=text.trim().split(/\r?\n/).find(x=>x.trim())?.trim()||'';
 const sentence=line.match(/^.*?[。！？](?:\s|$)?|^.*?[.!?](?:\s|$)/)?.[0]?.trim()||line;
 return sentence.length>160?sentence.slice(0,159)+'…':sentence;
}
export function TaskTimeline({steps}:{steps:Step[]}){
 const results=steps.filter(s=>s.output||s.error);
 return <>{results.map(s=><div className="handoff" key={s.id}><div><strong>{tr(s.role)} · {s.agent}</strong><span className={'pill '+(s.status==='Succeeded'&&s.output.includes('<acc_result>')?'green':s.status==='Failed'?'red':'amber')}>{tr(s.status==='Succeeded'&&!s.output.includes('<acc_result>')?'Output received — outcome unverified':s.status)}</span></div><p>{handoffSummary(s.error||s.output)}</p><details><summary>{tr('Full output')}</summary><pre>{s.output||s.error}</pre>{s.output&&s.error&&<pre>{s.error}</pre>}{s.session&&<small>{tr('Native session: ')}{s.session}</small>}</details></div>)}{!results.length&&<p>{tr('Waiting for a result.')}</p>}</>;
}
