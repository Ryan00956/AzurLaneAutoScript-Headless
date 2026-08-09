[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Serial,
    [ValidateSet('null', 'system')][string]$DriverMode = 'null',
    [string]$AngleApk,
    [Parameter(Mandatory = $true)][string]$UnityApk,
    [string]$AnglePackage = 'org.chromium.angle',
    [string]$UnityPackage = 'io.github.alasheadless.unitycontract',
    [string]$Activity = 'com.unity3d.player.UnityPlayerActivity',
    [string]$UnityCommandLine,
    [ValidateRange(45, 7200)][int]$DurationSeconds = 75,
    [int]$ExpectedWidth = 1280,
    [int]$ExpectedHeight = 720,
    [string]$ExpectedRendererPattern,
    [int]$HostProcessId = 0,
    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')) 'evidence')
)

$ErrorActionPreference = 'Stop'
$adb = (Get-Command adb -ErrorAction Stop).Source
$angleApkPath = $null
if ($DriverMode -eq 'null') {
    if ([string]::IsNullOrWhiteSpace($AngleApk)) { throw '-AngleApk is required in null mode' }
    $angleApkPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($AngleApk)
}
if ([string]::IsNullOrWhiteSpace($ExpectedRendererPattern)) {
    $ExpectedRendererPattern = if ($DriverMode -eq 'null') { 'NULL' } else { 'SwiftShader' }
}
$unityApkPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($UnityApk)
foreach ($path in @($angleApkPath, $unityApkPath) | Where-Object { $_ }) {
    if (-not (Test-Path -LiteralPath $path)) { throw "APK does not exist: $path" }
}

$capturedAt = [DateTimeOffset]::UtcNow
$captureName = 'g2-{0}-{1}-{2}' -f $DriverMode, $capturedAt.ToString('yyyyMMddTHHmmssZ'),
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

