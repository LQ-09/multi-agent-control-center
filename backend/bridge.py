"""Mac transport broker. Agent sandboxes do not own the SSH connection."""
import argparse
import base64
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from core import Store, clean
from agents import run, version, cleanup
from history import scan

class Remote:
    def __init__(self, config):
        target=config['ssh_alias']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}',target): raise ValueError('Use a simple configured SSH host alias')
        def ps(value): return "'"+value.replace("'","''")+"'"
        script=("$ProgressPreference = 'SilentlyContinue'; $ErrorActionPreference = 'Stop'; "
            "$env:PYTHONIOENCODING = 'utf-8'; "
            f"& {ps(config['windows_python'])} -u {ps(config['windows_service'])} --root {ps(config['windows_root'])}")
        encoded=base64.b64encode(script.encode('utf-16-le')).decode()
        self.lock=threading.Lock(); self.lines=queue.Queue(maxsize=8); self.errors=[]
        self.p=subprocess.Popen(['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2',target,
            'powershell.exe -NoProfile -NonInteractive -EncodedCommand '+encoded],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',bufsize=1)
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
                self.close(); raise TimeoutError('Windows response timed out; no automatic request replay. '+''.join(self.errors))
            if line is None: raise RuntimeError('Windows service disconnected. '+''.join(self.errors))
            result=json.loads(line)
            if not result.get('ok'): raise ValueError(result.get('error','Remote error'))
            return result['data']
    def close(self):
        if self.p.poll() is None: self.p.terminate()

class Bridge:
    def __init__(self,cache):
        self.cache=Path(cache).resolve(); self.cache.mkdir(parents=True,exist_ok=True)
        self.config={'ssh_alias':'my-worker','windows_python':'python','windows_service':r'C:\Users\Administrator\AgentControlCenter\backend\service.py',
            'windows_root':r'C:\Users\Administrator\AgentControlCenter\state','mac_workspace':str(Path.home()),'mode':'demo'}
        path=self.cache/'connection.json'
        if path.exists(): self.config.update(json.loads(path.read_text()))
        self.demo=Store(self.cache/'demo',demo=True); self.remote=None; self.connected=False; self.info=None
        self.error=None; self.active=False; self.stop=False; self.last_live=None
        self.needs_connect=self.config['mode']=='live'
        self.local_agents={a:version(a) for a in ('codex','claude')}
        threading.Thread(target=self.loop,daemon=True).start()
    def call(self,op,args=None):
        if self.config['mode']=='demo': return self.demo.dispatch({'op':op,'args':args or {}})
        if not self.connected or not self.remote: raise ValueError(self.error or 'Windows is not connected. Use Reconnect to test the saved settings.')
        return self.remote.call(op,args)
    def loop(self):
        while not self.stop:
            try:
                if self.config['mode']=='demo':
                    if not self.active:
                        s=self.call('claim',{'host':'mac'}) or self.call('claim',{'host':'windows'})
                        if s: self.start(s,True)
                elif self.connected:
                    self.remote.call('tick')
                    if not self.active:
                        s=self.call('claim',{'host':'mac'})
                        if s: self.start(s,False)
            except Exception as e:
                self.error=clean(e,1000)
                if self.config['mode']=='live': self.connected=False
            time.sleep(.6)
    def start(self,s,demo):
        self.active=True
        # Bind the authority for this attempt; switching connection during a run is forbidden.
        target=self.demo.dispatch if demo else None; remote=self.remote
        def call(op,args=None): return target({'op':op,'args':args or {}}) if demo else remote.call(op,args)
        def work():
            try: run(s,call,self.config['mac_workspace'],demo)
            finally: self.active=False
        threading.Thread(target=work,daemon=True).start()
    def dispatch(self,r):
        op=r.get('op'); args=r.get('args',{})
        if op=='snapshot':
            stale=False
            try:
                if self.needs_connect:
                    self.needs_connect=False
                    self.dispatch({'op':'connect'})
                data=self.call('snapshot')
                if self.config['mode']=='live': self.last_live=data
            except Exception as e:
                self.connected=False; self.error=clean(e,1000); stale=True
                data=self.last_live or {'tasks':[],'steps':[],'events':[],'artifacts':[],'history':[],'storage':{}}
            data={**data,'mode':self.config['mode'],'connected':self.connected,'stale':stale,'connection':self.config,'error':self.error,
                'hosts':{'mac':{'host':platform.node(),'agents':self.local_agents},'windows':self.info},
                'mac_storage':{'managed_bytes':sum(p.stat().st_size for p in self.cache.rglob('*') if p.is_file()),'budget':1_000_000_000,'disk_free':shutil.disk_usage(self.cache).free},
                'capabilities':{'live_profile':'read-only','general_dag':False,'automatic_verification':False,'mcp':False,'artifact_sync':'small-text-only'}}
            return data
        if op=='configure':
            if self.active: raise ValueError('Stop active work before changing the connection.')
            snap=self.call('snapshot') if self.config['mode']=='demo' or self.connected else self.last_live
            if snap and any(t['status'] in ('Running','Planning','Queued','Blocked') for t in snap['tasks']):
                raise ValueError('Pause/cancel or reconcile pending tasks before changing mode.')
            allowed=set(self.config)
            if set(args)-allowed: raise ValueError('Unknown configuration field')
            new={**self.config,**args}
            if new['mode'] not in ('demo','live'): raise ValueError('Invalid mode')
            for key,value in new.items():
                if not isinstance(value,str) or not value.strip() or len(value)>1000 or '\n' in value or '\x00' in value: raise ValueError('Invalid connection setting: '+key)
            if self.remote: self.remote.close()
            self.remote=None; self.connected=False; self.last_live=None; self.info=None; self.error=None
            self.config=new; self.needs_connect=new['mode']=='live'
            (self.cache/'connection.json').write_text(json.dumps(new,indent=2)); return new
        if op=='connect':
            self.needs_connect=False
            if self.active: raise ValueError('A local agent is still active')
            if self.config['mode']!='live': raise ValueError('Select live mode first')
            if self.remote: self.remote.close()
            try:
                self.remote=Remote(self.config); self.info=self.remote.call('hello')
                if self.info['os']!='Windows' or self.info['protocol']!=1: raise ValueError('Incompatible authority')
                self.connected=True; self.error=None; return self.info
            except Exception as e:
                self.connected=False; self.error=clean(e,2000)
                if self.remote: self.remote.close()
                raise
        if op=='scan':
            if self.config['mode']!='live' or not self.connected: raise ValueError('History import requires a live Windows authority; demo never scans native stores.')
            if self.active: raise ValueError('Wait for active work before indexing history.')
            return {'mac':scan(self.call,'mac'),'windows':self.remote.call('scan')}
        if op not in ('create','control','artifact'): raise ValueError('Unknown desktop operation')
        return self.call(op,args)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--cache',required=True); a=parser.parse_args(); bridge=Bridge(a.cache)
    try:
        for line in sys.stdin:
            try:
                if len(line)>100000: raise ValueError('Desktop request too large')
                result=bridge.dispatch(json.loads(line)); response={'ok':True,'data':result}
            except Exception as e: response={'ok':False,'error':clean(e,2000)}
            print(json.dumps(response),flush=True)
    finally:
        bridge.stop=True
        cleanup()
        if bridge.remote: bridge.remote.close()
if __name__=='__main__': main()
