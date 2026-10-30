"""Windows authority over SSH stdio. Disconnect stops owned jobs through lease loss."""
import argparse
import json
import platform
import sys
import threading
from core import Store, clean
from agents import run, version, cleanup
from history import scan

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--root',required=True); args=parser.parse_args()
    if platform.system()!='Windows': raise SystemExit('The live authority must run on Windows. Use demo mode on Mac.')
    store=Store(args.root); active=set()
    def call(op,args=None): return store.dispatch({'op':op,'args':args or {}})
    for line in sys.stdin:
        try:
            if len(line)>1_000_000: raise ValueError('Request too large')
            req=json.loads(line); op=req.get('op')
            if op=='hello': result={'host':platform.node(),'os':'Windows','agents':{a:version(a) for a in ('codex','claude')},'root':str(store.root),'protocol':1}
            elif op=='tick':
                s=call('claim',{'host':'windows'}) if len(active)<1 else None
                if s:
                    active.add(s['id'])
                    def work(step):
                        try: run(step,call)
                        finally: active.discard(step['id'])
                    threading.Thread(target=work,args=(s,),daemon=True).start()
                result={'dispatched':bool(s)}
            elif op=='scan': result=scan(call,'windows')
            else: result=store.dispatch(req)
            response={'ok':True,'data':result}
        except Exception as e: response={'ok':False,'error':clean(e,2000)}
        print(json.dumps(response),flush=True)
    cleanup()
    # No task is automatically relaunched on reconnect. Running leases expire and become Blocked.

if __name__=='__main__': main()
