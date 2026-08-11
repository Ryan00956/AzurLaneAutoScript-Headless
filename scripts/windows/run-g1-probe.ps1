[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Serial,
    [Parameter(Mandatory = $true)][string]$AngleApk,
    [Parameter(Mandatory = $true)][string]$ProbeApk,
    [string]$AnglePackage = 'org.chromium.angle',
    [string]$ProbePackage = 'io.github.alasheadless.glescontract',
    [int]$ExpectedWidth = 1280,
    [int]$ExpectedHeight = 720,
    [ValidateRange(5, 7200)][int]$DurationSeconds = 15,
    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')) 'evidence')
)

$ErrorActionPreference = 'Stop'
$adb = (Get-Command adb -ErrorAction Stop).Source
$angleApkPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($AngleApk)
$probeApkPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ProbeApk)
if (-not (Test-Path -LiteralPath $angleApkPath)) {
    throw "ANGLE APK does not exist: $angleApkPath"
}
if (-not (Test-Path -LiteralPath $probeApkPath)) {
    throw "Probe APK does not exist: $probeApkPath"
}
$capturedAt = [DateTimeOffset]::UtcNow
$captureName = 'g1-{0}-{1}' -f $capturedAt.ToString('yyyyMMddTHHmmssZ'),
    ($Serial -replace '[^A-Za-z0-9._-]', '_')
$outputDirectory = Join-Path $OutputRoot $captureName
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

function Invoke-Adb {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [switch]$AllowFailure)
    $lines = @(& $adb @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $text = ($lines | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "adb $($Arguments -join ' ') failed ($exitCode): $text"
    }
    return $text
}

function Get-GlobalSetting {
    param([string]$Name)
    return (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'get', 'global', $Name)).Trim()
}

function Restore-GlobalSetting {
    param([string]$Name, [AllowEmptyString()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -eq 'null') {
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'delete', 'global', $Name) |
            Out-Null
    }
    else {
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global', $Name, $Value) |
            Out-Null
    }
}

