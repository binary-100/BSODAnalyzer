# Model A factory: remove pack-generic rules synced into the project by Refresh-AgentContext.cmd.
# Generic rules belong in %USERPROFILE%\.cursor\rules\ on this machine — not duplicated here.
param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $ProjectRoot 'docs\MODEL_A_FACTORY.json'
if (-not (Test-Path $manifestPath)) {
    Write-Error "Missing manifest: $manifestPath"
}

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$rulesDir = Join-Path $ProjectRoot '.cursor\rules'
$removed = @()
$extras = @()

foreach ($name in $manifest.removeAfterPackRefresh) {
    $path = Join-Path $rulesDir $name
    if (Test-Path $path) {
        if ($VerifyOnly) {
            $removed += $name
        } else {
            Remove-Item $path -Force
            $removed += $name
        }
    }
}

Get-ChildItem $rulesDir -Filter 'generic-*.mdc' -File -ErrorAction SilentlyContinue | ForEach-Object {
    if ($manifest.removeAfterPackRefresh -notcontains $_.Name) {
        if ($VerifyOnly) { $removed += $_.Name } else { Remove-Item $_.FullName -Force; $removed += $_.Name }
    }
}

foreach ($rel in $manifest.removePathsAfterPackRefresh) {
    $path = Join-Path $ProjectRoot ($rel -replace '/', '\')
    if (Test-Path $path) {
        if ($VerifyOnly) {
            $removed += $rel
        } else {
            Remove-Item $path -Recurse -Force -ErrorAction SilentlyContinue
            $removed += $rel
        }
    }
}

$remaining = @(Get-ChildItem $rulesDir -Filter '*.mdc' -File | ForEach-Object { $_.Name })
foreach ($name in $remaining) {
    if ($manifest.allowedProjectRules -notcontains $name) {
        $extras += $name
    }
}

$allowedSet = @($manifest.allowedProjectRules | Sort-Object)
$remainingSet = @($remaining | Sort-Object)
$missing = @($allowedSet | Where-Object { $_ -notin $remainingSet })

if ($VerifyOnly) {
    if ($removed.Count -gt 0 -or $extras.Count -gt 0) {
        Write-Host "Model A verify FAIL: unwanted rules or paths present."
        if ($removed.Count) { Write-Host "  Blocked present: $($removed -join ', ')" }
        if ($extras.Count) { Write-Host "  Unexpected .mdc: $($extras -join ', ')" }
        exit 1
    }
    if ($missing.Count) {
        Write-Host "Model A verify FAIL: missing allowed rules: $($missing -join ', ')"
        exit 1
    }
    Write-Host "Model A verify OK ($($remaining.Count) project rules)."
    exit 0
}

if ($removed.Count) {
    Write-Host "Removed after pack refresh: $($removed -join ', ')"
} else {
    Write-Host "No generic project rules to remove."
}

if ($extras.Count) {
    Write-Warning "Unexpected .mdc in project (review manually): $($extras -join ', ')"
}
if ($missing.Count) {
    Write-Warning "Missing expected BSOD rules: $($missing -join ', ')"
}

Write-Host "Project rules: $($remaining.Count) file(s) in $rulesDir"
exit 0
