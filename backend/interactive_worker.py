"""Same-host Windows executor. SSH remains the control plane; no TCP listener."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import time
import threading
from core import Store
from agents import run, cleanup
from providers import Providers

MAX_AGE = 15


def session_id():
    if os.name != 'nt':
        raise RuntimeError('Interactive executor requires Windows')
    value = ctypes.c_ulong()
    if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(value)):
        raise RuntimeError('Cannot determine Windows session')
    if value.value == 0:
        raise RuntimeError('Start this worker in the logged-in Windows desktop, not SSH or a service')
    return value.value


def enabled(root):
    return (Path(root) / 'interactive-executor.json').exists()


def heartbeat(store, kind, value=None):
    key = 'executor.' + kind
    with store.transaction():
        if value is not None:
            store.db.execute('INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)',
                             (key, json.dumps(value)))
        row = store.db.execute('SELECT value FROM preferences WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else {}


def fresh(value):
    age = time.time() - value.get('time', 0)
    return 0 <= age < MAX_AGE


def tick(store, profile):
    heartbeat(store, 'controller', {'time': time.time(), 'profile': profile})
    worker = heartbeat(store, 'worker')
    if not fresh(worker) or worker.get('profile') != profile:
        raise RuntimeError('Windows interactive worker is offline or profile differs. Start interactive_worker.py in the Windows desktop, then reconnect ACC. No SSH execution fallback.')
    return {'dispatched': False, 'executor': worker}


def guarded_call(store, profile, op, args=None):
    if op in ('pulse', 'claim'):
        controller = heartbeat(store, 'controller')
        if not fresh(controller) or controller.get('profile') != profile:
            raise RuntimeError('ACC controller heartbeat lost; execution stopped. Reconcile before retry.')
    return store.dispatch({'op': op, 'args': args or {}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--profile', choices=['single', 'split'], default='split')
    args = parser.parse_args()
    sid = session_id()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # OS lock releases on process death. A stale PID file must not allow two executors.
    import msvcrt
    with (root / 'interactive-executor.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        store = Store(root, host='worker' if args.profile == 'single' else None)
        providers = Providers(root)
        marker = root / 'interactive-executor.json'
        heartbeat(store, 'controller', {'time': 0})
        marker.write_text(json.dumps({'profile': args.profile}), encoding='utf-8')
        def beat():
            heartbeat(store, 'worker', {'time': time.time(), 'session_id': sid,
                                       'pid': os.getpid(), 'profile': args.profile})
        def call(op, data=None):
            beat()
            return guarded_call(store, args.profile, op, data)
        stop = threading.Event()
        def keepalive():
            while not stop.wait(3):
                beat()
        thread = threading.Thread(target=keepalive, daemon=True)
        thread.start()
        print('ACC interactive executor ready; session', sid, flush=True)
        try:
            while True:
                beat()
                controller = heartbeat(store, 'controller')
                if fresh(controller) and controller.get('profile') == args.profile:
                    step = call('claim', {'host': 'worker' if args.profile == 'single' else 'windows'})
                    if step:
                        # API keys supplied to the SSH service are memory-only and intentionally not copied.
                        run(step, call, providers=providers)
                time.sleep(1)
        finally:
            stop.set()
            thread.join(timeout=5)
            cleanup()
            heartbeat(store, 'worker', {'time': 0})
            store.close()


if __name__ == '__main__':
    main()
