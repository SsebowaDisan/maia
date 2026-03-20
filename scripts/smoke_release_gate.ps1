param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$UiBase = "http://127.0.0.1:5173",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Name,
        [bool]$Pass,
        [string]$Detail
    )

    $results.Add([PSCustomObject]@{
        Name = $Name
        Pass = $Pass
        Detail = $Detail
    }) | Out-Null
}

function Invoke-StatusCheck {
    param(
        [string]$Name,
        [string]$Url,
        [int]$Expected = 200
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 20
        $ok = ($response.StatusCode -eq $Expected)
        $detail = "HTTP $($response.StatusCode)"
        Add-Result -Name $Name -Pass $ok -Detail $detail
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if (-not $statusCode) {
            $statusCode = "ERR"
        }
        Add-Result -Name $Name -Pass $false -Detail "HTTP $statusCode"
    }
}

function Invoke-CommandCheck {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkingDirectory
    )

    $output = ""
    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process `
            -FilePath "cmd.exe" `
            -ArgumentList "/c", $Command `
            -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError $stderrFile `
            -PassThru `
            -Wait

        $stdout = if (Test-Path $stdoutFile) { Get-Content $stdoutFile -Raw } else { "" }
        $stderr = if (Test-Path $stderrFile) { Get-Content $stderrFile -Raw } else { "" }
        $output = ($stdout + "`n" + $stderr).Trim()
        $exitCode = $proc.ExitCode
        if ($exitCode -eq 0) {
            Add-Result -Name $Name -Pass $true -Detail "ok"
        } else {
            $detail = "exit=$exitCode"
            if ($output) {
                $detail = "$detail :: $output"
            }
            Add-Result -Name $Name -Pass $false -Detail $detail
        }
    } catch {
        $msg = $_.Exception.Message
        if ($output) {
            $msg = "$msg :: $output"
        }
        Add-Result -Name $Name -Pass $false -Detail $msg
    } finally {
        Remove-Item $stdoutFile -Force -ErrorAction SilentlyContinue
        Remove-Item $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "[maia] Running smoke release gate..."

$apiListening = [bool](Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
$uiListening = [bool](Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue)
$apiDetail = if ($apiListening) { "yes" } else { "no" }
$uiDetail = if ($uiListening) { "yes" } else { "no" }
Add-Result -Name "Port 8000 listening" -Pass $apiListening -Detail $apiDetail
Add-Result -Name "Port 5173 listening" -Pass $uiListening -Detail $uiDetail

Invoke-StatusCheck -Name "API docs" -Url "$ApiBase/docs"
Invoke-StatusCheck -Name "API connectors catalog" -Url "$ApiBase/api/connectors"
Invoke-StatusCheck -Name "API marketplace agents" -Url "$ApiBase/api/marketplace/agents"
Invoke-StatusCheck -Name "API marketplace workflows" -Url "$ApiBase/api/marketplace/workflows"
Invoke-StatusCheck -Name "API explore" -Url "$ApiBase/api/explore"
Invoke-StatusCheck -Name "UI root" -Url $UiBase

$uiRoutes = @(
    "/",
    "/marketplace",
    "/connectors",
    "/workflows",
    "/operations",
    "/explore"
)
foreach ($route in $uiRoutes) {
    Invoke-StatusCheck -Name "UI route $route" -Url "$UiBase$route"
}

$localIconAssets = @(
    "/icons/connectors/google-workspace.svg",
    "/icons/connectors/google-calendar.svg",
    "/icons/connectors/google-drive.svg",
    "/icons/connectors/google-docs.svg",
    "/icons/connectors/google-sheets.svg",
    "/icons/connectors/google-analytics.svg",
    "/icons/connectors/google-ads.svg",
    "/icons/connectors/google-maps.svg"
)
foreach ($asset in $localIconAssets) {
    Invoke-StatusCheck -Name "UI asset $asset" -Url "$UiBase$asset"
}

$pythonExe = Join-Path $repoRoot ".venv311\Scripts\python.exe"
if (Test-Path $pythonExe) {
    Invoke-CommandCheck -Name "Python compileall api" -Command ".\.venv311\Scripts\python.exe -m compileall -q api" -WorkingDirectory $repoRoot
} else {
    Add-Result -Name "Python compileall api" -Pass $false -Detail ".venv311\\Scripts\\python.exe missing"
}

if (-not $SkipBuild) {
    Invoke-CommandCheck -Name "Frontend build" -Command "npm --prefix frontend/user_interface run build" -WorkingDirectory $repoRoot
} else {
    Add-Result -Name "Frontend build" -Pass $true -Detail "skipped"
}

Write-Host ""
Write-Host "[maia] Smoke results:"
foreach ($result in $results) {
    $prefix = if ($result.Pass) { "[PASS]" } else { "[FAIL]" }
    Write-Host "$prefix $($result.Name) -> $($result.Detail)"
}

$failed = @($results | Where-Object { -not $_.Pass })
Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "[maia] Smoke gate FAILED ($($failed.Count) checks failed)."
    exit 1
}

Write-Host "[maia] Smoke gate PASSED."
exit 0
