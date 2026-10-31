"""Copy only these application sources to the user's Windows home via existing SSH trust."""
import base64
import re
import subprocess
import sys
from pathlib import Path
alias=sys.argv[1] if len(sys.argv)>1 else 'worker'
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}',alias):raise SystemExit('Use a configured simple SSH alias')
script="$target = Join-Path $env:USERPROFILE 'AgentControlCenter'; New-Item -ItemType Directory -Force -Path $target | Out-Null; Write-Output $target; python --version; codex --version"
encoded=base64.b64encode(script.encode('utf-16-le')).decode()
opts=['-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8']
subprocess.run(['ssh',*opts,alias,'powershell.exe -NoProfile -NonInteractive -EncodedCommand '+encoded],check=True)
# Only Python source files, no caches, credentials, repositories or session history.
import tempfile,shutil
with tempfile.TemporaryDirectory() as tmp:
    stage=Path(tmp)/'backend';stage.mkdir()
    for src in (Path(__file__).resolve().parents[1]/'backend').glob('*.py'):shutil.copy2(src,stage/src.name)
    subprocess.run(['scp',*opts,'-r',str(stage),alias+':AgentControlCenter/'],check=True)
if '--interactive-worker' in sys.argv[2:]:
    setup="$target = Join-Path $env:USERPROFILE 'AgentControlCenter'; & python (Join-Path $target 'backend/install_interactive_worker.py') --root (Join-Path $target 'state'); exit $LASTEXITCODE"
    encoded=base64.b64encode(setup.encode('utf-16-le')).decode()
    subprocess.run(['ssh',*opts,alias,'powershell.exe -NoProfile -NonInteractive -EncodedCommand '+encoded],check=True)
print('Backend copied. Set the Windows service.py and storage paths in native app Settings; select Live and Test connection.')
