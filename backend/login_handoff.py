"""Explicit human login on the execution host; no credential extraction or copying."""
import os
import subprocess
import time
from urllib.parse import urlsplit
from browser_tools import runtime_root, browser_server, browser_lease, profile_path

def login_origin(url):
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('Login requires an HTTPS website URL without credentials.')
    # Do not persist tokens or callback parameters supplied in page URLs.
    return 'https://'+parts.netloc+'/'

def control_login(store, task, action):
    if task['status']!='Waiting for Login': raise ValueError('Task is not waiting for login.')
    step=store.db.execute("SELECT host FROM steps WHERE task_id=? AND status='Blocked' ORDER BY position LIMIT 1",(task['id'],)).fetchone()
    if not step or (store.host is None and step['host']=='mac'):
        raise ValueError('Login handoff requires a local task or Windows execution host; no cross-host profile transfer.')
    state=task['login_state']
    if action=='login_open':
        if state not in ('waiting','closed','error'): raise ValueError('Login window already requested.')
        state='requested'
    elif state=='open': state='closing'
    else: raise ValueError('Wait for the login window to open before continuing.')
    store.db.execute('UPDATE tasks SET login_state=?,login_error=?,revision=revision+1 WHERE id=?',(state,'',task['id']))
    store.event(task['id'],'browser.'+action,'User requested browser login handoff.' if action=='login_open' else 'User confirmed login; close browser before resuming.')
    return {'status':task['status'],'login_state':state}

# The helper only owns the dedicated profile and opens the approved origin.
# Credentials stay in the browser; no page text, cookies or storage are exported.
LOGIN_SCRIPT = r"""
const readline = require('readline');
const [pkg, profile, channel, url] = process.argv.slice(1);
(async () => {
  const {chromium} = require(pkg);
  const context = await chromium.launchPersistentContext(profile, {channel, headless:false});
  context.on('close', () => process.exit(0));
  const input=readline.createInterface({input:process.stdin});
  input.on('line', async () => { await context.close(); });
  input.on('close', async () => { await context.close(); });
  process.on('SIGTERM', async () => { await context.close(); });
  const page=context.pages()[0] || await context.newPage();
  await page.goto(url, {timeout:30000}).catch(() => {});
})().catch(() => process.exit(1));
"""

class LoginWindow:
    def __init__(self,store,host):
        self.store=store; self.host=host; self.process=None; self.lease=None; self.ident=None; self.closing=0
        # Never replay a login request left open by a dead worker.
        with store.transaction():
            store.db.execute("UPDATE tasks SET login_state='error',login_error='Worker restarted; close any old login window, then open it again.' WHERE login_state IN ('open','closing') AND id IN (SELECT task_id FROM steps WHERE host=?)",(host,))

    def tick(self):
        store=self.store
        if self.process:
            task=store.get_task(self.ident)
            if task['login_state']=='closing' and not self.closing:
                self.closing=time.monotonic()
                try: self.process.stdin.write(b'close\n'); self.process.stdin.flush()
                except (OSError,ValueError): pass
            rc=self.process.poll()
            if rc is None:
                if self.closing and time.monotonic()-self.closing>15: self.close('Login browser did not close; reopen and verify before continuing.')
                return True
            resume=rc==0 and task['login_state']=='closing'
            self._release()
            with store.transaction():
                store.db.execute("UPDATE tasks SET login_state=?,login_error=?,revision=revision+1 WHERE id=?",('closed' if rc==0 else 'error','' if rc==0 else 'Browser could not start or exited unexpectedly. Check Node, browser installation and profile ownership.',self.ident))
                store.event(self.ident,'browser.closed','Login window closed; login success is not inferred.')
            if resume:
                task=store.get_task(self.ident)
                store.control(self.ident,'retry',task['revision'])
            self.ident=None
            return True
        with store.transaction():
            if store.db.execute("SELECT 1 FROM steps WHERE host=? AND status='Running'",(self.host,)).fetchone(): return False
            row=store.db.execute("SELECT DISTINCT t.* FROM tasks t JOIN steps s ON s.task_id=t.id WHERE t.login_state='requested' AND t.archived=0 AND s.host=? AND s.status='Blocked' ORDER BY t.created LIMIT 1",(self.host,)).fetchone()
            if not row: return False
            self.ident=row['id']; url=login_origin(row['login_url'])
            store.db.execute("UPDATE tasks SET login_state='open',revision=revision+1 WHERE id=?",(self.ident,))
        try:
            from task_graph import browser_key
            selected=store.db.execute('SELECT * FROM steps WHERE id=?',(row['login_step'],)).fetchone()
            owner=browser_key(dict(selected)) if selected else 'shared'
            server=browser_server(owner=owner)
            if not server: raise RuntimeError('Install the ACC browser runtime on this execution host first.')
            self.lease=browser_lease(owner); self.lease.__enter__()
            root=runtime_root(); channel=server['args'][server['args'].index('--browser')+1]
            command=[server['command'],'-e',LOGIN_SCRIPT,str(root/'node_modules'/'playwright'),str(profile_path(owner)),channel,url]
            self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
            from agents import CHILDREN,CHILD_LOCK
            with CHILD_LOCK: CHILDREN.add(self.process)
            self.closing=0
        except Exception as exc: self.close(str(exc))
        return True

    def _release(self):
        if self.process:
            from agents import CHILDREN,CHILD_LOCK
            with CHILD_LOCK: CHILDREN.discard(self.process)
            if self.process.stdin: self.process.stdin.close()
            self.process=None
        if self.lease:
            self.lease.__exit__(None,None,None); self.lease=None

    def close(self,error='Controller disconnected; login paused. Open the login window again when connected.'):
        if self.process:
            from agents import stop_process
            stop_process(self.process)
        self._release()
        if self.ident:
            with self.store.transaction():
                self.store.db.execute("UPDATE tasks SET login_state='error',login_error=?,revision=revision+1 WHERE id=?",(error[:500],self.ident))
            self.ident=None
