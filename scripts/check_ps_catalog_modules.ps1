$ErrorActionPreference = 'Continue'
Write-Host '=== PowerShell ==='
$PSVersionTable.PSVersion.ToString()
Write-Host ''
Write-Host '=== Installed modules ==='
foreach ($name in @('MSCatalogLTS', 'CatalogUpdateDownloader', 'MSCatalog')) {
    $m = Get-Module -ListAvailable $name -ErrorAction SilentlyContinue
    if ($m) {
        $m | ForEach-Object { Write-Host "$($_.Name) $($_.Version) -> $($_.ModuleBase)" }
    } else {
        Write-Host "$name : NOT INSTALLED"
    }
}
Write-Host ''
Write-Host '=== PSGallery latest ==='
foreach ($name in @('MSCatalogLTS', 'CatalogUpdateDownloader')) {
    try {
        $fm = Find-Module $name -ErrorAction Stop
        Write-Host "$($fm.Name) $($fm.Version) published $($fm.PublishedDate)"
    } catch {
        Write-Host "$name : Find-Module failed - $($_.Exception.Message)"
    }
}
