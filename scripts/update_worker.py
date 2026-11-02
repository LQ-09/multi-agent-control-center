"""Upgrade application code with a retained backup, never native auth or sessions."""
import argparse
import compileall
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

def main():
    p=argparse.ArgumentParser();p.add_argument('--target',required=True);p.add_argument('--state',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    if sys.version_info<(3,10):raise SystemExit('AutoSwarm requires Python 3.10+ in the registered worker.')
    source=Path(__file__).resolve().parents[1]/'backend';target=Path(a.target).resolve();state=Path(a.state).resolve()
    if source.resolve()==(target/'backend').resolve():raise SystemExit('Run the updater from a separate extracted release directory.')
    if not (target/'backend/service.py').is_file():raise SystemExit('Existing backend not found at --target.')
    db=state/'control.sqlite'
    if not db.is_file():raise SystemExit('Existing state database not found; check --state.')
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
        if conn.execute("SELECT 1 FROM tasks WHERE status IN ('Queued','Running','Planning') LIMIT 1").fetchone():
            raise SystemExit('Pause pending/running tasks in ACC, then quit ACC before upgrading.')
        if conn.execute("SELECT 1 FROM steps WHERE status='Running' OR lease IS NOT NULL LIMIT 1").fetchone():
            raise SystemExit('An execution is active or unreconciled; wait for cancellation acknowledgement before upgrading.')
        columns={r[1] for r in conn.execute('PRAGMA table_info(tasks)')}
        if 'login_state' in columns and conn.execute("SELECT 1 FROM tasks WHERE login_state IN ('requested','open','closing') LIMIT 1").fetchone():
            raise SystemExit('Close the ACC login window before upgrading.')
    if a.check:
        print('Preflight passed. Existing worker Python:',sys.executable);return
    backup=target/'backups'/('0.13.0-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True)
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as old, sqlite3.connect(backup/'control.sqlite') as copy:old.backup(copy)
    with tempfile.TemporaryDirectory(prefix='acc-upgrade-',dir=target) as temp:
        stage=Path(temp)/'backend'
        shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        if not compileall.compile_dir(stage,quiet=1):raise SystemExit('New backend did not compile; existing code retained.')
        (target/'backend').rename(backup/'backend')
        try:stage.rename(target/'backend')
        except BaseException:
            (backup/'backend').rename(target/'backend');raise
    print('Worker code upgraded to 0.13.0. Previous code and database backup:',backup)

if __name__=='__main__':main()
