"""ACC prototype domain model. No third-party Python dependencies; no public listener."""
from __future__ import annotations
import hashlib
from contextlib import contextmanager
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

STATES = {'Draft','Queued','Planning','Running','Waiting for Dependency','Waiting for Approval','Paused','Blocked','Failed','Verifying','Completed','Cancelled'}
MAX_DB = 80_000_000
MAX_LOG = 8_000

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())
def digest(text): return hashlib.sha256(text.encode()).hexdigest()
def redact(text):
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[REDACTED PRIVATE KEY]', str(text), flags=re.S)
    text = re.sub(r'(?i)(bearer\s+)[\w.\-]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|password|secret)\s*[=:]\s*["\x27]?)[^\s,"\x27}]+', r'\1[REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[REDACTED]', text)
    return text

def clean(value, limit=12000): return redact(str(value))[:limit]

class Store:
    def __init__(self, root, demo=False, host=None):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.host = host
        self.demo = demo; self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root/'control.sqlite', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON'); self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL'); self.db.execute('PRAGMA journal_size_limit=4194304')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, title TEXT NOT NULL, prompt TEXT NOT NULL, status TEXT NOT NULL,
            created TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, workspace TEXT NOT NULL, acceptance TEXT NOT NULL, demo INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS steps(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), position INTEGER NOT NULL,
            role TEXT NOT NULL, agent TEXT NOT NULL, host TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
            attempt TEXT, session TEXT, lease REAL, error TEXT, UNIQUE(task_id,position));
        CREATE TABLE IF NOT EXISTS events(sequence_number INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
            task_id TEXT, step_id TEXT, agent_type TEXT NOT NULL, host_id TEXT NOT NULL, native_session_id TEXT,
            timestamp_utc TEXT NOT NULL, event_type TEXT NOT NULL, status TEXT NOT NULL, input_summary TEXT NOT NULL,
            output_summary TEXT NOT NULL, artifact_references TEXT NOT NULL DEFAULT '[]', source_log_reference TEXT,
            UNIQUE(event_id));
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), step_id TEXT,
            name TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL, created TEXT NOT NULL, content TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS commands(key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, result TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY, host TEXT NOT NULL, agent TEXT NOT NULL, session TEXT,
            timestamp TEXT NOT NULL, summary TEXT NOT NULL, source TEXT NOT NULL, offset INTEGER NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cursors(source TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, offset INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS event_task ON events(task_id,sequence_number);
        CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Events are append-only'); END;
        ''')
        self.db.commit()
    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
    def close(self): self.db.close()
    def size(self): return sum(p.stat().st_size for p in self.root.glob('*') if p.is_file())
    def reserve(self):
        # Leave headroom for cancellation and final control records. Never evict unsynced records.
        if self.size() > MAX_DB: raise ValueError('Prototype metadata quota reached; new work is blocked. Export/retain data before cleanup.')
    def event(self, task, kind, message, step=None, status=None, event_id=None):
        row = self.db.execute('SELECT status FROM tasks WHERE id=?',(task,)).fetchone() if task else None
        self.db.execute('INSERT OR IGNORE INTO events(event_id,task_id,step_id,agent_type,host_id,native_session_id,timestamp_utc,event_type,status,input_summary,output_summary) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (event_id or uid(),task,step['id'] if step else None,step['agent'] if step else 'system',step['host'] if step else (self.host or 'windows'),step.get('session') if step else None,now(),kind,status or (row['status'] if row else 'Imported'),'',clean(message,MAX_LOG)))
    def get_task(self, ident):
        row=self.db.execute('SELECT * FROM tasks WHERE id=?',(ident,)).fetchone()
        if row is None: raise ValueError('Task not found')
        return dict(row)
    def create(self, data):
        title=str(data.get('title','')).strip(); prompt=str(data.get('prompt','')).strip()
        workspace=str(data.get('workspace','')).strip(); acceptance=str(data.get('acceptance','')).strip()
        if not title or not prompt or not acceptance: raise ValueError('Title, task brief and acceptance criteria are required.')
        if len(prompt)>12000 or len(title)>160 or len(acceptance)>2000: raise ValueError('Task input is too large.')
        if not workspace or any(c in workspace for c in '\r\n\x00'): raise ValueError('An explicit execution workspace is required.')
        agents=data.get('agents',['codex','codex','claude'])
        if len(agents)!=3 or any(not isinstance(a,str) or (a not in ('codex','claude') and not re.fullmatch(r'api:[a-z][a-z0-9_-]{0,39}',a)) for a in agents): raise ValueError('Choose supported agents for all three roles.')
        key=data.get('key'); fingerprint=digest(json.dumps(data,sort_keys=True))
        if not key: raise ValueError('Idempotency key required')
        with self.transaction():
            previous=self.db.execute('SELECT * FROM commands WHERE key=?',(key,)).fetchone()
            if previous:
                if previous['request_hash']!=fingerprint: raise ValueError('Idempotency key payload conflict')
                return json.loads(previous['result'])
            self.reserve(); ident=uid()
            self.db.execute('INSERT INTO tasks(id,title,prompt,status,created,workspace,acceptance,demo) VALUES(?,?,?,?,?,?,?,?)',
                (ident,clean(title),clean(prompt),'Draft',now(),workspace,clean(acceptance),int(self.demo)))
            for pos,(role,host) in enumerate([('Plan',self.host or 'mac'),('Execute',self.host or 'windows'),('Review',self.host or 'mac')]):
                self.db.execute('INSERT INTO steps(id,task_id,position,role,agent,host,status) VALUES(?,?,?,?,?,?,?)',(uid(),ident,pos,role,agents[pos],host,'Pending'))
            self.event(ident,'task.created','Task saved. Execution requires explicit Run. Read-only agent tools in this prototype.')
            result={'id':ident}; self.db.execute('INSERT INTO commands VALUES(?,?,?)',(key,fingerprint,json.dumps(result)))
            return result
    def control(self, ident, action, revision):
        with self.transaction():
            t=self.get_task(ident)
            if t['revision']!=revision: raise ValueError('Task changed; refresh before applying this action.')
            active=self.db.execute("SELECT * FROM steps WHERE task_id=? AND status='Running'",(ident,)).fetchone()
            if action=='run':
                if t['status'] not in ('Draft','Paused'): raise ValueError('Only draft or paused tasks can be started.')
                if active: raise ValueError('Previous process is still stopping.')
                status='Queued'
            elif action in ('pause','cancel'):
                if t['status'] in ('Completed','Cancelled'): raise ValueError('Task is terminal.')
                status='Blocked' if active else ('Paused' if action=='pause' else 'Cancelled')
                if active: self.db.execute('UPDATE steps SET error=? WHERE id=?',(action+' requested',active['id']))
            elif action=='accept':
                if t['status']!='Verifying': raise ValueError('All agent steps must finish before acceptance.')
                status='Completed'
                self.event(ident,'verification.accepted','User explicitly accepted the current read-only result against: '+t['acceptance'])
            else: raise ValueError('Unsupported action')
            self.db.execute('UPDATE tasks SET status=?,revision=revision+1 WHERE id=?',(status,ident))
            self.event(ident,'task.'+action,'Stop requested; awaiting worker acknowledgment.' if active else 'Task '+status.lower(),status=status)
            return {'status':status}
    def claim(self, host):
        if host not in ((self.host,) if self.host else ('mac','windows')): raise ValueError('Unknown host')
        with self.transaction():
            self.reserve()
            # A fixed, inspectable linear DAG in the prototype. General plan DAGs remain a later phase.
            s=self.db.execute("""SELECT s.* FROM steps s JOIN tasks t ON t.id=s.task_id
            WHERE s.host=? AND s.status='Pending' AND t.status IN ('Queued','Running','Planning')
            AND NOT EXISTS (SELECT 1 FROM steps p WHERE p.task_id=s.task_id AND p.position<s.position AND p.status!='Succeeded')
            ORDER BY t.created,s.position LIMIT 1""",(host,)).fetchone()
            if not s: return None
            s=dict(s); s['attempt']=uid(); s['lease']=time.time()+45; s['status']='Running'
            self.db.execute("UPDATE steps SET status='Running',attempt=?,lease=?,error=NULL WHERE id=?",(s['attempt'],s['lease'],s['id']))
            status='Planning' if s['position']==0 else 'Running'
            self.db.execute('UPDATE tasks SET status=?,revision=revision+1 WHERE id=?',(status,s['task_id']))
            self.event(s['task_id'],'step.started',f"{s['role']} started on {host}; {s['agent']} read-only profile.",s,status)
            t=self.get_task(s['task_id']); s['task']=t
            s['context']=[dict(r) for r in self.db.execute("SELECT role,output FROM steps WHERE task_id=? AND status='Succeeded' ORDER BY position",(s['task_id'],))]
            return s
    def check_attempt(self, step_id, attempt):
        s=self.db.execute('SELECT * FROM steps WHERE id=?',(step_id,)).fetchone()
        if not s or s['attempt']!=attempt or s['status']!='Running': raise ValueError('Stale or unknown attempt')
        return dict(s)
    def pulse(self, step_id, attempt):
        with self.transaction():
            s=self.check_attempt(step_id,attempt)
            if s['lease'] < time.time(): raise ValueError('Execution lease expired; stop and reconcile')
            self.db.execute('UPDATE steps SET lease=? WHERE id=?',(time.time()+45,step_id))
            return {'stop':s['error'] if s['error'] in ('pause requested','cancel requested') else None}
    def record(self, step_id, attempt, message, key, session=None):
        with self.transaction():
            s=self.check_attempt(step_id,attempt)
            if s['lease']<time.time(): raise ValueError('Stale lease')
            self.reserve()
            if session:
                self.db.execute('UPDATE steps SET session=? WHERE id=?',(clean(session,160),step_id)); s['session']=clean(session,160)
            self.event(s['task_id'],'agent.output',message,s,event_id=key)
            return True
    def finish(self, step_id, attempt, output, error=None, stopped=None):
        with self.transaction():
            s=self.check_attempt(step_id,attempt)
            if s['lease']<time.time(): raise ValueError('Expired attempt cannot publish a result')
            if s['error'] in ('pause requested','cancel requested') and not stopped: stopped=s['error'].split()[0]
            if stopped:
                status='Paused' if stopped=='pause' else 'Cancelled'; step_status='Pending' if stopped=='pause' else 'Cancelled'
            elif error: status='Failed'; step_status='Failed'
            else:
                step_status='Succeeded'; status='Verifying' if s['position']==2 else 'Queued'
                content=clean(output,24000)
                if not content.strip(): raise ValueError('Empty output cannot satisfy the step contract')
                self.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)',(uid(),s['task_id'],step_id,s['role'].lower()+'-handoff.md',digest(content),len(content.encode()),now(),content))
            self.db.execute('UPDATE steps SET status=?,output=?,error=?,lease=NULL WHERE id=?',(step_status,clean(output,24000),clean(error or '',2000),step_id))
            self.db.execute('UPDATE tasks SET status=?,revision=revision+1 WHERE id=?',(status,s['task_id']))
            self.event(s['task_id'],'step.finished',error or ('Stopped at user request.' if stopped else 'Result stored with SHA-256. CLI success is not task acceptance.'),s,status)
            return {'status':status}
    def expire(self):
        with self.transaction():
            for row in self.db.execute("SELECT * FROM steps WHERE status='Running' AND lease<?",(time.time(),)).fetchall():
                s=dict(row)
                self.db.execute("UPDATE steps SET status='Blocked',error='Lease expired; execution outcome unknown' WHERE id=?",(s['id'],))
                self.db.execute("UPDATE tasks SET status='Blocked',revision=revision+1 WHERE id=?",(s['task_id'],))
                self.event(s['task_id'],'lease.expired','No automatic retry: reconcile the previous process before further work.',s,'Blocked')
    def snapshot(self):
        self.expire()
        with self.lock:
            return {'tasks':[dict(r) for r in self.db.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 200')],
                'steps':[dict(r) for r in self.db.execute('SELECT * FROM steps ORDER BY position LIMIT 1000')],
                'events':[dict(r) for r in self.db.execute('SELECT * FROM events ORDER BY sequence_number DESC LIMIT 160')][::-1],
                'artifacts':[dict(r) for r in self.db.execute('SELECT id,task_id,step_id,name,sha256,size,created FROM artifacts ORDER BY created DESC LIMIT 200')],
                'storage':{'metadata_bytes':self.size(),'metadata_limit':MAX_DB,'disk_free':shutil.disk_usage(self.root).free,'root':str(self.root)},
                'history':[dict(r) for r in self.db.execute('SELECT * FROM history ORDER BY timestamp DESC LIMIT 100')]}
    def artifact(self, ident):
        with self.lock:
            row=self.db.execute('SELECT * FROM artifacts WHERE id=?',(ident,)).fetchone()
            if not row: raise ValueError('Artifact not found')
            return dict(row)
    def import_batch(self, source, fingerprint, offset, records):
        with self.transaction():
            self.reserve()
            for r in records:
                self.db.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?,?,?,?,?,?)',(r['id'],r['host'],r['agent'],r.get('session'),r['timestamp'],clean(r['summary'],2000),source,r['offset'],r['hash']))
            self.db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?,?)',(source,fingerprint,offset))
        return {'records':len(records),'offset':offset}
    def cursor(self, source):
        with self.lock:
            row=self.db.execute('SELECT * FROM cursors WHERE source=?',(source,)).fetchone()
            return dict(row) if row else None
    def dispatch(self, r):
        op=r.get('op'); a=r.get('args',{})
        if op=='snapshot': return self.snapshot()
        if op=='create': return self.create(a)
        if op=='control': return self.control(a['id'],a['action'],a['revision'])
        if op=='claim': return self.claim(a['host'])
        if op=='pulse': return self.pulse(a['step_id'],a['attempt'])
        if op=='record': return self.record(**a)
        if op=='finish': return self.finish(**a)
        if op=='artifact': return self.artifact(a['id'])
        if op=='cursor': return self.cursor(a['source'])
        if op=='import_batch': return self.import_batch(**a)
        raise ValueError('Unknown service operation')
