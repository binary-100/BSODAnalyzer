$ErrorActionPreference = 'SilentlyContinue'
Write-Output 'Scanning online driver catalog (may take 1-2 min)...'
$nv = Get-WindowsDriver -Online -All 2>$null |
    Where-Object { $_.ProviderName -match 'NVIDIA' -and $_.ClassName -eq 'Display' } |
    Sort-Object { [version]$_.Version } -Descending |
    Select-Object -First 5 ProviderName, Version, HardwareDescription, Date
if ($nv) {
    $nv | ConvertTo-Json -Compress -Depth 3
} else {
    Write-Output 'No NVIDIA display drivers in online catalog (or cmdlet failed)'
}
$amd = Get-WindowsDriver -Online -All 2>$null |
    Where-Object { $_.ProviderName -match 'AMD' -and $_.ClassName -eq 'Display' } |
    Sort-Object { [version]$_.Version } -Descending |
    Select-Object -First 3 ProviderName, Version, HardwareDescription
if ($amd) {
    Write-Output '---AMD---'
    $amd | ConvertTo-Json -Compress -Depth 3
}
