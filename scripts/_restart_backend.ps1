$root = "C:\Users\SBW\OneDrive - Axon Group\Documents\GitHub\maia"
$logDir = Join-Path $root ".run_logs"

# Kill everything currently listening on port 8000
$listeners = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
foreach ($l in $listeners) {
    Stop-Process -Id $l.OwningProcess -Force -ErrorAction SilentlyContinue
    Write-Host "[maia] Killed PID $($l.OwningProcess) on port 8000"
}
Start-Sleep -Seconds 2

# Start backend with the project venv
$python = Join-Path $root ".venv311\Scripts\python.exe"
$outLog = Join-Path $logDir "backend.out.log"
$errLog = Join-Path $logDir "backend.err.log"

# Clear old logs so we get a clean read
"" | Out-File -FilePath $outLog -Encoding utf8
"" | Out-File -FilePath $errLog -Encoding utf8

$proc = Start-Process `
    -FilePath $python `
    -ArgumentList "run_api.py" `
    -WorkingDirectory $root `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru `
    -WindowStyle Hidden

$proc.Id | Out-File -FilePath (Join-Path $logDir "backend.pid") -Encoding ascii
Write-Host "[maia] Backend started PID=$($proc.Id)"

# Wait up to 30s for startup
$elapsed = 0
do {
    Start-Sleep -Seconds 1
    $elapsed++
    $up = [bool](Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
} while (-not $up -and $elapsed -lt 30)

if ($up) {
    Write-Host "[maia] API is up on http://localhost:8000"
} else {
    Write-Host "[maia] API did NOT come up after 30s - check $errLog"
}
