"""Exercise the actual JSON-lines bridge, without provider requests or native session access."""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

with tempfile.TemporaryDirectory() as cache:
    executable = ([sys.argv[1]] if len(sys.argv)>1 else [sys.executable,'-u',str(Path(__file__).resolve().parents[1]/'backend/bridge.py')])
    proc=subprocess.Popen([*executable,'--cache',cache],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def call(op,args=None):
        proc.stdin.write(json.dumps({'op':op,'args':args or {}})+'\n');proc.stdin.flush()
        r=json.loads(proc.stdout.readline())
        assert r['ok'],r
        return r['data']
    try:
        t=call('create',{'key':'smoke','title':'Read-only orchestration smoke test','prompt':'Review the host boundary','workspace':'C:\\example','acceptance':'Three attributed handoffs; explicit final acceptance.'})
        call('control',{'id':t['id'],'revision':1,'action':'run'})
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            s=call('snapshot')
            if s['tasks'][0]['status']=='Verifying':break
            time.sleep(.2)
        assert s['tasks'][0]['status']=='Verifying',s['tasks']
        assert len(s['artifacts'])==3
        call('control',{'id':t['id'],'revision':s['tasks'][0]['revision'],'action':'accept'})
        assert call('snapshot')['tasks'][0]['status']=='Completed'
        print('PASS: JSON IPC -> SQLite -> Mac plan -> Windows execute -> Mac review -> user acceptance (all agents simulated).')
    finally:
        proc.stdin.close()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
        stderr=proc.stderr.read();proc.stderr.close();proc.stdout.close()
        if proc.returncode:raise RuntimeError(stderr)
