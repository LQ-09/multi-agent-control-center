"""Build the private runtime shipped inside the app; never bundle user environments."""
import subprocess
import sys
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
    '--name', 'acc-backend', '--distpath', str(root/'build/runtime'),
    '--workpath', str(root/'build/pyinstaller'), '--specpath', str(root/'build'),
    '--paths', str(root/'backend'), str(root/'backend/bridge.py'),
], check=True, cwd=root, env={**os.environ, 'PYINSTALLER_CONFIG_DIR': str(root/'build/pyinstaller-cache')})

subprocess.run([sys.executable, str(root/'scripts/collect_licenses.py')], check=True, cwd=root)
