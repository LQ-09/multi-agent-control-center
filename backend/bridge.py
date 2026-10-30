"""Native broker: one selected authority, local by default, optional SSH profiles."""
import argparse
import base64
import json
import platform
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path
from core import Store, clean
from agents import run, version, cleanup
from history import scan
from providers import Providers, PRESETS
from agent_monitor import AgentMonitor

DEFAULT = {'ssh_alias':'worker','windows_python':'python3','windows_service':'/home/user/agent-control-center/backend/service.py',
    'windows_root':'/home/user/agent-control-center/state','mac_workspace':str(Path.home()),
    'mode':'local','remote_os':'posix','profile':'single'}

def remote_command(config):
    argv=[config['windows_python'],'-u',config['windows_service'],'--root',config['windows_root']]
    if config.get('profile','split')=='single': argv+=['--profile','single']
    if config.get('remote_os','windows')=='posix': return 'exec '+shlex.join(argv)
    def ps(value): return "'"+value.replace("'","''")+"'"
    script="$ProgressPreference = 'SilentlyContinue'; $ErrorActionPreference = 'Stop'; $env:PYTHONIOENCODING = 'utf-8'; & "+' '.join(map(ps,argv))
    return 'powershell.exe -NoProfile -NonInteractive -EncodedCommand '+base64.b64encode(script.encode('utf-16-le')).decode()

