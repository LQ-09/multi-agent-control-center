param([string]$Target = (Join-Path $env:USERPROFILE 'AgentControlCenter'))
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'ACC-Interactive-Worker'
$action = @($task.Actions)[0]
$python = $action.Execute
$arguments = $action.Arguments
$match = [regex]::Match($arguments, '--root\s+(?:"([^"]+)"|([^\s]+))')
if (!$match.Success) { throw 'Cannot identify the existing worker state directory.' }
$state = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
$source = Split-Path $PSScriptRoot
# Preflight before stopping the registered worker; no global Python/CLI changes.
& $python (Join-Path $PSScriptRoot 'update_worker.py') --target $Target --state $state --check
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. No backend files were replaced.' }
Stop-ScheduledTask -TaskName $task.TaskName
$deadline = (Get-Date).AddSeconds(20)
while ((Get-ScheduledTask -TaskName $task.TaskName).State -eq 'Running') {
    if ((Get-Date) -gt $deadline) { throw 'Worker did not stop. No backend files were replaced.' }
    Start-Sleep -Milliseconds 200
}
try {
    & $python (Join-Path $PSScriptRoot 'update_worker.py') --target $Target --state $state
    if ($LASTEXITCODE -ne 0) { throw 'Worker upgrade failed; inspect the error and retained backup.' }
    & $python (Join-Path $Target 'backend/install_browser.py')
    if ($LASTEXITCODE -ne 0) { throw 'Backend upgraded, browser installation failed. Correct the reported installation error.' }
} finally {
    Start-ScheduledTask -TaskName $task.TaskName
}
Write-Host 'ACC worker 0.13.0 installed. Reconnect the Mac app; then run the real CLI probe below.'
& $python (Join-Path $PSScriptRoot 'verify_swarm.py') --backend (Join-Path $Target 'backend') --state $state --workspace $source
if ($LASTEXITCODE -ne 0) { throw 'Upgrade completed, but real agent verification failed. Keep the printed diagnostics.' }