function Write-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)]$Value)
    [IO.File]::WriteAllText($Path,
        ($Value | ConvertTo-Json -Depth 10) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
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
    $top = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'top', '-b', '-n', '1',
        '-p', $ProcessId.ToString()) -AllowFailure
    $cpuPercent = $null
    $processLine = $top -split "`r?`n" | Where-Object { $_ -match "^\s*$ProcessId\s" } |
        Select-Object -First 1
    if ($processLine) {
        $columns = $processLine.Trim() -split '\s+'
        if ($columns.Count -gt 8) {
            $parsed = 0.0
            if ([double]::TryParse($columns[8], [Globalization.NumberStyles]::Float,
                    [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) {
                $cpuPercent = $parsed
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

function Get-HostSample {
    if ($HostProcessId -le 0) { return $null }
    $process = Get-Process -Id $HostProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return [ordered]@{
            captured_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
            process_alive = $false
        }
    }
    return [ordered]@{
        captured_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
        process_alive = $true
        cpu_seconds = [Math]::Round($process.CPU, 6)
        working_set_bytes = [int64]$process.WorkingSet64
        private_memory_bytes = [int64]$process.PrivateMemorySize64
        thread_count = $process.Threads.Count
    }
}

$settingNames = @(
    'angle_debug_package',
    'angle_gl_driver_selection_pkgs',
    'angle_gl_driver_selection_values',
    'show_angle_in_use_dialog_box'
)
$originalSettings = [ordered]@{}
$settingsChanged = $false
$targetPid = ''

try {
    if ($Serial -match '^[^:]+:\d+$') {
        Invoke-Adb -Arguments @('connect', $Serial) | Out-Null
    }
    $deviceState = (Invoke-Adb -Arguments @('-s', $Serial, 'get-state')).Trim()
    if ($deviceState -ne 'device') { throw "ADB device is not ready: '$deviceState'" }
    foreach ($name in $settingNames) { $originalSettings[$name] = Get-GlobalSetting -Name $name }

    if ($DriverMode -eq 'null') {
        Invoke-Adb -Arguments @('-s', $Serial, 'install', '-r', '-d', '--force-queryable',
            $angleApkPath) | Out-Null
    }
    Invoke-Adb -Arguments @('-s', $Serial, 'install', '-r', $unityApkPath) | Out-Null

    $settingsChanged = $true
    if ($DriverMode -eq 'null') {
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
            'angle_debug_package', $AnglePackage) | Out-Null
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
            'angle_gl_driver_selection_pkgs', $UnityPackage) | Out-Null
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
            'angle_gl_driver_selection_values', 'angle') | Out-Null
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
            'show_angle_in_use_dialog_box', '0') | Out-Null
    }
    else {
        foreach ($name in $settingNames) {
            Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'delete', 'global', $name) |
                Out-Null
        }
    }

    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'force-stop', $UnityPackage) | Out-Null
    $externalTelemetryPath = "/sdcard/Android/data/$UnityPackage/files/alas-unity-contract.jsonl"
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'rm', '-f', $externalTelemetryPath) `
        -AllowFailure | Out-Null
    $component = "$UnityPackage/$Activity"
    $startArguments = @('-s', $Serial, 'shell', 'am', 'start', '-W')
    if (-not [string]::IsNullOrWhiteSpace($UnityCommandLine)) {
        $startArguments += @('--es', 'unity', $UnityCommandLine)
    }
    $startArguments += @('-n', $component)
    $startOutput = Invoke-Adb -Arguments $startArguments

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $targetPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $UnityPackage) `
            -AllowFailure).Trim()
        if ($targetPid -match '^\d+$') { break }
        Start-Sleep -Milliseconds 500
    }
    if ($targetPid -notmatch '^\d+$') { throw "Unity probe is not running: '$targetPid'" }

    $samples = [System.Collections.Generic.List[object]]::new()
    $hostSamples = [System.Collections.Generic.List[object]]::new()
    $actions = [System.Collections.Generic.List[object]]::new()
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $clicked = $false
    $pauseResume = $false
    $processFailure = $null
    while ($clock.Elapsed.TotalSeconds -lt $DurationSeconds) {
        $samples.Add((Get-MemorySample -ProcessId ([int]$targetPid)))
        $hostSample = Get-HostSample
        if ($hostSample) { $hostSamples.Add($hostSample) }
        $elapsed = [int][Math]::Floor($clock.Elapsed.TotalSeconds)
        if (-not $clicked -and $elapsed -ge 10) {
            Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'input', 'tap', '640', '580') |
                Out-Null
            $actions.Add([ordered]@{ elapsed_seconds = $elapsed; action = 'tap'; x = 640; y = 580 })
            $clicked = $true
        }
        if (-not $pauseResume -and $elapsed -ge 20) {
            Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'input', 'keyevent', '3') | Out-Null
            $actions.Add([ordered]@{ elapsed_seconds = $elapsed; action = 'home' })
            Start-Sleep -Seconds 3
            Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'start', '-W', '-n', $component) |
                Out-Null
            $actions.Add([ordered]@{ elapsed_seconds = [int]$clock.Elapsed.TotalSeconds; action = 'resume' })
            $pauseResume = $true
        }
        $currentPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $UnityPackage) `
            -AllowFailure).Trim()
        if ($currentPid -ne $targetPid) {
            $processFailure = "Unity process changed or exited: '$currentPid'"
            break
        }
        Start-Sleep -Seconds 5
    }
    $clock.Stop()
    if (-not $processFailure) {
        $samples.Add((Get-MemorySample -ProcessId ([int]$targetPid)))
        $hostSample = Get-HostSample
        if ($hostSample) { $hostSamples.Add($hostSample) }
    }

    $logText = Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '--pid', $targetPid, '-d')
    $telemetryText = Invoke-Adb -Arguments @('-s', $Serial, 'exec-out', 'cat',
        $externalTelemetryPath) -AllowFailure
    [IO.File]::WriteAllText((Join-Path $outputDirectory 'start.txt'),
        $startOutput + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $outputDirectory 'logcat.txt'),
        $logText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $outputDirectory 'telemetry.jsonl'),
        $telemetryText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

    $events = [System.Collections.Generic.List[object]]::new()
    foreach ($line in ($telemetryText -split "`r?`n")) {
        $clean = $line.Trim().TrimStart([char]0xfeff)
        if ($clean.StartsWith('{')) {
            try { $events.Add(($clean | ConvertFrom-Json)) } catch { }
        }
    }
    if ($events.Count -eq 0) {
        foreach ($line in ($logText -split "`r?`n")) {
            if ($line -match 'ALAS_UNITY_CONTRACT\s+(\{.*\})\s*$') {
                try { $events.Add(($Matches[1] | ConvertFrom-Json)) } catch { }
            }
        }
    }
    $startup = @($events | Where-Object event -eq 'startup') | Select-Object -First 1
    $heartbeats = @($events | Where-Object event -eq 'heartbeat')
    $lastHeartbeat = $heartbeats | Select-Object -Last 1
    $asyncOutcomes = @($events | Where-Object event -in @(
        'async-readback', 'async-readback-error', 'async-readback-unsupported'))
    $failures = [System.Collections.Generic.List[string]]::new()
    if ($processFailure) { $failures.Add($processFailure) }
    if (-not $startup) { $failures.Add('missing-startup') }
    elseif ($startup.graphics_device -notmatch $ExpectedRendererPattern) {
        $failures.Add('renderer-not-expected')
    }
    if ($startup -and ($startup.screen_width -ne $ExpectedWidth -or
            $startup.screen_height -ne $ExpectedHeight)) { $failures.Add('unexpected-surface-size') }
    if ($heartbeats.Count -lt 2) { $failures.Add('insufficient-heartbeats') }
    elseif ($lastHeartbeat.updates -le $heartbeats[0].updates -or
        $lastHeartbeat.fixed_updates -le 0 -or $lastHeartbeat.end_of_frame -le 0) {
        $failures.Add('player-loop-not-advancing')
    }
    if (@($events | Where-Object event -eq 'scene-transition').Count -lt 1) {
        $failures.Add('missing-scene-transition')
    }
    if (@($events | Where-Object event -eq 'button-click').Count -lt 1) {
        $failures.Add('missing-button-click')
    }
    if (@($events | Where-Object { $_.event -eq 'application-pause' -and $_.paused }).Count -lt 1 -or
        @($events | Where-Object { $_.event -eq 'application-pause' -and -not $_.paused }).Count -lt 1) {
        $failures.Add('pause-resume-incomplete')
    }
    if ($asyncOutcomes.Count -lt 1) { $failures.Add('missing-async-readback-outcome') }
    if (@($events | Where-Object event -eq 'async-readback-timeout').Count -gt 0) {
        $failures.Add('async-readback-timeout')
    }
    if ($lastHeartbeat -and ($lastHeartbeat.button_semantic -ne 'contract/button-clicked' -or
            $lastHeartbeat.button_generation -lt 2)) { $failures.Add('semantic-state-not-updated') }
    if ($HostProcessId -gt 0 -and ($hostSamples.Count -lt 2 -or
            -not $hostSamples[$hostSamples.Count - 1].process_alive)) {
        $failures.Add('host-process-sampling-incomplete')
    }

    $manifest = [ordered]@{
        schema = 'alas-headless.g2-unity/v2'
        captured_at_utc = $capturedAt.ToString('o')
        serial = $Serial
        driver_mode = $DriverMode
        unity_command_line = if ([string]::IsNullOrWhiteSpace($UnityCommandLine)) {
            $null
        } else { $UnityCommandLine }
        expected_renderer_pattern = $ExpectedRendererPattern
        duration_seconds = [Math]::Round($clock.Elapsed.TotalSeconds, 3)
        angle_apk_sha256 = if ($angleApkPath) {
            (Get-FileHash -LiteralPath $angleApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
        } else { $null }
        unity_apk_sha256 = (Get-FileHash -LiteralPath $unityApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
        pid = [int]$targetPid
        host_process_id = if ($HostProcessId -gt 0) { $HostProcessId } else { $null }
        host_logical_processor_count = [Environment]::ProcessorCount
        original_settings = $originalSettings
        memory_samples = $samples
        host_samples = $hostSamples
        actions = $actions
        event_counts = [ordered]@{
            total = $events.Count
            heartbeat = $heartbeats.Count
            scene_transition = @($events | Where-Object event -eq 'scene-transition').Count
            async_outcome = $asyncOutcomes.Count
        }
        startup = $startup
        last_heartbeat = $lastHeartbeat
        failures = $failures
        passed = $failures.Count -eq 0
    }
    Write-JsonFile -Path (Join-Path $outputDirectory 'manifest.json') -Value $manifest
    if ($failures.Count -gt 0) { throw "G2 contract failed: $($failures -join ', ')" }
    Write-Output $outputDirectory
}
finally {
    if ($settingsChanged) {
        foreach ($name in $settingNames) {
            Restore-GlobalSetting -Name $name -Value $originalSettings[$name]
        }
    }
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'force-stop', $UnityPackage) `
        -AllowFailure | Out-Null
}
