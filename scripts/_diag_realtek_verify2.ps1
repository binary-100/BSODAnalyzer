$raw = pnputil /enum-drivers 2>&1 | Out-String
$blocks = $raw -split '(?=Published Name\s*:)'
Write-Output '=== oem87.inf block ==='
$blocks | Where-Object { $_ -match 'oem87\.inf' }

Write-Output '=== NET class Realtek blocks ==='
$blocks | Where-Object { $_ -match 'Class Name:\s+Net' -and $_ -match 'Realtek|8125|rt68|rt25|rt8125|10EC' }

Write-Output '=== DUP Realtek Ethernet snippets ==='
Select-String -Path 'C:\ProgramData\Dell\UpdateService\Temp\Alienware_Notebook_0B5B.xml' -Pattern 'Realtek|Ethernet|8125|1168\.|1125\.' -Context 0,2 | Select-Object -First 25
