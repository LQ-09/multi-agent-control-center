"""Windows authority over SSH stdio. Disconnect stops owned jobs through lease loss."""
import argparse
import json
import platform
import sys
import threading
from core import Store, clean
from agents import run, version, cleanup
from history import scan
from providers import Providers
from agent_monitor import AgentMonitor

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--root',required=True); parser.add_argument('--profile',choices=['single','split'],default='split'); args=parser.parse_args()
    if args.profile=='split' and platform.system()!='Windows': raise SystemExit('The live authority must run on Windows. Use demo mode on Mac.')
    store=Store(args.root,host='worker' if args.profile=='single' else None); providers=Providers(args.root); active=set(); monitor=AgentMonitor()
    def call(op,args=None): return store.dispatch({'op':op,'args':args or {}})
    for line in sys.stdin:
        try:
            if len(line)>1_000_000: raise ValueError('Request too large')
            req=json.loads(line); op=req.get('op')
            if op=='hello': result={'host':platform.node(),'os':platform.system(),'agents':{a:version(a) for a in ('codex','claude')},'root':str(store.root),'protocol':2,'profile':args.profile,'agent_controls':1,'planned_acceptance':1,'model_catalog':1}
            elif op=='agent_status':result=monitor.snapshot(bool(req.get('args',{}).get('refresh')))
            elif op=='tick':
                s=call('claim',{'host':'worker' if args.profile=='single' else 'windows'}) if len(active)<1 else None
                if s:
                    active.add(s['id'])
                    def work(step):
                        try: run(step,call,providers=providers)
                        finally: active.discard(step['id'])
                    threading.Thread(target=work,args=(s,),daemon=True).start()
                result={'dispatched':bool(s)}
            elif op=='scan': result=scan(call,'worker' if args.profile=='single' else 'windows')
            elif op=='snapshot': result={**store.snapshot(),'providers':providers.list()}
            elif op=='provider_models':result=providers.discover_models(req['args']['config'],req['args'].get('key',''))
            elif op in ('save_provider','set_provider_key'):
                if active or any(t['status'] in ('Running','Planning','Queued','Blocked') for t in store.snapshot()['tasks']): raise ValueError('Stop pending tasks before changing providers')
                result=providers.save_checked(req['args']) if op=='save_provider' else providers.set_key(req['args']['id'],req['args']['key'])
            elif op=='save_agent_defaults':
                for agent in ('codex','claude'):monitor.validate_selection(agent,req['args'][agent])
                result=store.dispatch(req)
            elif op=='create':
                saved=store.agent_defaults();data=req.get('args',{});agents=data.get('agents',saved['roles'])
                options=data.get('agent_options') or [saved.get(a,{}) for a in agents]
                for i,(agent,option) in enumerate(zip(agents,options)):
                    if args.profile=='single' or i==1:monitor.validate_selection(agent,option)
                for agent in req.get('args',{}).get('agents',[]):
                    if agent.startswith('api:'): providers.get(agent[4:])
                result=store.dispatch(req)
            else: result=store.dispatch(req)
            response={'ok':True,'data':result}
        except Exception as e: response={'ok':False,'error':clean(e,2000)}
        print(json.dumps(response),flush=True)
    cleanup()
    # No task is automatically relaunched on reconnect. Running leases expire and become Blocked.

if __name__=='__main__': main()
