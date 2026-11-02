"""ACC-owned browser runtime; never changes native CLI configuration or profiles."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

MCP_VERSION = '0.0.84'
BROWSER_TOOLS = ['browser_navigate', 'browser_navigate_back', 'browser_snapshot',
                 'browser_click', 'browser_type', 'browser_fill_form',
                 'browser_select_option', 'browser_press_key', 'browser_wait_for',
                 'browser_tabs', 'browser_close', 'browser_take_screenshot']

def runtime_root():
    return Path.home() / 'AgentControlCenter' / 'browser-runtime'

def browser_server(task_id='default'):
    root = runtime_root()
    cli = root / 'node_modules' / '@playwright' / 'mcp' / 'cli.js'
    node = shutil.which('node')
    if not node or not cli.is_file():
        return None
    profile = hashlib.sha256(str(task_id).encode()).hexdigest()[:24]
    return {'command': node, 'args': [str(cli), '--browser',
            'msedge' if sys.platform == 'win32' else 'chrome',
            '--user-data-dir', str(root / 'profiles' / profile),
            '--output-dir', str(root / 'artifacts' / profile), '--no-webmcp']}

def research_capabilities():
    return {'web_search': 'configured-live', 'web_fetch': 'configured',
            'browser': 'configured-unverified' if browser_server() else 'not-installed',
            'browser_setup': 'python backend/install_browser.py',
            'git': 'installed-unverified' if shutil.which('git') else 'not-installed',
            'api_tools': False}

def codex_browser_args(server):
    if not server:
        return []
    settings = {**server, 'enabled_tools': BROWSER_TOOLS, 'startup_timeout_sec': 30}
    return [part for key, value in settings.items()
            for part in ('-c', 'mcp_servers.acc_browser.' + key + '=' + json.dumps(value))]
