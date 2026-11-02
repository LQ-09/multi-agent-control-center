"""Install the pinned MCP runtime on the execution host, without CLI config edits."""
import os
import shutil
import subprocess
from browser_tools import MCP_VERSION, runtime_root, browser_server

def main():
    npm = shutil.which('npm')
    if not npm or not shutil.which('node'):
        raise SystemExit('Install Node.js 18+ on this execution host first, then retry.')
    root = runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    command = [npm, 'install', '--prefix', str(root), '--no-audit', '--no-fund',
               '--save-exact', '@playwright/mcp@' + MCP_VERSION]
    if os.name == 'nt' and npm.lower().endswith(('.cmd', '.bat')):
        command = ['cmd.exe', '/d', '/s', '/c', subprocess.list2cmdline(command)]
    subprocess.run(command, check=True, timeout=300)
    server = browser_server()
    subprocess.run([server['command'], server['args'][0], '--help'], check=True, timeout=15,
                   stdout=subprocess.DEVNULL)
    print('MCP runtime installed. Requires Microsoft Edge on Windows or Chrome on macOS/Linux.')
    print('Reconnect ACC and run a browser task to verify launch and site access. Login/CAPTCHA remain manual.')

if __name__ == '__main__':
    main()
