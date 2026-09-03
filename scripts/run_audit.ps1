param(
    [string]$AppRoot = (Get-Location).Path,
    [switch]$FinalizeOnly,
    [switch]$SkipTests
)

$AppRoot = (Resolve-Path -LiteralPath $AppRoot).Path

# Flat layout: project root owns AGENTS.md, docs/AUDIT.md, and .git (when present).
$RepoRoot = $AppRoot
if (-not (Test-Path -LiteralPath (Join-Path $AppRoot '.git'))) {
    $parent = Split-Path -Parent $AppRoot
    if ($parent -and
        (Split-Path -Leaf $AppRoot) -eq 'app' -and
        (Test-Path -LiteralPath (Join-Path $AppRoot 'docs\AUDIT.md')) -and
        (Test-Path -LiteralPath (Join-Path $parent '.git'))) {
        $RepoRoot = $parent
    }
}

function Resolve-AuditCore {
    $candidates = @()
    if ($env:AGENT_STARTER_PACK_ROOT) { $candidates += $env:AGENT_STARTER_PACK_ROOT }
    if ($env:CURSOR_STARTER_PACK_ROOT) { $candidates += $env:CURSOR_STARTER_PACK_ROOT }
    $candidates += @(
        (Join-Path $env:USERPROFILE '.cursor\AgentStarterPack'),
        (Join-Path $env:USERPROFILE '.cursor\agent-starter-pack'),
        (Join-Path $env:USERPROFILE 'OneDrive\Desktop\AgentStarterPack'),
        (Join-Path $env:USERPROFILE 'OneDrive\Desktop\CursorAgentStarterPack')
    )
    foreach ($base in ($candidates | Select-Object -Unique)) {
        $core = Join-Path $base 'pack\scripts\run_audit_core.ps1'
        if (Test-Path -LiteralPath $core) { return $core }
    }
    Write-Error 'run_audit_core.ps1 not found. Install Agent Starter Pack (Install-AgentStarterPack.cmd).'
}

$core = Resolve-AuditCore
if ($FinalizeOnly) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $core -RepoRoot $RepoRoot -AppRoot $AppRoot -FinalizeOnly
} elseif ($SkipTests) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $core -RepoRoot $RepoRoot -AppRoot $AppRoot -SkipTests
} else {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $core -RepoRoot $RepoRoot -AppRoot $AppRoot
}
exit $LASTEXITCODE
