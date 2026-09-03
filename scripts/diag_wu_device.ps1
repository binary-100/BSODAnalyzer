$ErrorActionPreference = 'SilentlyContinue'
$pnp = (Get-CimInstance Win32_VideoController -EA 0 | Where-Object { $_.Name -like '*NVIDIA*GeForce*' } | Select-Object -First 1).PNPDeviceID
$hw = $pnp -replace '\\','\\'
Write-Output "Searching for: $pnp"
$Session = New-Object -ComObject Microsoft.Update.Session
$Searcher = $Session.CreateUpdateSearcher()
$Searcher.Online = $true
$criteria = @(
    "IsInstalled=0 and Type='Driver'",
    "IsInstalled=0 and Type='Driver' and DeviceID='$($pnp.Replace('\','\\'))'"
)
foreach ($c in $criteria) {
    try {
        $R = $Searcher.Search($c)
        Write-Output "Criteria=$c Count=$($R.Updates.Count)"
    } catch {
        Write-Output "Criteria=$c Error=$($_.Exception.Message)"
    }
}

# DriverStore - third party
Get-WindowsDriver -Online -All 2>$null | Where-Object { $_.ProviderName -match 'NVIDIA' -and $_.ClassName -eq 'Display' } |
    Select-Object -First 3 ProviderName, Version, Date, OriginalFileName |
    ConvertTo-Json -Compress
