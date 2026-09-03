# One-shot Realtek NIC verification baseline (agent diagnostic)
$ErrorActionPreference = 'SilentlyContinue'

Write-Output '=== Win32_PnPSignedDriver (Realtek NET) ==='
Get-CimInstance Win32_PnPSignedDriver |
  Where-Object {
    $_.DeviceName -match 'Realtek' -and (
      $_.DeviceClass -eq 'NET' -or $_.DeviceName -match 'Gbe|Ethernet|2\.5'
    )
  } |
  Select-Object DeviceName, DriverVersion, DriverDate, InfName, DeviceID |
  Format-List

Write-Output '=== ARP Realtek Ethernet packages ==='
$keys = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
Get-ItemProperty $keys |
  Where-Object { $_.DisplayName -match 'Realtek.*(Ethernet|Gbe|Network|PCIe)' } |
  Select-Object DisplayName, DisplayVersion, Publisher |
  Format-Table -AutoSize

Write-Output '=== pnputil Realtek published drivers (sample) ==='
$raw = pnputil /enum-drivers 2>&1 | Out-String
$blocks = $raw -split '(?=Published Name\s*:)' | Where-Object { $_ -match 'Realtek|10EC|rt68|rt25|rt640' }
$blocks | Select-Object -First 8

Write-Output '=== Dell DUP manifest Realtek (if present) ==='
$dupBase = Join-Path $env:ProgramData 'Dell\UpdateService\Temp'
if (Test-Path $dupBase) {
  Get-ChildItem -Path $dupBase -Recurse -Filter '*.xml' -ErrorAction SilentlyContinue |
    Select-Object -First 20 FullName
} else {
  Write-Output '(no Dell UpdateService Temp folder)'
}
