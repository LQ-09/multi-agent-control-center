"""Exercise real broker threads and graph joins, using explicitly simulated agents."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
with tempfile.TemporaryDirectory() as cache:
    executable=([sys.argv[1]] if len(sys.argv)>1 else [sys.executable,'-u',str(Path(__file__).resolve().parents[1]/'backend/bridge.py')])
    env=dict(os.environ)
    if len(sys.argv)>1:env['PATH']=cache  # Frozen orchestration must not depend on Python on PATH.
    proc=subprocess.Popen([*executable,'--cache',cache],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    def call(op,args=None):
        proc.stdin.write(json.dumps(dict(op=op,args=args or {}))+'\n');proc.stdin.flush()
        r=json.loads(proc.stdout.readline());assert r['ok'],r;return r['data']
    try:
        call('configure',dict(mode='demo'))
        task=call('create',dict(key='parallel',workflow='adaptive',prompt='Compare two independent research results',workspace=cache,acceptance='Simulated branches overlap and join.'))
        call('control',dict(id=task['id'],action='run',revision=1))
        peak=0;deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            snap=call('snapshot');steps=[s for s in snap['steps'] if s['task_id']==task['id']]
            peak=max(peak,sum(s['status']=='Running' for s in steps))
            state=next(t for t in snap['tasks'] if t['id']==task['id'])
            if state['status'] in ('Completed','Failed','Blocked'):break
            time.sleep(.1)
        assert state['status']=='Completed',snap
        assert peak>=2,('No overlapping execution',peak)
        assert len(steps)==4 and len(snap['artifacts'])==4
        final=next(s for s in steps if s['role']=='Deliver')
        assert len(json.loads(final['dependencies']))==2
        print('PASS: real JSON bridge worker threads -> overlapping simulated branches -> dependency join -> accepted delivery; peak concurrency',peak)
    finally:
        proc.stdin.close()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
        error=proc.stderr.read();proc.stderr.close();proc.stdout.close()
        if proc.returncode:raise RuntimeError(error)
