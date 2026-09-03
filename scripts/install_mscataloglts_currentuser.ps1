$ErrorActionPreference = 'Stop'
$version = '2.1.0.2'
$moduleName = 'MSCatalogLTS'
$destRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Modules'
$destDir = Join-Path $destRoot "$moduleName\$version"
$nupkg = Join-Path $env:TEMP "$moduleName.$version.nupkg"
$url = "https://www.powershellgallery.com/api/v2/package/$moduleName/$version"

Write-Host "Downloading $moduleName $version ..."
Invoke-WebRequest -Uri $url -OutFile $nupkg -UseBasicParsing

Write-Host "Extracting to $destDir ..."
if (Test-Path $destDir) { Remove-Item -Recurse -Force $destDir }
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($nupkg, $destDir)

# nupkg layout: module files may be in root or subfolder
$psd1 = Get-ChildItem -Path $destDir -Filter '*.psd1' -Recurse | Select-Object -First 1
if (-not $psd1) { throw 'No .psd1 found after extract' }
$moduleRoot = $psd1.Directory.FullName
if ($moduleRoot -ne $destDir) {
    Get-ChildItem $moduleRoot | Move-Item -Destination $destDir -Force
}

Write-Host 'Verifying import ...'
Import-Module (Join-Path $destDir 'MSCatalogLTS.psd1') -Force
$cmd = Get-Command Get-MSCatalogUpdate -ErrorAction SilentlyContinue
if (-not $cmd) { throw 'Get-MSCatalogUpdate not found after import' }
Write-Host "OK: $($cmd.Name) from $($cmd.ModuleName)"

Write-Host ''
Write-Host '=== Installed ==='
Get-Module -ListAvailable MSCatalogLTS | Format-List Name, Version, ModuleBase