class Remote:
    def __init__(self, config):
        target=config['ssh_alias']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}',target): raise ValueError('Use a simple configured SSH host alias')
        self.lock=threading.Lock(); self.lines=queue.Queue(maxsize=8); self.errors=[]
        self.p=subprocess.Popen(['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2',target,remote_command(config)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def read():
            try:
                for line in self.p.stdout: self.lines.put(line)
            finally: self.lines.put(None)
        def errors():
            for line in self.p.stderr: self.errors=(self.errors+[clean(line,500)])[-6:]
        threading.Thread(target=read,daemon=True).start(); threading.Thread(target=errors,daemon=True).start()
    def call(self,op,args=None):
        with self.lock:
            if self.p.poll() is not None: raise RuntimeError('SSH stopped. '+''.join(self.errors))
            self.p.stdin.write(json.dumps({'op':op,'args':args or {}})+'\n'); self.p.stdin.flush()
            try: line=self.lines.get(timeout=25)
            except queue.Empty:
                self.close(); raise TimeoutError('Remote response timed out; no automatic request replay. '+''.join(self.errors))
            if line is None: raise RuntimeError('Remote service disconnected. '+''.join(self.errors))
            result=json.loads(line)
            if not result.get('ok'): raise ValueError(result.get('error','Remote error'))
            return result['data']
    def close(self):
        if self.p.poll() is None: self.p.terminate()

class Bridge:
    def __init__(self,cache):
        self.cache=Path(cache).resolve(); self.cache.mkdir(parents=True,exist_ok=True)
        self.config=dict(DEFAULT)
        path=self.cache/'connection.json'
        if path.exists():
            saved=json.loads(path.read_text())
            if saved.get('mode')=='live' and 'profile' not in saved:
                saved.update(profile='split',remote_os='windows')
            self.config.update(saved)
        env_path=self.cache/'environments.json'
        self.environments=json.loads(env_path.read_text()) if env_path.exists() else []
        self.demo=Store(self.cache/'demo',demo=True)
        self.local=Store(self.cache/'local',host='local')
        self.providers=Providers(self.cache/'local'); self.monitor=AgentMonitor()
        self.remote=None; self.connected=self.config['mode']=='local'; self.info=None
        self.update_pending=False; self.error=None; self.active=False; self.stop=False; self.last_live=None
        self.needs_connect=self.config['mode']=='live'
        self.local_agents={a:version(a) for a in ('codex','claude')}
        self.execution_lock=threading.RLock()
        threading.Thread(target=self.loop,daemon=True).start()
    def call(self,op,args=None):
        if self.config['mode'] in ('demo','local'):
            store=self.demo if self.config['mode']=='demo' else self.local
            return store.dispatch({'op':op,'args':args or {}})
        if not self.connected or not self.remote: raise ValueError(self.error or 'Remote environment is not connected. Use Reconnect to test the saved settings.')
        return self.remote.call(op,args)
    def loop(self):
        while not self.stop:
            try:
                with self.execution_lock:
                    if self.update_pending: pass
                    elif self.config['mode'] in ('demo','local'):
                        if not self.active:
                            s=(self.call('claim',{'host':'mac'}) or self.call('claim',{'host':'windows'})) if self.config['mode']=='demo' else self.call('claim',{'host':'local'})
                            if s: self.start(s,self.config['mode']=='demo')
                    elif self.connected:
                        self.remote.call('tick')
                        if self.config['profile']=='split' and not self.active:
                            s=self.call('claim',{'host':'mac'})
                            if s: self.start(s,False)
            except Exception as e:
                self.error=clean(e,1000)
                if self.config['mode']=='live': self.connected=False
            time.sleep(.6)
    def start(self,s,demo):
        self.active=True
        target=self.demo.dispatch if demo else self.local.dispatch if self.config['mode']=='local' else None
        remote=self.remote; workspace=self.config['mac_workspace']
        def call(op,args=None): return target({'op':op,'args':args or {}}) if target else remote.call(op,args)
        def work():
            try: run(s,call,workspace,demo,self.providers)
            finally: self.active=False
        threading.Thread(target=work,daemon=True).start()
    def idle(self):
        if self.active: raise ValueError('Stop active work before changing environments or providers.')
        snap=self.call('snapshot') if self.config['mode']!='live' or self.connected else self.last_live
        if snap and any(t['status'] in ('Running','Planning','Queued','Blocked') for t in snap['tasks']):
            raise ValueError('Pause/cancel or reconcile pending tasks before changing environments or providers.')
    @staticmethod
    def validate_config(config):
        if set(config)!=set(DEFAULT): raise ValueError('Unknown or missing environment setting')
        if config['mode'] not in ('demo','local','live') or config['profile'] not in ('single','split') or config['remote_os'] not in ('posix','windows'):
            raise ValueError('Invalid environment mode, profile or OS')
        if config['profile']=='split' and config['remote_os']!='windows': raise ValueError('Split profile requires an explicit Windows authority')
        for key,value in config.items():
            if not isinstance(value,str) or not value.strip() or len(value)>1000 or any(c in value for c in '\r\n\x00'): raise ValueError('Invalid setting: '+key)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}',config['ssh_alias']): raise ValueError('Use a simple SSH host alias')
        return config
    def dispatch(self,r):
        # Serialize control changes with claims; never dispatch an old step onto a newly selected authority.
        with self.execution_lock: return self._dispatch(r)
    def _dispatch(self,r):
        op=r.get('op'); args=r.get('args',{})
        if op=='prepare_update':
            if self.config['mode']=='live' and (not self.connected or self.needs_connect):
                raise ValueError('Reconnect the remote environment before updating; task state is unknown.')
            self.idle()
            self.update_pending=True
            return {'ready':True}
        if op=='abort_update':
            self.update_pending=False
            return {'ready':False}
        if self.update_pending and op!='snapshot':
            raise ValueError('Application update in progress; task changes are temporarily locked.')
        if op=='snapshot':
            stale=False
            try:
                if self.needs_connect:
                    self.needs_connect=False; self.dispatch({'op':'connect'})
                data=self.call('snapshot')
                if self.config['mode']=='live': self.last_live=data
            except Exception as e:
                self.connected=False; self.error=clean(e,1000); stale=True
                data=self.last_live or {'tasks':[],'steps':[],'events':[],'artifacts':[],'history':[],'storage':{}}
            return {**data,'mode':self.config['mode'],'connected':self.connected,'stale':stale,'connection':self.config,'error':self.error,
                'environments':self.environments,'providers':data.get('providers',[]) if self.config['mode']=='live' else self.providers.list(),'provider_presets':PRESETS,
                'hosts':{'mac':{'host':platform.node(),'os':platform.system(),'agents':self.local_agents},'windows':self.info},
                'mac_storage':{'managed_bytes':sum(p.stat().st_size for p in self.cache.rglob('*') if p.is_file()),'budget':1_000_000_000,'disk_free':shutil.disk_usage(self.cache).free},
                'capabilities':{'live_profile':'read-only','general_dag':False,'automatic_verification':False,'mcp':False,'artifact_sync':'small-text-only'}}
        if op=='agent_status':
            if self.config['mode']=='demo':return {'hosts':{},'demo':True}
            hosts={}
            if self.config['mode']=='local' or self.config['profile']=='split':
                hosts['local']=self.monitor.snapshot(bool(args.get('refresh')))
            if self.config['mode']=='live':
                if not self.connected:hosts['remote']={'error':'Remote environment is not connected.','agents':{}}
                elif not (self.info or {}).get('agent_controls'):hosts['remote']={'error':'Update the remote worker to v0.6 for account and model controls.','agents':{}}
                else:hosts['remote']=self.call('agent_status',args)
            return {'hosts':hosts}
        if op=='save_agent_defaults':
            if self.config['mode']=='live' and not (self.info or {}).get('agent_controls'):
                raise ValueError('Update the remote worker to v0.6 for account and model controls.')
            return self.call(op,args)
        if op=='save_environment':
            ident=args.get('id',''); name=args.get('name','')
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',ident) or not isinstance(name,str) or not name.strip() or len(name)>80: raise ValueError('Enter a profile ID and name')
            config=self.validate_config(args['config'])
            profiles=[x for x in self.environments if x['id']!=ident]+[{'id':ident,'name':name,'config':config}]
            if len(profiles)>16: raise ValueError('At most 16 saved environments are supported')
            (self.cache/'environments.json').write_text(json.dumps(profiles,indent=2)); self.environments=profiles
            return profiles
        if op=='activate_environment':
            entry=next((e for e in self.environments if e['id']==args['id']),None)
            if entry is None: raise ValueError('Environment profile not found')
            return self.dispatch({'op':'configure','args':entry['config']})
        if op=='configure':
            self.idle()
            new=self.validate_config({**self.config,**args})
            if self.remote: self.remote.close()
            self.remote=None; self.connected=new['mode']=='local'; self.last_live=None; self.info=None; self.error=None
            self.config=new; self.needs_connect=new['mode']=='live'
            (self.cache/'connection.json').write_text(json.dumps(new,indent=2)); return new
        if op=='connect':
            self.needs_connect=False
            if self.active: raise ValueError('A local agent is still active')
            if self.config['mode']!='live': raise ValueError('Select an SSH environment first')
            if self.remote: self.remote.close()
            try:
                self.remote=Remote(self.config); self.info=self.remote.call('hello')
                if self.config['profile']=='split':
                    if self.info['os']!='Windows' or self.info['protocol'] not in (1,2): raise ValueError('Split mode requires a Windows authority')
                elif self.info.get('protocol')!=2 or self.info.get('profile')!='single': raise ValueError('Update the remote backend to v0.3 for single-environment SSH execution')
                self.connected=True; self.error=None; return self.info
            except Exception as e:
                self.connected=False; self.error=clean(e,2000)
                if self.remote: self.remote.close()
                raise
        if op in ('save_provider','set_provider_key'):
            self.idle()
            if self.config['mode']=='live': return self.call(op,args)
            if op=='save_provider': return self.providers.save(args)
            return self.providers.set_key(args['id'],args['key'])
        if op=='scan':
            if self.config['mode']=='demo': raise ValueError('Demo never scans native stores')
            if self.active: raise ValueError('Wait for active work before indexing history')
            if self.config['mode']=='local': return {'local':scan(self.call,'local')}
            if self.config['profile']=='single': return {'remote':self.call('scan')}
            return {'mac':scan(self.call,'mac'),'windows':self.call('scan')}
        if op=='create' and self.config['mode']=='live' and args.get('agent_options') and not (self.info or {}).get('agent_controls'):
            if any(o.get('model') or o.get('effort') for o in args['agent_options']):
                raise ValueError('Update the remote worker to v0.6 for account and model controls.')
        if op=='create' and self.config['mode']!='demo':
            for i,agent in enumerate(args.get('agents',[])):
                if agent.startswith('api:'):
                    if self.config['mode']=='live' and self.config['profile']=='split' and i!=1: raise ValueError('Split-mode local planning/review currently requires Codex or Claude CLI')
                    if self.config['mode']=='local': self.providers.get(agent[4:])
        if op not in ('create','control','artifact'): raise ValueError('Unknown desktop operation')
        return self.call(op,args)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--cache',required=True); a=parser.parse_args(); bridge=Bridge(a.cache)
    try:
        for line in __import__('sys').stdin:
            try:
                if len(line)>100000: raise ValueError('Desktop request too large')
                result=bridge.dispatch(json.loads(line)); response={'ok':True,'data':result}
            except Exception as e: response={'ok':False,'error':clean(e,2000)}
            print(json.dumps(response),flush=True)
    finally:
        bridge.stop=True; cleanup()
        if bridge.remote: bridge.remote.close()
if __name__=='__main__': main()
