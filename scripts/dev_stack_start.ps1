param(
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $root ".run_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$apiPidFile = Join-Path $logDir "api.pid"
$uiPidFile = Join-Path $logDir "ui.pid"
$apiOut = Join-Path $logDir "api-dev.log"
$apiErr = Join-Path $logDir "api-dev.err.log"
$uiOut = Join-Path $logDir "ui-dev.log"
$uiErr = Join-Path $logDir "ui-dev.err.log"

function Get-LocalPython {
    $local = Join-Path $root "tools\python\python.exe"
    if (Test-Path $local) { return $local }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python runtime not found. Install Python or keep tools\python\python.exe."
}

function Get-NpmCmd {
    $local = Join-Path $root "tools\node\npm.cmd"
    if (Test-Path $local) { return $local }
    $cmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "npm not found. Install Node.js or keep tools\node\npm.cmd."
}

function Stop-ByPidFile([string]$pidFile) {
    if (!(Test-Path $pidFile)) { return }
    $procId = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($procId -and ($procId -as [int])) {
        Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

function Test-PortListening([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

if ($ForceRestart) {
    Stop-ByPidFile $apiPidFile
    Stop-ByPidFile $uiPidFile
}

if (Test-PortListening 8000 -and -not $ForceRestart) {
    Write-Host "[maia] API already listening on :8000"
}

if (Test-PortListening 5173 -and -not $ForceRestart) {
    Write-Host "[maia] UI already listening on :5173"
}

$pythonExe = Get-LocalPython
$npmCmd = Get-NpmCmd
$nodeDir = Split-Path $npmCmd -Parent

if (-not (Test-PortListening 8000)) {
    $apiCmd = "set PYTHONPATH=$root&& `"$pythonExe`" -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
    $apiProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $apiCmd -WorkingDirectory $root -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru
    Set-Content -Path $apiPidFile -Value $apiProc.Id
    Write-Host "[maia] API starting on http://localhost:8000 (PID $($apiProc.Id))"
}

if (-not (Test-PortListening 5173)) {
    $frontendDir = Join-Path $root "frontend\user_interface"
    $uiCmd = "set PATH=$nodeDir;%PATH%&& `"$npmCmd`" run dev -- --host 0.0.0.0 --port 5173"
    $uiProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $uiCmd -WorkingDirectory $frontendDir -RedirectStandardOutput $uiOut -RedirectStandardError $uiErr -PassThru
    Set-Content -Path $uiPidFile -Value $uiProc.Id
    Write-Host "[maia] UI starting on http://localhost:5173 (PID $($uiProc.Id))"
}

$maxWaitSeconds = 45
$elapsed = 0
do {
    Start-Sleep -Seconds 1
    $elapsed += 1
    $apiUp = Test-PortListening 8000
    $uiUp = Test-PortListening 5173
} while ((-not ($apiUp -and $uiUp)) -and $elapsed -lt $maxWaitSeconds)

if ($apiUp) {
    $apiListener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($apiListener) { Set-Content -Path $apiPidFile -Value $apiListener.OwningProcess }
}

if ($uiUp) {
    $uiListener = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($uiListener) { Set-Content -Path $uiPidFile -Value $uiListener.OwningProcess }
}

Write-Host "[maia] API up: $apiUp | UI up: $uiUp"
if (-not $apiUp) { Write-Host "[maia] API logs: $apiErr" }
if (-not $uiUp) { Write-Host "[maia] UI logs: $uiErr" }
