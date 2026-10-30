"""CLI adapters: read-only Codex and tool-free Claude, never a shell prompt executor."""
import json
import atexit
import os
import shutil
import signal
import subprocess
import threading
import queue
import time
from pathlib import Path
from core import clean, uid
from agent_settings import selection

CHILDREN = set()
CHILD_LOCK = threading.Lock()

def cleanup():
    with CHILD_LOCK: children = list(CHILDREN)
    for child in children:
        try: stop_process(child)
        except Exception: pass

atexit.register(cleanup)

def version(agent):
    binary=shutil.which(agent)
    if not binary: return {'available':False,'error':f'{agent} not found on PATH'}
    try:
        p=subprocess.run([binary,'--version'],capture_output=True,text=True,timeout=8)
        return {'available':p.returncode==0,'path':binary,'version':clean(p.stdout.strip() or p.stderr,300)}
    except Exception as e: return {'available':False,'error':clean(e,300)}

def argv(agent, model="", effort=""):
    selection(agent,{"model":model,"effort":effort})
    extra=(["--model",model] if model else [])
    if effort:extra+=(["-c",'model_reasoning_effort="'+effort+'"'] if agent=="codex" else ["--effort",effort])
    binary=shutil.which(agent)
    if not binary: raise ValueError(f'{agent} is not installed or not visible in the background process PATH')
    if agent=='codex':
        return [binary,*extra,'-a','never','exec','--json','--sandbox','read-only','--skip-git-repo-check','-']
    # No shell, filesystem or MCP tools are enabled for this Claude prototype adapter.
    if agent=='claude':
        return [binary,*extra,'-p','--output-format','stream-json','--verbose','--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--permission-mode','dontAsk']
    raise ValueError('Unsupported agent')

def prompt_for(s):
    context='\n\n'.join(x['role']+':\n'+x['output'][:10000] for x in s['context'])
    return (f"You are the {s['role']} agent in a read-only orchestration prototype. Do not modify files, run destructive actions, trade, submit forms, or handle credentials. "
        'Produce a concise useful result, state assumptions and unverified claims. This prototype cannot implement file changes. '
        'If asked to implement, provide a patch proposal and verification plan as text only. '
        'For Plan: outline a short approach. If Acceptance is empty, derive concrete, checkable acceptance criteria from the goal and append them inside <acceptance_criteria>...</acceptance_criteria> (maximum 2000 characters). Separate evidence that can be checked from work this read-only prototype cannot perform. For Execute: answer or analyze using permitted read-only tools. '
        'For Review: inspect supplied results and explain whether the acceptance criteria are satisfied; never claim tests ran without evidence.\n'
        f"Task: {s['task']['prompt']}\nAcceptance: {s['task']['acceptance']}\nPrior handoffs:\n{context}")

def stop_process(p):
    if p.poll() is not None: return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,timeout=8)
    else:
        try: os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError: return
        try: p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError: pass
    try: p.wait(timeout=5)
    except subprocess.TimeoutExpired: raise RuntimeError('Process termination not confirmed')

