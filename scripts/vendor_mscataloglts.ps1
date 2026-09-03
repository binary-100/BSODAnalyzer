$ErrorActionPreference = 'Stop'
$version = '2.1.0.2'
$moduleName = 'MSCatalogLTS'
$repoRoot = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path (Join-Path $repoRoot 'VERSION.txt'))) {
    throw "Could not locate repo root from $PSScriptRoot"
}
$destRoot = Join-Path $repoRoot 'PowerShellModules'
$destDir = Join-Path $destRoot "$moduleName\$version"
$nupkg = Join-Path $env:TEMP "$moduleName.$version.nupkg"
$url = "https://www.powershellgallery.com/api/v2/package/$moduleName/$version"

Write-Host "Repo: $repoRoot"
Write-Host "Downloading $moduleName $version ..."
Invoke-WebRequest -Uri $url -OutFile $nupkg -UseBasicParsing

Write-Host "Extracting to $destDir ..."
if (Test-Path $destDir) { Remove-Item -Recurse -Force $destDir }
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($nupkg, $destDir)

# Remove NuGet metadata folders not needed at runtime.
foreach ($junk in @('_rels', 'package', '[Content_Types].xml', "$moduleName.nuspec")) {
    $p = Join-Path $destDir $junk
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}

Import-Module (Join-Path $destDir "$moduleName.psd1") -Force
if (-not (Get-Command Get-MSCatalogUpdate -ErrorAction SilentlyContinue)) {
    throw 'Get-MSCatalogUpdate not available after import'
}
Write-Host "OK: MSCatalogLTS $version vendored to $destDir"
