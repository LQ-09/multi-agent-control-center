"""Explicit real CLI + native resume probe, isolated from ACC task scheduling."""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--backend',required=True);p.add_argument('--state',required=True);p.add_argument('--workspace',required=True);a=p.parse_args()
    sys.path.insert(0,str(Path(a.backend).resolve()))
    from autoswarm import engine
    from autoswarm.records import Records
    records=Records(Path(a.state)/'autoswarm-probe');reports=[]
    def collect(ident):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            values=engine.receive(records,[ident],include_inbox=False)
            if values:return values[0]
            time.sleep(.3)
        return {'outcome':'timeout','error':'Probe-only 120-second deadline; cancellation requested.'}
    for agent in ('codex','claude-code'):
        token='ACC_PROBE_'+uuid.uuid4().hex
        report={'agent':agent,'verified':False};ident=None
        try:
            args=['--sandbox','read-only','--ask-for-approval','never'] if agent=='codex' else ['--tools=','--strict-mcp-config','--mcp-config={"mcpServers":{}}']
            call=engine.start_call(records,agent,'Remember '+token+'. Reply with that exact phrase only. Do not call tools or edit files.',a.workspace,parent=None,return_mode='wait',provider_args=args,delegate_approvals=False)
            ident=call['call_id'];report['initial_call']=ident;first=collect(ident)
            if first.get('outcome')!='completed' or token not in first.get('content',''):
                report['error']=first.get('error') or first.get('kind') or 'Incorrect initial response'
            else:
                call=engine.resume(records,ident,'Repeat the exact phrase I asked you to remember. Do not call tools.',inherit_parent=False,return_mode='wait')
                ident=call['call_id'];report['resume_call']=ident;second=collect(ident)
                report['verified']=second.get('outcome')=='completed' and token in second.get('content','') and bool(first.get('native_session_id')) and first['native_session_id']==second.get('native_session_id')
                if not report['verified']:report['error']=second.get('error') or 'Native resume/recall failed'
        except Exception as exc:report['error']=str(exc)
        finally:
            if ident:
                from swarm_adapter import stop
                try:stop(records,ident)
                except Exception as exc:report.update(verified=False,error=str(exc))
        reports.append(report);print(json.dumps(report,ensure_ascii=False),flush=True)
    raise SystemExit(0 if all(r['verified'] for r in reports) else 1)

if __name__=='__main__':main()