def run(s, call, mac_workspace=None, demo=False, providers=None):
    common={'step_id':s['id'],'attempt':s['attempt']}; p=None
    def report(text,session=None): call('record',{**common,'message':text,'key':uid(),'session':session})
    try:
        if demo:
            for message in ['Preparing bounded task context…','Checking role and host restrictions…','Producing structured handoff…']:
                state=call('pulse',common)
                if state['stop']: return call('finish',{**common,'output':'','stopped':state['stop'].split()[0]})
                report('[SIMULATED] '+message); time.sleep(.45)
            text={'Plan':'1. Inspect the requested scope.\n2. Analyze on the selected environment.\n3. Review results.\n4. Ask the user to accept the evidence.\n<acceptance_criteria>Simulated workflow produces three handoffs and explicitly identifies all unverified claims; the user reviews the results.</acceptance_criteria>',
                'Execute':'Simulated execution result. No CLI or external command ran.\nThe demo produced this small handoff to demonstrate cross-host ordering.',
                'Review':'The simulated handoff is internally consistent. This demonstrates orchestration only; no real acceptance tests were executed.'}[s['role']]
            return call('finish',{**common,'output':text})
        if s['agent'].startswith('api:'):
            if providers is None: raise ValueError('API provider is unavailable on this execution host')
            ident=s['agent'][4:]; config=providers.get(ident)
            providers.validate_model(config,refresh=True)
            report('Text API request: '+config['name']+' / '+config['model']+'. Only task text and handoffs are sent; no filesystem tools.')
            result=queue.Queue(maxsize=1)
            def request():
                try: result.put((True,providers.complete(ident,prompt_for(s))))
                except Exception as e: result.put((False,e))
            threading.Thread(target=request,daemon=True).start()
            start=time.monotonic()
            while True:
                state=call('pulse',common)
                if state['stop']:
                    return call('finish',{**common,'output':'','stopped':state['stop'].split()[0]})
                if time.monotonic()-start>90: raise TimeoutError('API step timed out; request outcome unknown. No automatic retry.')
                try: ok,value=result.get(timeout=2)
                except queue.Empty: continue
                if not ok: raise value
                return call('finish',{**common,'output':value})
        if s.get('model') or s.get('effort'):
            from agent_monitor import probe_codex, claude_models
            from agent_settings import validate_catalog
            binary=shutil.which(s['agent'])
            if not binary:raise ValueError('CLI not installed on the execution host')
            models=probe_codex(binary).get('models',[]) if s['agent']=='codex' else claude_models(binary)
            validate_catalog(s['agent'],{'model':s.get('model',''),'effort':s.get('effort','')},models)
        cwd=Path(mac_workspace if s['host']=='mac' else s['task']['workspace']).expanduser().resolve()
        if not cwd.is_dir(): raise ValueError('Execution workspace does not exist: '+str(cwd))
        command=argv(s['agent'],s.get('model',''),s.get('effort',''))
        report(json.dumps({'type':'agent.configuration','agent':s['agent'],'model':s.get('model') or 'CLI default','effort':s.get('effort') or 'CLI default'}))
        if os.name=='nt' and command[0].lower().endswith(('.cmd','.bat')):
            # Only the trusted installed CLI shim is passed to cmd; task text is stdin, never argv.
            command=['cmd.exe','/d','/s','/c',subprocess.list2cmdline(command)]
        p=subprocess.Popen(command,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            start_new_session=(os.name!='nt'),creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        with CHILD_LOCK: CHILDREN.add(p)
        p.stdin.write(prompt_for(s).encode()); p.stdin.close()
        lines=queue.Queue(maxsize=128)
        def read():
            try:
                while True:
                    line=p.stdout.readline(65536)
                    if not line: break
                    lines.put(line)
            finally: lines.put(None)
        threading.Thread(target=read,daemon=True).start()
        output=[]; total=0; last_pulse=0; start=time.monotonic(); done=False
        while not done:
            if time.monotonic()-last_pulse>5:
                state=call('pulse',common); last_pulse=time.monotonic()
                if state['stop']:
                    stop_process(p); return call('finish',{**common,'output':'\n'.join(output),'stopped':state['stop'].split()[0]})
            if time.monotonic()-start>600: raise TimeoutError('Ten-minute prototype step limit reached')
            try: line=lines.get(timeout=.25)
            except queue.Empty: continue
            if line is None: done=True; continue
            total+=len(line)
            if total>2_000_000: raise ValueError('Agent log limit reached; stopped instead of accumulating output')
            text=line.decode('utf-8',errors='replace').strip()
            if not text: continue
            try:
                event=json.loads(text); typ=event.get('type','unknown')
                session=event.get('thread_id') or event.get('session_id')
                item=event.get('item',{})
                if typ=='item.completed' and item.get('type')=='agent_message': output.append(clean(item.get('text',''),20000))
                if typ=='result' and event.get('is_error'):raise ValueError('CLI rejected the request: '+clean(event.get('result','Model or account error'),1000))
                if typ=='result' and event.get('result'): output.append(clean(event['result'],20000))
                report(text,session)
            except json.JSONDecodeError: report(text)
        rc=p.wait(timeout=10)
        if rc!=0: raise ValueError(f'{s["agent"]} exited with code {rc}. See redacted timeline.')
        if not output: raise ValueError('CLI finished without a supported final response; parser compatibility needs verification.')
        return call('finish',{**common,'output':'\n'.join(output)[-24000:]})
    except Exception as e:
        if p:
            try: stop_process(p)
            except Exception: pass
        try: call('finish',{**common,'output':'','error':clean(e,2000)})
        except Exception: pass  # Authority loss: lease expiry blocks the task; never replay execution.

    finally:
        if p:
            if p.stdout: p.stdout.close()
            if p.stdin and not p.stdin.closed: p.stdin.close()
            with CHILD_LOCK: CHILDREN.discard(p)
