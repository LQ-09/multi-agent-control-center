"""Bounded, non-inference account queries. Native authentication remains CLI-owned."""
import concurrent.futures
import datetime
import hashlib
import json
import math
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from agents import CHILDREN, CHILD_LOCK, stop_process


def windows_argv(argv):
    if os.name=='nt' and argv[0].lower().endswith(('.cmd','.bat')):
        return ['cmd.exe','/d','/s','/c',subprocess.list2cmdline(argv)]
    return argv

class JsonProcess:
    def __init__(self, argv, cwd):
        self.p=subprocess.Popen(windows_argv(argv),cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',errors='replace',start_new_session=(os.name!='nt'),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        with CHILD_LOCK:CHILDREN.add(self.p)
        self.lines=queue.Queue(maxsize=256); self.closed=threading.Event(); self.total=0
        def read():
            try:
                while not self.closed.is_set():
                    line=self.p.stdout.readline(262145)
                    if not line: break
                    self.total+=len(line)
                    if len(line)>262144 or self.total>2_000_000: break
                    try:self.lines.put(line,timeout=.5)
                    except queue.Full:break
            finally:
                try:self.lines.put(None,timeout=.5)
                except queue.Full:pass
        threading.Thread(target=read,daemon=True).start()
    def send(self,data):
        self.p.stdin.write(json.dumps(data)+'\n');self.p.stdin.flush()
    def next(self,deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Account query timed out')
        try:line=self.lines.get(timeout=remaining)
        except queue.Empty:raise TimeoutError('Account query timed out')
        if line is None:raise ValueError('CLI account query ended without a supported response')
        try:return json.loads(line)
        except ValueError:return {}
    def request(self,ident,method,params,deadline):
        self.send({'id':ident,'method':method,'params':params})
        while True:
            event=self.next(deadline)
            if event.get('id')==ident:
                if 'error' in event:raise ValueError('CLI account method unavailable: '+method)
                return event.get('result') or {}
    def close(self):
        self.closed.set()
        if self.p.poll() is None:stop_process(self.p)
        with CHILD_LOCK:CHILDREN.discard(self.p)
        for stream in (self.p.stdin,self.p.stdout):
            try:stream.close()
            except (OSError,ValueError):pass

def timestamp(value):
    try:
        if isinstance(value,(int,float)) and not isinstance(value,bool):return datetime.datetime.fromtimestamp(value,datetime.timezone.utc).isoformat()
        if isinstance(value,str):return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).isoformat()
    except (ValueError,OverflowError,OSError):pass
    return None

def meter(label,used,reset,scope=''):
    if isinstance(used,bool) or not isinstance(used,(int,float)) or not math.isfinite(used) or not 0<=used<=100:return None
    return {'label':str(label)[:100],'remaining_percent':round(100-used,1),'resets_at':timestamp(reset),'scope':str(scope)[:100]}

def codex_meters(data):
    buckets=data.get('rateLimitsByLimitId')
    if not isinstance(buckets,dict) or not buckets:buckets={'codex':data.get('rateLimits') or {}}
    rows=[]
    for key,bucket in list(buckets.items())[:32]:
        for field in ('primary','secondary'):
            w=bucket.get(field)
            if not isinstance(w,dict):continue
            duration=w.get('windowDurationMins')
            label=f'{duration} min' if duration else field
            row=meter(label,w.get('usedPercent'),w.get('resetsAt'),bucket.get('limitName') or key)
            if row:rows.append(row)
    return rows

def claude_meters(report):
    limits=(report.get('rate_limits') or {}).get('limits')
    if not isinstance(limits,list):return []
    rows=[]
    for item in limits[:32]:
        scope=item.get('scope') or {}
        label=' / '.join(str((scope.get(k) or {}).get('display_name','')) for k in ('model','surface')).strip(' /')
        row=meter(item.get('kind','usage'),item.get('percent'),item.get('resets_at'),label)
        if row:rows.append(row)
    return rows

def account_tag(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:8] if value else None

def probe_codex(binary):
    result={'source':'Codex account/rateLimits/read','models':[],'meters':[]}
    with tempfile.TemporaryDirectory(prefix='acc-account-') as cwd:
        p=JsonProcess([binary,'app-server','--stdio'],cwd)
        try:
            deadline=time.monotonic()+25
            p.request(1,'initialize',{'clientInfo':{'name':'agent_control_center','version':'0.6.0'}},deadline)
            p.send({'method':'initialized','params':{}})
            account=p.request(2,'account/read',{'refreshToken':False},deadline).get('account') or {}
            result.update(plan=account.get('planType') or account.get('type') or 'unknown',account=account_tag(account.get('email')))
            try:
                config=p.request(3,'config/read',{'includeLayers':False},deadline).get('config') or {}
                result['cli_model']=config.get('model');result['cli_effort']=config.get('model_reasoning_effort')
            except ValueError:pass
            try:
                page=p.request(4,'model/list',{'limit':100},deadline)
                result['models']=[{'id':m['model'],'name':m.get('displayName',m['model']),
                    'efforts':[x['reasoningEffort'] for x in m.get('supportedReasoningEfforts',[])],
                    'default_effort':m.get('defaultReasoningEffort'),'default':m.get('isDefault',False)} for m in page.get('data',[]) if not m.get('hidden')][:100]
            except ValueError:pass
            data=p.request(5,'account/rateLimits/read',{},deadline)
            result['meters']=codex_meters(data)
            result['ordinary_usage_allowed']=data.get('ordinaryUsageAllowed')
            result['status']='ok' if result['meters'] else 'unavailable'
            if not result['meters']:result['reason']='No subscription meters returned; API billing and credits are separate.'
        except (ValueError,TimeoutError,OSError) as e:
            result.update(status='unavailable',reason=str(e)[:200])
        finally:p.close()
    return result

def probe_claude(binary):
    result={'source':'Claude Code /usage','models':[],'meters':[]}
    with tempfile.TemporaryDirectory(prefix='acc-account-') as cwd:
        version=subprocess.run(windows_argv([binary,'--version']),cwd=cwd,capture_output=True,text=True,timeout=8)
        match=re.search(r'(\d+)\.(\d+)\.(\d+)',version.stdout)
        if not match or tuple(map(int,match.groups()))<(2,1,273):
            return {**result,'status':'unavailable','reason':'Claude Code 2.1.273+ is required for structured /usage.'}
        auth=subprocess.run(windows_argv([binary,'auth','status','--json']),cwd=cwd,capture_output=True,text=True,timeout=8)
        try:
            a=json.loads(auth.stdout);result.update(plan=a.get('subscriptionType') or a.get('authMethod') or 'unknown',account=account_tag(a.get('email')))
        except ValueError:pass
        # Built-in /usage, no model prompt, tools, custom hooks, MCP or transcript persistence.
        p=JsonProcess([binary,'-p','/usage','--output-format','stream-json','--verbose','--no-session-persistence','--safe-mode','--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}'],cwd)
        try:
            p.p.stdin.close();deadline=time.monotonic()+25
            while True:
                event=p.next(deadline)
                if event.get('usage_report'):
                    result['meters']=claude_meters(event['usage_report'])
                if event.get('type')=='result':break
            result['status']='ok' if result['meters'] else 'unavailable'
            if not result['meters']:result['reason']='CLI returned no subscription meters. Check Claude /usage and your login or billing type.'
        finally:p.close()
    return result

class AgentMonitor:
    def __init__(self):
        self.lock=threading.Lock();self.rows={};self.started=0;self.refreshing=False
    def snapshot(self,refresh=False):
        with self.lock:
            if not self.refreshing and (not self.started or time.time()-self.started>300 or (refresh and time.time()-self.started>15)):
                self.started=time.time();self.refreshing=True
                threading.Thread(target=self._refresh,daemon=True).start()
            return {'refreshing':self.refreshing,'agents':dict(self.rows)}
    def _refresh(self):
        def one(agent):
            binary=shutil.which(agent)
            try:row=(probe_codex(binary) if agent=='codex' else probe_claude(binary)) if binary else {'status':'unavailable','reason':'CLI not found on this host.','meters':[],'models':[]}
            except Exception as e:row={'status':'unavailable','reason':type(e).__name__+': account query failed','meters':[],'models':[]}
            row['checked_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            with self.lock:self.rows[agent]=row
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(one,('codex','claude')))
        finally:
            with self.lock:self.refreshing=False
