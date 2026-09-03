#Requires -Version 5.1
<#
.SYNOPSIS
  Bulk path updates after repo flatten (app/ -> project root).
#>
param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

$skipRx = '(\\BSODAnalyzer_v6\\|\\DebuggingTools\\|_internal\\|__pycache__|\\build\\|\\dist\\|repo_flatten_archive|\\\.git\\)'

$replacements = @(
    @{ From = 'docs/'; To = 'docs/' }
    @{ From = 'docs\'; To = 'docs\' }
    @{ From = 'AGENTS.md'; To = 'AGENTS.md' }
    @{ From = 'AGENTS.md'; To = 'AGENTS.md' }
    @{ From = '.cursor/'; To = '.cursor/' }
    @{ From = '.cursor\'; To = '.cursor\' }
    @{ From = 'Desktop\BSODAnalyzer\'; To = 'Desktop\BSODAnalyzer\' }
    @{ From = 'BSODAnalyzer/'; To = 'BSODAnalyzer/' }
    @{ From = 'BSODAnalyzer\'; To = 'BSODAnalyzer\' }
    @{ From = 'from the project root'; To = 'from the project root' }
    @{ From = 'from the project root'; To = 'from the project root' }
    @{ From = 'in this repo'; To = 'in this repo' }
    @{ From = 'touch product code'; To = 'touch product code' }
    @{ From = '| product code |'; To = '| product code |' }
)

$exts = @('*.md', '*.mdc', '*.json', '*.cmd', '*.bat', '*.ps1', '*.py', '*.txt', '*.html')
$changed = 0
foreach ($ext in $exts) {
    Get-ChildItem -LiteralPath $ProjectRoot -Recurse -Filter $ext -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch $skipRx } |
        ForEach-Object {
            $raw = [System.IO.File]::ReadAllText($_.FullName)
            $new = $raw
            foreach ($r in $replacements) {
                $new = $new.Replace($r.From, $r.To)
            }
            # Remaining app/docs without prefix patterns
            $new = $new -replace '(?<![\w/\\])docs/', 'docs/'
            $new = $new -replace '(?<![\w/\\])app\\docs\\', 'docs\'
            if ($new -ne $raw) {
                [System.IO.File]::WriteAllText($_.FullName, $new, (New-Object System.Text.UTF8Encoding($false)))
                $script:changed++
                Write-Host "Updated: $($_.FullName.Substring($ProjectRoot.Length))"
            }
        }
}
Write-Host "Path update: $changed file(s)"
exit 0
