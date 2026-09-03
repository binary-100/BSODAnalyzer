#Requires -Version 5.1
<#
.SYNOPSIS
  One-time: move app/ contents to git root (flat layout). Run from repo root after review.
#>
param(
    [string]$RepoRoot = (Split-Path $PSScriptRoot -Parent),
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$AppDir = Join-Path $RepoRoot 'app'

if (-not (Test-Path -LiteralPath $AppDir)) {
    Write-Host "ERROR: app/ not found under $RepoRoot (already flattened?)"
    exit 1
}

function Move-Safe([string]$From, [string]$To) {
    if (-not (Test-Path -LiteralPath $From)) { return }
    if ($WhatIf) { Write-Host "[whatif] move $From -> $To"; return }
    $dir = Split-Path -Parent $To
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Move-Item -LiteralPath $From -Destination $To -Force
}

Write-Host "Flatten: $AppDir -> $RepoRoot"

# Mistaken nested copy from a bad refresh path
$nested = Join-Path $AppDir 'app'
if (Test-Path -LiteralPath $nested) {
    Write-Host "Removing mistaken app/app/ ..."
    if (-not $WhatIf) { Remove-Item -LiteralPath $nested -Recurse -Force }
}

# Merge repo-root .cursor/rules into app before lift
$rootRules = Join-Path $RepoRoot '.cursor\rules'
$appRules = Join-Path $AppDir '.cursor\rules'
if (Test-Path -LiteralPath $rootRules) {
    if (-not (Test-Path -LiteralPath $appRules)) { New-Item -ItemType Directory -Path $appRules -Force | Out-Null }
    Get-ChildItem -LiteralPath $rootRules -Filter '*.mdc' -File | ForEach-Object {
        $dst = Join-Path $appRules $_.Name
        Write-Host "Merge rule: $($_.Name)"
        if (-not $WhatIf) { Copy-Item -LiteralPath $_.FullName -Destination $dst -Force }
    }
    if (-not $WhatIf) { Remove-Item -LiteralPath (Join-Path $RepoRoot '.cursor') -Recurse -Force }
}

# Remove repo-root shim / duplicate agent artifacts
foreach ($rel in @('docs', '.agent-bootstrap.json')) {
    $p = Join-Path $RepoRoot $rel
    if (Test-Path -LiteralPath $p) {
        Write-Host "Remove repo-root $rel"
        if (-not $WhatIf) { Remove-Item -LiteralPath $p -Recurse -Force }
    }
}

# Archive pre-flatten repo-root docs (pointers / migration-era)
$archive = Join-Path $AppDir 'docs\repo_flatten_archive'
if (-not $WhatIf) { New-Item -ItemType Directory -Path $archive -Force | Out-Null }
foreach ($name in @('BUILD_NOTES.md', 'CONSOLIDATION.md', 'EVALUATION.md', 'ONEDRIVE_CLEANUP.md', 'PERFORMANCE_PLAN.md', 'README.md', 'PROJECT_LAYOUT.md')) {
    $src = Join-Path $RepoRoot $name
    if (Test-Path -LiteralPath $src) {
        Move-Safe $src (Join-Path $archive $name)
    }
}

# Lift everything under app/ to repo root
Get-ChildItem -LiteralPath $AppDir -Force | ForEach-Object {
    $dest = Join-Path $RepoRoot $_.Name
    if (Test-Path -LiteralPath $dest) {
        Write-Host "ERROR: would overwrite $dest - resolve conflict manually"
        exit 1
    }
    Write-Host "Lift: $($_.Name)"
    if (-not $WhatIf) { Move-Item -LiteralPath $_.FullName -Destination $dest -Force }
}

if (Test-Path -LiteralPath $AppDir) {
    Write-Host "Remove empty app/"
    if (-not $WhatIf) { Remove-Item -LiteralPath $AppDir -Force -Recurse }
}

Write-Host "Flatten move complete. Run scripts/update_paths_after_flatten.ps1 next."
exit 0
