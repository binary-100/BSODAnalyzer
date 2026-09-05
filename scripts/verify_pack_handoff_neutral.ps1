#Requires -Version 5.1
<#
.SYNOPSIS
  Scan Starter Pack transfer handoff for forbidden cross-project / vendor leakage.
.DESCRIPTION
  Maintainer runs before USB/email transfer. Checks the handoff markdown only.
  Exit 0 = clean enough to transfer; exit 1 = fix listed hits.
#>
param(
    [string]$HandoffPath = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AgentStarterPack_Audit_And_Rules_Upgrade_2026-09-05.md')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $HandoffPath)) {
    Write-Error "Handoff not found: $HandoffPath"
}

$text = Get-Content -LiteralPath $HandoffPath -Raw -Encoding UTF8

# Whole-document forbidden (app names, paths, domain leakage in prose outside JSON blocklist docs)
$forbiddenPatterns = @(
    'BSOD',
    'BSODAnalyzer',
    'binar\\',
    'OneDrive\\Desktop\\BSOD',
    'driver catalog',
    'bundle_verification',
    'inner_versions',
    'bundle_components',
    'Alienware',
    'Maintenance USB',
    'WQ-003',
    'project-handoffs\.mdc'
)

# Allowed: contaminationForbiddenSubstrings JSON array documents what pack verify rejects
$lines = $text -split "`n"
$inContaminationJson = $false
$hits = @()

for ($i = 0; $i -lt $lines.Count; $i++) {
    $line = $lines[$i]
    $lineNum = $i + 1

    if ($line -match 'contaminationForbiddenSubstrings') { $inContaminationJson = $true }
    if ($inContaminationJson -and $line -match '^\s*\],?\s*$') { $inContaminationJson = $false }

    foreach ($pat in $forbiddenPatterns) {
        if ($line -match $pat) {
            $hits += [PSCustomObject]@{ Line = $lineNum; Pattern = $pat; Text = $line.Trim().Substring(0, [Math]::Min(120, $line.Trim().Length)) }
        }
    }
}

# Structural checks
$required = @(
    'Zero cross-project contamination',
    'aggregate_status_vs_member_drift',
    'HANDOFF-VERIFY',
    'verify-audit-upgrade-handoff.ps1',
    'productAccuracySections',
    'handoffs.archiveOnDone'
)
$missing = @($required | Where-Object { $text -notmatch [regex]::Escape($_) })

if ($hits.Count -gt 0) {
    Write-Host "FAIL: forbidden content in handoff:" -ForegroundColor Red
    $hits | Format-Table -AutoSize
}

if ($missing.Count -gt 0) {
    Write-Host "FAIL: missing required sections/fields:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" }
}

if ($hits.Count -gt 0 -or $missing.Count -gt 0) {
    exit 1
}

Write-Host "OK: handoff passes neutral scan ($HandoffPath)" -ForegroundColor Green
exit 0
