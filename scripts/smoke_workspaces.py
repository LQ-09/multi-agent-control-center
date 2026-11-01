"""Exercise the frozen project's RPC, Git workspace and fake CLI without Python on PATH."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

binary=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='acc-workspace-smoke-') as temp:
    root=Path(temp).resolve();repo=root/'repo';repo.mkdir();bin_dir=root/'bin';bin_dir.mkdir()
    git=shutil.which('git')
    def command(*args):
        subprocess.run([git,'-C',str(repo),*args],check=True,capture_output=True)
    command('init');(repo/'README.md').write_text('Shared project document.');(repo/'source.txt').write_text('original')
    command('add','.')
    command('-c','user.name=ACC smoke','-c','user.email=acc@example.invalid','-c','commit.gpgsign=false','commit','-m','fixture')
    (bin_dir/'git').symlink_to(git)
    fake=bin_dir/'codex'
    fake.write_text('#!'+sys.executable+'''\nimport json,sys
from pathlib import Path
if '--version' in sys.argv:
    print('codex smoke fixture');sys.exit(0)
prompt=sys.stdin.read()
context=json.loads(prompt.split('Bound project context (shared by all adapters):\\n')[1])
assert context['workspace']==str(Path.cwd())
assert context['shared_documents']['README.md']=='Shared project document.'
if 'You are the Execute agent' in prompt:Path('source.txt').write_text('fake CLI change')
result='<acc_result>'+json.dumps(dict(status='succeeded',summary='Simulated CLI verified.',details='Shared context and cwd matched.'))+'</acc_result>'
print(json.dumps(dict(type='item.completed',item=dict(type='agent_message',text=result))))
''')
    fake.chmod(0o755)
    env={**os.environ,'PATH':str(bin_dir)}
    assert shutil.which('python',path=env['PATH']) is None and shutil.which('python3',path=env['PATH']) is None
    proc=subprocess.Popen([str(binary),'--cache',str(root/'state')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    def call(op,args=None):
        proc.stdin.write(json.dumps(dict(op=op,args=args or {}))+'\n');proc.stdin.flush()
        response=json.loads(proc.stdout.readline());assert response['ok'],response
        return response['data']
    try:
        project=call('save_project',dict(name='Smoke project',repo_path=str(repo),documents=['README.md'],rules='Use outputs.'))
        task=call('create',dict(key='smoke',project_id=project['id'],prompt='Simulated workspace edit',acceptance='Fake CLI changes its isolated source',execution_mode='workspace-write'))
        call('control',dict(id=task['id'],action='run',revision=1))
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            snapshot=call('snapshot');state=snapshot['tasks'][0]
            if state['status'] in ('Verifying','Failed','Blocked'):break
            time.sleep(.1)
        assert state['status']=='Verifying',snapshot['steps']
        context=call('project_context',dict(id=task['id']))
        assert (repo/'source.txt').read_text()=='original'
        assert (Path(context['workspace'])/'source.txt').read_text()=='fake CLI change'
        call('control',dict(id=task['id'],action='accept',revision=state['revision']))
        print('PASS: frozen RPC -> registered project -> isolated Git worktree -> shared context -> three fake CLI roles -> acceptance; Python absent from PATH.')
    finally:
        proc.stdin.close()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
        stderr=proc.stderr.read();proc.stderr.close();proc.stdout.close()
        if proc.returncode:raise RuntimeError(stderr)
