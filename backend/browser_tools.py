"""ACC-owned browser runtime; never changes native CLI configuration or profiles."""
import hashlib
import json
import shutil
import sys
import os
from contextlib import contextmanager
from pathlib import Path

MCP_VERSION = '0.0.84'
BROWSER_TOOLS = ['browser_navigate', 'browser_navigate_back', 'browser_snapshot',
                 'browser_click', 'browser_type', 'browser_fill_form',
                 'browser_select_option', 'browser_press_key', 'browser_wait_for',
                 'browser_tabs', 'browser_close', 'browser_take_screenshot']

def runtime_root():
    return Path.home() / 'AgentControlCenter' / 'browser-runtime'

def profile_path(owner='shared'):
    return runtime_root() / 'profiles' / ('shared' if owner=='shared' else hashlib.sha256(str(owner).encode()).hexdigest()[:24])

def browser_server(task_id='default', owner='shared'):
    root = runtime_root()
    cli = root / 'node_modules' / '@playwright' / 'mcp' / 'cli.js'
    node = shutil.which('node')
    if not node or not cli.is_file():
        return None
    profile = hashlib.sha256(str(task_id).encode()).hexdigest()[:24]
    return {'command': node, 'args': [str(cli), '--browser',
            'msedge' if sys.platform == 'win32' else 'chrome',
            '--user-data-dir', str(profile_path(owner)),
            '--output-dir', str(root / 'artifacts' / profile), '--no-webmcp', '--headless']}

@contextmanager
def browser_lease(owner='shared'):
    """One owner across workers/authorities; never share a live profile."""
    root=runtime_root(); root.mkdir(parents=True,exist_ok=True)
    name='browser.lock' if owner=='shared' else 'browser-'+hashlib.sha256(str(owner).encode()).hexdigest()[:24]+'.lock'
    with (root/name).open('a+b') as lock:
        if lock.tell()==0: lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('ACC browser is in use by another worker or login window; retry after it closes.')
        try: yield
        finally:
            lock.seek(0)
            if os.name=='nt': msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(lock.fileno(),fcntl.LOCK_UN)

def research_capabilities():
    return {'web_search': 'configured-live', 'web_fetch': 'configured',
            'browser': 'configured-unverified' if browser_server() else 'not-installed',
            'browser_setup': 'python backend/install_browser.py',
            'git': 'installed-unverified' if shutil.which('git') else 'not-installed',
            'api_tools': False, 'browser_mode':'headless', 'browser_profile':'shared',
            'login_handoff': True}

def codex_browser_args(server):
    if not server:
        return []
    settings = {**server, 'enabled_tools': BROWSER_TOOLS, 'startup_timeout_sec': 30}
    return [part for key, value in settings.items()
            for part in ('-c', 'mcp_servers.acc_browser.' + key + '=' + json.dumps(value))]
