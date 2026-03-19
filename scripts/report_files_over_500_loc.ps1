param(
    [int]$Limit = 500,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $repoRoot "docs\files_over_500_loc.md"
}

$sourceRoots = @(
    (Join-Path $repoRoot "api"),
    (Join-Path $repoRoot "frontend\user_interface\src")
)

$allowedExtensions = @(".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss")
$excludePathTokens = @(
    "\node_modules\",
    "\dist\",
    "\build\",
    "\coverage\",
    "\tests\",
    "\__pycache__\"
)

function Is-ExcludedPath {
    param([string]$FullPath)

    $normalized = $FullPath.Replace("/", "\").ToLowerInvariant()
    foreach ($token in $excludePathTokens) {
        if ($normalized.Contains($token)) {
            return $true
        }
    }
    return $false
}

function Is-TestFile {
    param([string]$FileName)
    $lower = $FileName.ToLowerInvariant()
    return ($lower.Contains(".test.") -or $lower.Contains(".spec."))
}

$matches = New-Object System.Collections.Generic.List[object]

foreach ($root in $sourceRoots) {
    if (!(Test-Path $root)) {
        continue
    }

    Get-ChildItem -Path $root -Recurse -File | ForEach-Object {
        if (Is-ExcludedPath -FullPath $_.FullName) {
            return
        }

        $ext = $_.Extension.ToLowerInvariant()
        if ($allowedExtensions -notcontains $ext) {
            return
        }

        if (Is-TestFile -FileName $_.Name) {
            return
        }

        $lineCount = (Get-Content $_.FullName | Measure-Object -Line).Lines
        if ($lineCount -le $Limit) {
            return
        }

        $fullPath = $_.FullName
        $relative = $fullPath.Substring($repoRoot.Length).TrimStart("\", "/").Replace("\", "/")
        $matches.Add([PSCustomObject]@{
            Lines = $lineCount
            Path = $relative
        }) | Out-Null
    }
}

$sorted = $matches | Sort-Object -Property @{Expression = "Lines"; Descending = $true}, @{Expression = "Path"; Descending = $false}
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss 'UTC'")

$doc = New-Object System.Collections.Generic.List[string]
$doc.Add("# Source Code Files Above $Limit LOC") | Out-Null
$doc.Add("") | Out-Null
$doc.Add("Generated on: $timestamp") | Out-Null
$doc.Add("") | Out-Null
$doc.Add("Total source code files > $Limit LOC (excluding test files): $($sorted.Count)") | Out-Null
$doc.Add("") | Out-Null
$doc.Add('```text') | Out-Null
if ($sorted.Count -eq 0) {
    $doc.Add("(none)") | Out-Null
} else {
    foreach ($row in $sorted) {
        $doc.Add(("{0,4}  {1}" -f $row.Lines, $row.Path)) | Out-Null
    }
}
$doc.Add('```') | Out-Null

$targetDir = Split-Path $OutputPath -Parent
if (!(Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
}

$doc | Set-Content -Path $OutputPath

Write-Host "[maia] LOC report generated: $OutputPath"
Write-Host "[maia] Files above $Limit LOC: $($sorted.Count)"
foreach ($row in $sorted) {
    Write-Host ("{0,4}  {1}" -f $row.Lines, $row.Path)
}
