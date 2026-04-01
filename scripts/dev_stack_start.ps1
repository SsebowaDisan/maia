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

function Test-PythonHasModules([string]$pythonPath, [string[]]$requiredModules) {
    if (-not $pythonPath -or -not (Test-Path $pythonPath)) { return $false }
    $checkScript = "import importlib.util as u, sys; mods = sys.argv[1:]; raise SystemExit(0 if all(u.find_spec(m) for m in mods) else 1)"
    & $pythonPath -c $checkScript @requiredModules *> $null
    return ($LASTEXITCODE -eq 0)
}

function Get-LocalPython {
    $requiredModules = @("fastapi", "uvicorn")
    $candidates = @(
        (Join-Path $root ".venv311\Scripts\python.exe"),
        (Join-Path $root ".venv\Scripts\python.exe"),
        (Join-Path $root "tools\python\python.exe")
    )

    $sysPython = Get-Command python -ErrorAction SilentlyContinue
    if ($sysPython -and $sysPython.Source) {
        $candidates += $sysPython.Source
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-PythonHasModules -pythonPath $candidate -requiredModules $requiredModules) {
            return $candidate
        }
    }

    $checked = (($candidates | Select-Object -Unique) -join ", ")
    throw "No suitable Python runtime found with required modules (fastapi, uvicorn). Checked: $checked"
}

function Get-NpmCmd {
    $candidates = @(
        (Join-Path $root "tools\node\npm.cmd")
    )

    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "nodejs\npm.cmd")
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} "nodejs\npm.cmd")
    }

    $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $candidates += $cmd.Source
    }

    $npmApp = Get-Command npm -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($npmApp -and $npmApp.Source) {
        $candidates += $npmApp.Source
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    throw "npm.cmd not found. Install Node.js or keep tools\node\npm.cmd."
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
