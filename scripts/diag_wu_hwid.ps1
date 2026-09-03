$ErrorActionPreference = 'SilentlyContinue'
$pnp = (Get-CimInstance Win32_VideoController -EA 0 | Where-Object { $_.Name -like '*NVIDIA*' } | Select-Object -First 1).PNPDeviceID
Write-Output "PNP=$pnp"
$Session = New-Object -ComObject Microsoft.Update.Session
$Searcher = $Session.CreateUpdateSearcher()
$Searcher.Online = $true
# All non-installed drivers
$Result = $Searcher.Search("IsInstalled=0 and Type='Driver'")
Write-Output "TotalOptionalDrivers=$($Result.Updates.Count)"
# Try matching by title
$nv = @()
for ($i = 0; $i -lt $Result.Updates.Count; $i++) {
  $u = $Result.Updates.Item($i)
  if ($u.Title -match 'NVIDIA|GeForce') {
    $ver = ''
    try { $ver = [string]$u.DriverVerVersion } catch {}
    $nv += "$($u.Title)|$ver"
  }
}
Write-Output "NvidiaMatches=$($nv.Count)"
$nv | Select-Object -First 5 | ForEach-Object { Write-Output $_ }

# Win32_PnPSignedDriver for NVIDIA devices
Get-CimInstance Win32_PnPSignedDriver -EA 0 |
  Where-Object { $_.DeviceName -match 'NVIDIA|GeForce' } |
  Select-Object -First 3 DeviceName, DriverVersion, DriverProviderName, InfName |
  ConvertTo-Json -Compress
