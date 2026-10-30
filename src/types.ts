export type Task = {id:string;title:string;prompt:string;status:string;created:string;revision:number;workspace:string;acceptance:string;demo:number};
export type Step = {model?:string;effort?:string;id:string;task_id:string;position:number;role:string;agent:string;host:string;status:string;output:string;session?:string;error?:string};
export type Event = {event_id:string;task_id:string;step_id?:string;sequence_number:number;agent_type:string;host_id:string;timestamp_utc:string;event_type:string;status:string;output_summary:string};
export type Artifact = {id:string;task_id:string;name:string;sha256:string;size:number;created:string;content?:string};
export type History = {id:string;host:string;agent:string;session:string;timestamp:string;summary:string;source:string;offset:number;hash:string};
export type Connection = {mode:'demo'|'local'|'live';ssh_alias:string;windows_python:string;windows_service:string;windows_root:string;mac_workspace:string;remote_os:'windows'|'posix';profile:'single'|'split'};
export type Provider = {id:string;name:string;base_url:string;model:string;key_env:string;key_ready?:boolean};
export type Environment = {id:string;name:string;config:Connection};
export type AgentInfo = {available:boolean;version?:string;path?:string;error?:string};
export type Snapshot = {agent_defaults?:import("./agent-controls").AgentDefaults;tasks:Task[];steps:Step[];events:Event[];artifacts:Artifact[];history:History[];mode:'demo'|'local'|'live';connected:boolean;stale:boolean;error:string|null;connection:Connection;environments:Environment[];providers:Provider[];provider_presets:Provider[];hosts:{mac:{host:string;os:string;agents:Record<string,AgentInfo>};windows:{host:string;agents:Record<string,AgentInfo>;root:string}|null};storage:{metadata_bytes?:number;metadata_limit?:number;disk_free?:number;root?:string};mac_storage:{managed_bytes:number;budget:number;disk_free:number}};
declare global { interface Window { __TAURI__?:{ core:{invoke<T>(cmd:string,args:unknown):Promise<T>} } } }
export async function rpc<T>(op:string,args:unknown={}):Promise<T> {
  if(!window.__TAURI__) throw new Error('Native bridge unavailable. Open with npm run tauri dev; this is a desktop application.');
  const response=await window.__TAURI__.core.invoke<{ok:boolean;data:T;error?:string}>('rpc',{request:{op,args}});
  if(!response.ok) throw new Error(response.error||'Request failed');
  return response.data;
}