function Get-MemorySample {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $meminfo = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'dumpsys', 'meminfo',
        $ProcessId.ToString()) -AllowFailure
    $pssKb = $null
    $rssKb = $null
    if ($meminfo -match 'TOTAL PSS:\s+(\d+)\s+TOTAL RSS:\s+(\d+)') {
        $pssKb = [int64]$Matches[1]
        $rssKb = [int64]$Matches[2]
    }
    $topOutput = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'top', '-b', '-n', '1',
        '-p', $ProcessId.ToString()) -AllowFailure
    $cpuPercent = $null
    $processLine = $topOutput -split "`r?`n" |
        Where-Object { $_ -match "^\s*$ProcessId\s" } |
        Select-Object -First 1
    if ($processLine) {
        $columns = $processLine.Trim() -split '\s+'
        if ($columns.Count -gt 8) {
            $parsedCpu = 0.0
            if ([double]::TryParse($columns[8],
                    [Globalization.NumberStyles]::Float,
                    [Globalization.CultureInfo]::InvariantCulture,
                    [ref]$parsedCpu)) {
                $cpuPercent = $parsedCpu
            }
        }
    }
    return [ordered]@{
        captured_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
        pss_kb = $pssKb
        rss_kb = $rssKb
        cpu_percent = $cpuPercent
    }
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )
    [IO.File]::WriteAllText($Path,
        ($Value | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
}

$settingNames = @(
    'angle_debug_package',
    'angle_gl_driver_selection_pkgs',
    'angle_gl_driver_selection_values',
    'show_angle_in_use_dialog_box'
)
$originalSettings = [ordered]@{}
$settingsChanged = $false

try {
    foreach ($name in $settingNames) {
        $originalSettings[$name] = Get-GlobalSetting -Name $name
    }

    # Android 11+ package visibility can otherwise make a successfully installed
    # debug ANGLE package invisible to the target app's GraphicsEnvironment.
    Invoke-Adb -Arguments @('-s', $Serial, 'install', '-r', '-d',
        '--force-queryable', $angleApkPath) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'install', '-r', $probeApkPath) | Out-Null

    $settingsChanged = $true
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_debug_package', $AnglePackage) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_gl_driver_selection_pkgs', $ProbePackage) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_gl_driver_selection_values', 'angle') | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'show_angle_in_use_dialog_box', '0') | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'force-stop', $ProbePackage) | Out-Null
    $component = "$ProbePackage/.MainActivity"
    $startOutput = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'start', '-W',
        '-n', $component, '--ez', 'expect_null', 'true')
    $targetPid = ''
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $targetPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $ProbePackage) `
            -AllowFailure).Trim()
        if ($targetPid -match '^\d+$') { break }
        Start-Sleep -Seconds 1
    }
    if ($targetPid -notmatch '^\d+$') {
        throw "Probe process is not running after launch: $targetPid"
    }

    $contract = $null
    $initialLogText = ''
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $initialLogText = Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '--pid',
            $targetPid, '-d')
        $contractLine = $initialLogText -split "`r?`n" |
            Where-Object { $_ -match 'ALAS_CONTRACT.*\{"event":"contract-result"' } |
            Select-Object -Last 1
        if ($contractLine -and $contractLine -match '(\{"event":"contract-result".*\})') {
            $contract = $Matches[1] | ConvertFrom-Json
            break
        }
        Start-Sleep -Milliseconds 500
    }
    [IO.File]::WriteAllText((Join-Path $outputDirectory 'initial-logcat.txt'),
        $initialLogText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    if (-not $contract) {
        throw 'No structured contract-result event was found after probe startup.'
    }
    if (-not $contract.passed) {
        throw "GLES contract failed: $($contract.failure)"
    }
    if (-not $contract.renderer_is_null) {
        throw 'Probe passed without the NULL renderer identity.'
    }
    if ($contract.surface_width -ne $ExpectedWidth -or
        $contract.surface_height -ne $ExpectedHeight) {
        throw "Unexpected logical surface: $($contract.surface_width)x$($contract.surface_height)"
    }
    Write-JsonFile -Path (Join-Path $outputDirectory 'contract-result.json') -Value $contract

    $memorySamples = [System.Collections.Generic.List[object]]::new()
    $elapsedSeconds = 0
    $processFailure = $null
    while ($elapsedSeconds -lt $DurationSeconds) {
        $memorySamples.Add((Get-MemorySample -ProcessId ([int]$targetPid)))
        $progress = [ordered]@{
            schema = 'alas-headless.g1-probe-progress/v1'
            captured_at_utc = $capturedAt.ToString('o')
            serial = $Serial
            pid = [int]$targetPid
            requested_duration_seconds = $DurationSeconds
            observed_duration_seconds = $elapsedSeconds
            memory_samples = @($memorySamples)
            contract = $contract
        }
        Write-JsonFile -Path (Join-Path $outputDirectory 'progress.json') -Value $progress
        $sleepSeconds = [Math]::Min(30, $DurationSeconds - $elapsedSeconds)
        Start-Sleep -Seconds $sleepSeconds
        $elapsedSeconds += $sleepSeconds
        $currentPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $ProbePackage) `
            -AllowFailure).Trim()
        if ($currentPid -ne $targetPid) {
            $processFailure = "Probe process changed or exited after $elapsedSeconds seconds: '$currentPid'"
            break
        }
    }
    if (-not $processFailure) {
        $memorySamples.Add((Get-MemorySample -ProcessId ([int]$targetPid)))
        $elapsedSeconds = $DurationSeconds
    }
    $logText = Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '--pid', $targetPid, '-d')

    [IO.File]::WriteAllText((Join-Path $outputDirectory 'start.txt'),
        $startOutput + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $outputDirectory 'logcat.txt'),
        $logText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

    if ($processFailure) {
        [IO.File]::WriteAllText((Join-Path $outputDirectory 'failure.txt'),
            $processFailure + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        throw $processFailure
    }

    $manifest = [ordered]@{
        schema = 'alas-headless.g1-probe/v1'
        captured_at_utc = $capturedAt.ToString('o')
        serial = $Serial
        angle_apk_sha256 = (Get-FileHash -LiteralPath $angleApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
        probe_apk_sha256 = (Get-FileHash -LiteralPath $probeApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
        pid = [int]$targetPid
        duration_seconds = $DurationSeconds
        original_settings = $originalSettings
        memory_samples = $memorySamples
        contract = $contract
    }
    Write-JsonFile -Path (Join-Path $outputDirectory 'manifest.json') -Value $manifest
    Write-Output $outputDirectory
}
finally {
    if ($settingsChanged) {
        foreach ($name in $settingNames) {
            Restore-GlobalSetting -Name $name -Value $originalSettings[$name]
        }
    }
}
