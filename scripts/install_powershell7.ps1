# Install latest PowerShell 7 on Windows (BSOD Analyzer helper).
# Run elevated. Prefers direct MSI (reliable when already elevated); winget is fallback.
$ErrorActionPreference = 'Stop'

$LogFile = Join-Path $env:TEMP 'BSODAnalyzer_pwsh7_install.log'

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $Message"
    Write-Host $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Test-Pwsh7Installed {
    $candidates = @(
        (Get-Command pwsh -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "$env:ProgramFiles\PowerShell\7\pwsh.exe"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    foreach ($exe in $candidates) {
        try {
            $ver = & $exe -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'
            if ($ver -and [int]($ver.Split('.')[0]) -ge 7) {
                Write-Log "PowerShell 7 already installed: $ver ($exe)"
                exit 0
            }
        } catch { }
    }
    return $false
}

function Test-InstallerExitOk {
    param([int]$ExitCode)
    return ($ExitCode -eq 0 -or $ExitCode -eq 3010)
}

function Get-WingetPath {
    $paths = @(
        (Get-Command winget -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe')
    )
    foreach ($p in $paths) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    $appInstaller = Get-ChildItem -Path "$env:ProgramFiles\WindowsApps" -Filter 'winget.exe' -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($appInstaller) { return $appInstaller }
    return $null
}

function Install-Pwsh7MsiFromUrl {
    param(
        [Parameter(Mandatory = $true)][string]$DownloadUrl,
        [string]$FileName = ''
    )
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $headers = @{ 'User-Agent' = 'BSODAnalyzer-pwsh7-installer' }
    if (-not $FileName) {
        $FileName = [System.IO.Path]::GetFileName(($DownloadUrl -split '\?')[0])
    }
    if (-not $FileName) {
        $FileName = 'PowerShell-7-win-x64.msi'
    }
    $dest = Join-Path $env:TEMP $FileName
    Write-Log "Downloading MSI: $DownloadUrl"
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $dest -Headers $headers -UseBasicParsing
    Write-Log "Running MSI installer: $dest"
    $proc = Start-Process -FilePath 'msiexec.exe' -ArgumentList @(
        '/i', $dest,
        '/qn',
        'ADD_EXPLORER_CONTEXT_MENU_OPENPOWERSHELL=1',
        'ENABLE_PSREMOTING=1',
        'REGISTER_MANIFEST=1',
        'USE_MU=1',
        'REBOOT=ReallySuppress'
    ) -Wait -PassThru
    if (-not (Test-InstallerExitOk $proc.ExitCode)) {
        throw "MSI installer failed with exit code $($proc.ExitCode)."
    }
    if ($proc.ExitCode -eq 3010) {
        Write-Log 'MSI reported success (reboot deferred).'
    }
    return $true
}

function Get-Pwsh7MsiUrlFromWingetPkgs {
    Write-Log 'Resolving PowerShell 7 MSI from winget-pkgs manifest...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $headers = @{ 'User-Agent' = 'BSODAnalyzer-pwsh7-installer' }
    $api = 'https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/m/Microsoft/PowerShell'
    $entries = Invoke-RestMethod -Uri $api -Headers $headers -UseBasicParsing
    $versions = @(
        $entries | Where-Object { $_.type -eq 'dir' } | ForEach-Object { $_.name } | Sort-Object -Descending
    )
    if (-not $versions) {
        return $null
    }
    $ver = $versions[0]
    $yamlUrl = "https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/m/Microsoft/PowerShell/$ver/Microsoft.PowerShell.installer.yaml"
    $yaml = (Invoke-WebRequest -Uri $yamlUrl -Headers $headers -UseBasicParsing).Content
    $blocks = [regex]::Split($yaml, '(?m)^-\s+Architecture:')
    foreach ($block in $blocks) {
        if ($block -notmatch '(?i)x64') { continue }
        if ($block -match '(?im)InstallerUrl:\s*(\S+)') {
            $url = $Matches[1].Trim()
            if ($url -match '(?i)\.msi') {
                Write-Log "winget-pkgs MSI URL ($ver): $url"
                return $url
            }
        }
    }
    if ($yaml -match '(?im)InstallerUrl:\s*(\S+win-x64[^\s]*\.msi[^\s]*)') {
        return $Matches[1].Trim()
    }
    return $null
}

function Install-Pwsh7Msi {
    Write-Log 'Downloading latest stable PowerShell 7 MSI from GitHub...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $headers = @{ 'User-Agent' = 'BSODAnalyzer-pwsh7-installer' }
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/PowerShell/PowerShell/releases/latest' -Headers $headers -UseBasicParsing
    $asset = $release.assets | Where-Object {
        $_.name -match 'win-x64\.msi$' -and $_.name -notmatch 'preview|rc'
    } | Select-Object -First 1
    if (-not $asset) {
        throw 'Could not find a win-x64 MSI in the latest PowerShell release.'
    }
    Install-Pwsh7MsiFromUrl -DownloadUrl $asset.browser_download_url -FileName $asset.name | Out-Null
    return $true
}

function Install-Pwsh7Winget {
    param([string]$WingetPath)
    Write-Log "Using winget: $WingetPath"
    $args = @(
        'install', '--id', 'Microsoft.PowerShell', '--source', 'winget',
        '--accept-package-agreements', '--accept-source-agreements',
        '--disable-interactivity', '-h', '--scope', 'machine'
    )
    $proc = Start-Process -FilePath $WingetPath -ArgumentList $args -Wait -PassThru -NoNewWindow
    Write-Log "winget exit code: $($proc.ExitCode)"
    return (Test-InstallerExitOk $proc.ExitCode)
}

try {
    "" | Set-Content -LiteralPath $LogFile -Encoding UTF8 -Force
    Write-Log "BSOD Analyzer PowerShell 7 install started."

    if (Test-Pwsh7Installed) { exit 0 }

    Write-Log 'Installing PowerShell 7...'

    $installed = $false
    try {
        Install-Pwsh7Msi | Out-Null
        $installed = $true
        Write-Log 'MSI install path completed.'
    } catch {
        Write-Log "MSI install failed: $($_.Exception.Message)"
    }

    if (-not $installed) {
        try {
            $manifestUrl = Get-Pwsh7MsiUrlFromWingetPkgs
            if ($manifestUrl) {
                Install-Pwsh7MsiFromUrl -DownloadUrl $manifestUrl | Out-Null
                $installed = $true
                Write-Log 'winget-pkgs MSI install path completed.'
            }
        } catch {
            Write-Log "winget-pkgs MSI install failed: $($_.Exception.Message)"
        }
    }

    if (-not $installed) {
        $winget = Get-WingetPath
        if ($winget) {
            try {
                if (Install-Pwsh7Winget -WingetPath $winget) {
                    $installed = $true
                    Write-Log 'winget install path completed.'
                }
            } catch {
                Write-Log "winget install failed: $($_.Exception.Message)"
            }
        } else {
            Write-Log 'winget not found; MSI was the only option.'
        }
    }

    if (Test-Pwsh7Installed) {
        Write-Log 'PowerShell 7 install complete.'
        exit 0
    }

    throw 'PowerShell 7 was not detected after install attempts. See log: ' + $LogFile
} catch {
    Write-Log "FAILED: $($_.Exception.Message)"
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Details: $LogFile" -ForegroundColor Yellow
    Write-Host ""
    Read-Host 'Press Enter to close'
    exit 1
}
