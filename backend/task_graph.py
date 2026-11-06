"""Dependency scheduling and resource ownership. Called under Store transactions."""
import json
from pathlib import Path

MAX_PARALLEL = 3


def dependencies(step, steps):
    if step.get('dependencies'):
        return json.loads(step['dependencies'])
    # Previously saved ordered plans retain their original ordering.
    return [s['id'] for s in steps if s['position'] < step['position']]


def ancestors(step, steps):
    by_id = {s['id']: s for s in steps}
    found = set()
    def visit(s):
        for ident in dependencies(s, steps):
            if ident in by_id and ident not in found:
                found.add(ident)
                visit(by_id[ident])
    visit(step)
    return found


def writable(step, task):
    return (step['role'] in ('Execute', 'Deliver') and step['agent'] == 'codex'
            and task['execution_mode'] == 'workspace-write'
            and step.get('access') != 'read-only')


def browser_key(step):
    return step['id'] if step.get('browser_mode') == 'isolated' else 'shared'


def choose_ready(store, host):
    running = [dict(r) for r in store.db.execute("SELECT * FROM steps WHERE host=? AND status='Running'", (host,))]
    if len(running) >= MAX_PARALLEL:
        return None
    if store.db.execute("SELECT 1 FROM tasks t JOIN steps s ON s.task_id=t.id WHERE s.host=? AND t.login_state IN ('requested','open','closing')", (host,)).fetchone():
        return None
    candidates = store.db.execute("""SELECT s.* FROM steps s JOIN tasks t ON t.id=s.task_id
        WHERE t.archived=0 AND s.host=? AND s.status='Pending'
        AND t.status IN ('Queued','Running','Planning') AND t.pending_rework='' AND t.stop_requested=''
        ORDER BY t.created,s.position""", (host,)).fetchall()
    from browser_tools import browser_server
    has_browser = bool(browser_server())
    for row in candidates:
        s = dict(row)
        task = store.get_task(s['task_id'])
        steps = [dict(r) for r in store.db.execute('SELECT * FROM steps WHERE task_id=?', (s['task_id'],))]
        succeeded = {p['id'] for p in steps if p['status'] == 'Succeeded'}
        if not set(dependencies(s, steps)) <= succeeded:
            continue
        conflict = False
        for other in running:
            other_task = store.get_task(other['task_id'])
            # Legacy invocations retain exclusive execution on this host.
            if task['workflow'] == 'legacy' or other_task['workflow'] == 'legacy':
                conflict = True
            path=Path(task['workspace']).resolve(); other_path=Path(other_task['workspace']).resolve()
            same_workspace = (task['id'] == other_task['id'] or path==other_path or path in other_path.parents or other_path in path.parents)
            if same_workspace and (writable(s, task) or writable(other, other_task)):
                conflict = True
            if has_browser and browser_key(s) == browser_key(other):
                conflict = True
        if not conflict:
            return s
    return None


def context_for(store, step):
    steps = [dict(r) for r in store.db.execute('SELECT * FROM steps WHERE task_id=? ORDER BY position', (step['task_id'],))]
    upstream = ancestors(step, steps)
    # Failed descendant feedback is retained for targeted rework, but unrelated
    # parallel outputs never accidentally become dependencies.
    return [dict(role=s['role'], output=('Node '+s['node_key']+':\n' if s.get('node_key') else '')+s['output'])
            for s in steps if s['output'] and s['id'] != step['id'] and
            ((s['id'] in upstream and s['status'] == 'Succeeded') or
             (step['id'] in ancestors(s, steps) and s['status'] != 'Succeeded'))]


def settle(store, task_id):
    task = store.get_task(task_id)
    steps = [dict(r) for r in store.db.execute('SELECT * FROM steps WHERE task_id=? ORDER BY position', (task_id,))]
    running = any(s['status'] == 'Running' for s in steps)
    if task['stop_requested']:
        return 'Blocked' if running else ('Paused' if task['stop_requested'] == 'pause' else 'Cancelled')
    if task['pending_rework'] and not running:
        targets = set(json.loads(task['pending_rework']))
        affected = [s for s in steps if s['id'] in targets or ancestors(s, steps) & targets]
        # Lost leases/native process outcomes must be reconciled, never replayed.
        if any(s['lease'] is not None or any(x in (s['error'] or '').lower() for x in ('unknown','unconfirmed')) for s in affected):
            return 'Blocked'
        for s in affected:
            store.db.execute("UPDATE steps SET status='Pending',attempt=NULL,lease=NULL,error=NULL WHERE id=?", (s['id'],))
        store.db.execute("UPDATE tasks SET pending_rework='',review_rounds=review_rounds+1 WHERE id=?", (task_id,))
        return settle(store, task_id)
    login_steps=[]
    from core import result_contract
    from login_handoff import login_origin
    for s in steps:
        if s['status']!='Blocked':continue
        try:
            result=result_contract(s['output'],required=True)
            if result.get('reason')=='login_required':login_steps.append((s,login_origin(result.get('login_url',''))))
        except (ValueError,TypeError):pass
    if login_steps:
        chosen=next((item for item in login_steps if item[0]['id']==task['login_step']),login_steps[0])
        state=task['login_state'] if chosen[0]['id']==task['login_step'] and task['login_state'] else 'waiting'
        store.db.execute('UPDATE tasks SET login_step=?,login_url=?,login_state=? WHERE id=?',(chosen[0]['id'],chosen[1],state,task_id))
        return 'Waiting for Login'
    if any(s['status'] == 'Blocked' for s in steps):
        return 'Blocked'
    if any(s['status'] == 'Failed' for s in steps):
        return 'Failed'
    if running:
        return 'Running'
    if steps and all(s['status'] == 'Succeeded' for s in steps) and steps[-1]['role'] == 'Deliver':
        return 'Completed'
    return 'Queued'
