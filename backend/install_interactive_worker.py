"""Register a least-privilege, logged-in-user task; no passwords or auto-login."""
import argparse
import base64
from pathlib import Path
import os
import json
import subprocess
import sys

def script(python, worker, root, profile):
    def quote(value): return "'" + str(value).replace("'", "''") + "'"
    arguments = subprocess.list2cmdline([str(worker), '--root', str(root), '--profile', profile])
    return f"""
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$name='ACC-Interactive-Worker'
$user=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute {quote(python)} -Argument {quote(arguments)} -WorkingDirectory {quote(worker.parent)}
$existing=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {{
  if ($existing.Actions.Execute -ne $action.Execute -or $existing.Actions.Arguments -ne $action.Arguments) {{
    throw 'An ACC worker task with different paths exists. Stop and review it before replacing.'
  }}
}} else {{
  $principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
  $trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
  $settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
}}
Start-ScheduledTask -TaskName $name
Write-Output 'Worker launch requested in the logged-in desktop. Reconnect ACC to verify readiness. No password or elevated run level configured.'
"""

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--profile',choices=['single','split'],default='split')
    args=parser.parse_args()
    if os.name!='nt': raise SystemExit('Run this installer on Windows')
    worker=Path(__file__).resolve().with_name('interactive_worker.py')
    # Keep a console for diagnostics; no hidden unbounded log files.
    root=Path(args.root).resolve()
    root.mkdir(parents=True,exist_ok=True)
    # Fail closed even if the scheduled task cannot start (for example, no desktop login).
    (root/'interactive-executor.json').write_text(json.dumps({'profile':args.profile}),encoding='utf-8')
    text=script(sys.executable,worker,root,args.profile)
    encoded=base64.b64encode(text.encode('utf-16-le')).decode()
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],check=True)

if __name__=='__main__': main()
