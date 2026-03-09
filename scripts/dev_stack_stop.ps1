$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $root ".run_logs"
$apiPidFile = Join-Path $logDir "api.pid"
$uiPidFile = Join-Path $logDir "ui.pid"

function Stop-IfRunning([int]$procId) {
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "[maia] Stopped PID $procId"
    } catch {
        Write-Host "[maia] PID $procId not running"
    }
}

if (Test-Path $apiPidFile) {
    $procId = Get-Content $apiPidFile | Select-Object -First 1
    if ($procId -as [int]) { Stop-IfRunning ([int]$procId) }
    Remove-Item $apiPidFile -Force -ErrorAction SilentlyContinue
}

if (Test-Path $uiPidFile) {
    $procId = Get-Content $uiPidFile | Select-Object -First 1
    if ($procId -as [int]) { Stop-IfRunning ([int]$procId) }
    Remove-Item $uiPidFile -Force -ErrorAction SilentlyContinue
}

# Fallback: stop listeners even if PID files are missing.
$listeners = Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    Stop-IfRunning $listener.OwningProcess
}

Write-Host "[maia] Stop routine complete."
