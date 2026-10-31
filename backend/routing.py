"""Pin each submission before RPC: an uncertain remote create must never replay locally."""
import json
from pathlib import Path, PureWindowsPath
from core import digest, validate_execution_workspace

class Routing:
    def __init__(self, store):
        self.store=store
        with store.transaction():
            store.db.execute('CREATE TABLE IF NOT EXISTS submission_routes(key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, authority TEXT NOT NULL, payload TEXT NOT NULL)')

    def submission(self, data, config, connected):
        key=data.get('key')
        if not key: raise ValueError('Idempotency key required')
        fingerprint=digest(json.dumps(data,sort_keys=True))
        authority='remote:'+config['ssh_alias']+':'+config['windows_root']
        with self.store.transaction():
            row=self.store.db.execute('SELECT * FROM submission_routes WHERE key=?',(key,)).fetchone()
            if row:
                if row['fingerprint']!=fingerprint: raise ValueError('Idempotency key payload conflict')
                if row['authority'] not in ('local',authority): raise ValueError('Submission belongs to another environment')
                return row['authority']=='local',json.loads(row['payload'])
            local=not connected
            payload=dict(data)
            if local:
                if data.get('host_requirement','portable')!='portable': raise ValueError('This task requires Windows; reconnect before submitting.')
                workspace=data.get('fallback_workspace') or config['mac_workspace']
                if PureWindowsPath(workspace).drive or not Path(workspace).is_absolute() or not Path(workspace).is_dir():
                    raise ValueError('Offline fallback needs an existing absolute local project directory.')
                validate_execution_workspace(str(Path(workspace).resolve()))
                if any(a not in ('codex','claude') for a in data.get('agents',['codex']*3)):
                    raise ValueError('Remote API credentials are not copied to the Mac fallback. Select local CLI agents.')
                payload['workspace']=str(Path(workspace).resolve())
            else: payload['routing']='windows-first'
            self.store.reserve()
            self.store.db.execute('INSERT INTO submission_routes VALUES(?,?,?,?)',(key,fingerprint,'local' if local else authority,json.dumps(payload)))
            return local,payload

    def owns(self, op, ident):
        table='artifacts' if op in ('artifact','artifact_versions') else 'tasks'
        with self.store.lock:
            return self.store.db.execute('SELECT 1 FROM '+table+' WHERE id=?',(ident,)).fetchone() is not None
