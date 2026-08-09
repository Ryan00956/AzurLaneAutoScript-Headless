[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Serial,
    [Parameter(Mandatory = $true)][string]$AngleApk,
    [Parameter(Mandatory = $true)][string]$UnityApk,
    [string]$AnglePackage = 'org.chromium.angle',
    [string]$UnityPackage = 'io.github.alasheadless.unitycontract',
    [string]$Activity = 'com.unity3d.player.UnityPlayerActivity',
    [string]$UnityCommandLine = '-force-gfx-st',
    [ValidateRange(500, 10000)][int]$MaxFreshnessMs = 2500,
    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')) 'evidence')
)

$ErrorActionPreference = 'Stop'
$adb = (Get-Command adb -ErrorAction Stop).Source
$angleApkPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($AngleApk)
$unityApkPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($UnityApk)
foreach ($path in @($angleApkPath, $unityApkPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "APK does not exist: $path" }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$expectedDriverRevision = (Get-Content -LiteralPath (Join-Path $repoRoot 'ANGLE_REVISION') -Raw).Trim()
$capturedAt = [DateTimeOffset]::UtcNow
$captureName = 'g3-observer-{0}-{1}' -f $capturedAt.ToString('yyyyMMddTHHmmssZ'),
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
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
}

function Get-GlobalSetting {
    param([Parameter(Mandatory = $true)][string]$Name)
    return (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'get', 'global', $Name)).Trim()
}

function Restore-GlobalSetting {
    param([Parameter(Mandatory = $true)][string]$Name, [AllowEmptyString()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -eq 'null') {
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'delete', 'global', $Name) |
            Out-Null
    }
    else {
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global', $Name, $Value) |
            Out-Null
    }
}

function Get-ForegroundPackage {
    $activities = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'dumpsys', 'activity', 'activities')
    $line = $activities -split "`r?`n" | Where-Object { $_ -match 'topResumedActivity=' } |
        Select-Object -First 1
    if ($line -match 'u\d+\s+([^/\s]+)/') { return $Matches[1] }
    return $null
}

function Invoke-ObserverRequest {
    param([Parameter(Mandatory = $true)][int]$Port,
          [Parameter(Mandatory = $true)][string]$Request)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $client.ReceiveTimeout = 3000
        $client.SendTimeout = 3000
        $client.Connect('127.0.0.1', $Port)
        $stream = $client.GetStream()
        $bytes = [Text.Encoding]::ASCII.GetBytes($Request)
        $stream.Write($bytes, 0, $bytes.Length)
        $reader = [IO.StreamReader]::new($stream, [Text.UTF8Encoding]::new($false), $false,
            2048, $true)
        $line = $reader.ReadLine()
        if ([string]::IsNullOrWhiteSpace($line)) { throw 'observer returned an empty response' }
        return ($line | ConvertFrom-Json)
    }
    finally {
        $client.Dispose()
    }
}

function Wait-ObserverSnapshot {
    param([Parameter(Mandatory = $true)][int]$Port,
          [Parameter(Mandatory = $true)][scriptblock]$Predicate,
          [ValidateRange(1, 60)][int]$TimeoutSeconds = 20)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null
    do {
        try {
            $last = Invoke-ObserverRequest -Port $Port -Request "GET /v1/snapshot`n"
            if (& $Predicate $last) { return $last }
        }
        catch {
            $last = [ordered]@{ error = $_.Exception.Message }
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "observer snapshot timeout: $($last | ConvertTo-Json -Compress)"
}

$settingNames = @('angle_debug_package', 'angle_gl_driver_selection_pkgs',
    'angle_gl_driver_selection_values', 'show_angle_in_use_dialog_box')
$originalSettings = [ordered]@{}
$settingsChanged = $false
$forwardPort = $null
$targetPid = $null

try {
    if ($Serial -match '^[^:]+:\d+$') {
        Invoke-Adb -Arguments @('connect', $Serial) | Out-Null
    }
    if ((Invoke-Adb -Arguments @('-s', $Serial, 'get-state')).Trim() -ne 'device') {
        throw 'ADB device is not ready'
    }
    foreach ($name in $settingNames) { $originalSettings[$name] = Get-GlobalSetting -Name $name }

    Invoke-Adb -Arguments @('-s', $Serial, 'install', '-r', '-d', '--force-queryable',
        $angleApkPath) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'install', '-r', $unityApkPath) | Out-Null
    $settingsChanged = $true
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_debug_package', $AnglePackage) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_gl_driver_selection_pkgs', $UnityPackage) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_gl_driver_selection_values', 'angle') | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'show_angle_in_use_dialog_box', '0') | Out-Null

    $component = "$UnityPackage/$Activity"
    $telemetryPath = "/sdcard/Android/data/$UnityPackage/files/alas-unity-contract.jsonl"
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'force-stop', $UnityPackage) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'rm', '-f', $telemetryPath) -AllowFailure |
        Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '-c') | Out-Null
    $startArguments = @('-s', $Serial, 'shell', 'am', 'start', '-W', '--es', 'unity',
        $UnityCommandLine, '-n', $component)
    $startOutput = Invoke-Adb -Arguments $startArguments
    [IO.File]::WriteAllText((Join-Path $outputDirectory 'start.txt'), $startOutput,
        [Text.UTF8Encoding]::new($false))

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $targetPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $UnityPackage) `
            -AllowFailure).Trim()
        if ($targetPid -match '^\d+$') { break }
        Start-Sleep -Milliseconds 500
    }
    if ($targetPid -notmatch '^\d+$') { throw 'Unity process did not start' }
    $socketName = "alas.g3.$targetPid"
    $forwardPort = [int](Invoke-Adb -Arguments @('-s', $Serial, 'forward', 'tcp:0',
        "localabstract:$socketName")).Trim()

    $before = Wait-ObserverSnapshot -Port $forwardPort -TimeoutSeconds 20 -Predicate {
        param($snapshot)
        $snapshot.status -eq 'ok' -and $snapshot.flags -eq 15 -and $snapshot.main_thread -and
        $snapshot.button_count -ge 1 -and $snapshot.interactable_button_count -ge 1 -and
        $snapshot.age_ms -le $MaxFreshnessMs
    }
    $beforeButtons = Invoke-ObserverRequest -Port $forwardPort -Request "GET /v1/buttons`n"
    $foregroundBefore = Get-ForegroundPackage
    $badRequest = Invoke-ObserverRequest -Port $forwardPort -Request "CALL il2cpp_runtime_invoke`n"

    $contractClickTargets = @($beforeButtons.buttons | Where-Object {
        $_.name -ceq 'ContractButton' -and $_.path -ceq 'ContractCanvas/ContractButton' -and
        $_.active_in_hierarchy -and $_.active_and_enabled -and $_.interactable -and
        $_.raycast_top -eq $true -and $_.adb_point -and $_.adb_bounds -and
        $_.adb_bounds.left -lt $_.adb_bounds.right -and
        $_.adb_bounds.top -lt $_.adb_bounds.bottom -and
        $_.adb_point.x -ge $_.adb_bounds.left -and
        $_.adb_point.x -le $_.adb_bounds.right -and
        $_.adb_point.y -ge $_.adb_bounds.top -and
        $_.adb_point.y -le $_.adb_bounds.bottom
    })
    if ($foregroundBefore -ne $UnityPackage -or $contractClickTargets.Count -ne 1) {
        throw 'contract Button is not the unique top EventSystem raycast target'
    }
    $contractClickTarget = $contractClickTargets[0]
    $contractClickX = [int][Math]::Round([double]$contractClickTarget.adb_point.x)
    $contractClickY = [int][Math]::Round([double]$contractClickTarget.adb_point.y)
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'input', 'tap', "$contractClickX",
        "$contractClickY") | Out-Null
    $afterClick = Wait-ObserverSnapshot -Port $forwardPort -TimeoutSeconds 15 -Predicate {
        param($snapshot)
        $snapshot.status -eq 'ok' -and
        [uint64]$snapshot.semantic_generation -gt [uint64]$before.semantic_generation -and
        $snapshot.semantic_code -eq 2 -and $snapshot.interactable_button_count -eq 0 -and
        $snapshot.age_ms -le $MaxFreshnessMs
    }

    $afterScene = Wait-ObserverSnapshot -Port $forwardPort -TimeoutSeconds 25 -Predicate {
        param($snapshot)
        $snapshot.status -eq 'ok' -and
        [uint64]$snapshot.scene_generation -gt [uint64]$afterClick.scene_generation -and
        $snapshot.age_ms -le $MaxFreshnessMs
    }

    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'input', 'keyevent', '3') | Out-Null
    Start-Sleep -Seconds 1
    $foregroundHome = Get-ForegroundPackage
    Start-Sleep -Milliseconds ($MaxFreshnessMs + 750)
    $homeSnapshot = Invoke-ObserverRequest -Port $forwardPort -Request "GET /v1/snapshot`n"
    $homeActionGate = $foregroundHome -eq $UnityPackage -and
        $homeSnapshot.status -eq 'ok' -and $homeSnapshot.age_ms -le $MaxFreshnessMs

    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'start', '-W', '-n', $component) |
        Out-Null
    $afterResume = Wait-ObserverSnapshot -Port $forwardPort -TimeoutSeconds 15 -Predicate {
        param($snapshot)
        $snapshot.status -eq 'ok' -and
        [uint64]$snapshot.generation -gt [uint64]$afterScene.generation -and
        $snapshot.age_ms -le $MaxFreshnessMs
    }
    $foregroundAfterResume = Get-ForegroundPackage
    $afterResumeButtons = Invoke-ObserverRequest -Port $forwardPort -Request "GET /v1/buttons`n"

    $logText = Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '--pid', $targetPid, '-d')
    [IO.File]::WriteAllText((Join-Path $outputDirectory 'logcat.txt'), $logText,
        [Text.UTF8Encoding]::new($false))
    $telemetryText = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'cat', $telemetryPath) `
        -AllowFailure
    [IO.File]::WriteAllText((Join-Path $outputDirectory 'telemetry.jsonl'), $telemetryText,
        [Text.UTF8Encoding]::new($false))
    $unityThread = $null
    $unityThreadLine = $telemetryText -split "`r?`n" |
        Where-Object { $_ -match '"event"\s*:\s*"unity-thread"' } |
        Select-Object -First 1
    if ($unityThreadLine -match '"tid"\s*:\s*(\d+)') {
        $unityThread = [int]$Matches[1]
    }

    $packageDump = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'dumpsys', 'package',
        $UnityPackage)
    $versionCode = if ($packageDump -match 'versionCode=(\d+)') { [int64]$Matches[1] } else { $null }
    $versionName = if ($packageDump -match 'versionName=([^\r\n]+)') { $Matches[1].Trim() } else { $null }
    $buildFingerprint = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'getprop',
        'ro.build.fingerprint')).Trim()
    $abi = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'getprop',
        'ro.product.cpu.abi')).Trim()

    $failures = [System.Collections.Generic.List[string]]::new()
    if ($foregroundBefore -ne $UnityPackage) { $failures.Add('initial-package-not-foreground') }
    if ($badRequest.status -ne 'bad-request') { $failures.Add('unknown-request-not-rejected') }
    if ($badRequest.PSObject.Properties.Name -contains 'generation') {
        $failures.Add('bad-request-leaked-snapshot')
    }
    if ($foregroundHome -eq $UnityPackage) { $failures.Add('home-foreground-gate-failed') }
    if ($homeActionGate) { $failures.Add('home-action-gate-open') }
    if ($homeSnapshot.age_ms -le $MaxFreshnessMs) { $failures.Add('home-snapshot-not-stale') }
    if ($foregroundAfterResume -ne $UnityPackage) { $failures.Add('resume-package-not-foreground') }
    if ($before.protocol_schema -ne 'alas-headless.observer/v1' -or
        $before.snapshot_schema -ne 1) { $failures.Add('observer-schema-mismatch') }
    if ($before.package -ne $UnityPackage -or $before.pid -ne [int]$targetPid) {
        $failures.Add('observer-process-identity-mismatch')
    }
    if ($before.driver_revision -ne $expectedDriverRevision -or $before.abi -ne 'x86_64') {
        $failures.Add('observer-version-fingerprint-mismatch')
    }
    if ($before.peer_uid -ne 2000) { $failures.Add('observer-peer-credential-mismatch') }
    if ($beforeButtons.protocol_schema -ne 'alas-headless.observer/v1' -or
        $beforeButtons.semantic_schema -ne 'alas-headless.buttons/v1' -or
        $beforeButtons.schema -ne 1) {
        $failures.Add('semantic-button-schema-mismatch')
    }
    if ($beforeButtons.package -ne $UnityPackage -or $beforeButtons.pid -ne [int]$targetPid -or
        $beforeButtons.peer_uid -ne 2000 -or
        $beforeButtons.driver_revision -ne $expectedDriverRevision) {
        $failures.Add('semantic-button-identity-mismatch')
    }
    $clickableSemanticButtons = @($beforeButtons.buttons | Where-Object {
        $_.active_in_hierarchy -and $_.active_and_enabled -and $_.interactable -and
        $_.raycast_top -eq $true -and
        -not [string]::IsNullOrWhiteSpace($_.name) -and
        -not [string]::IsNullOrWhiteSpace($_.path) -and $_.adb_point -and
        $_.adb_bounds -and $_.adb_bounds.left -lt $_.adb_bounds.right -and
        $_.adb_bounds.top -lt $_.adb_bounds.bottom -and
        $_.adb_point.x -ge $_.adb_bounds.left -and
        $_.adb_point.x -le $_.adb_bounds.right -and
        $_.adb_point.y -ge $_.adb_bounds.top -and
        $_.adb_point.y -le $_.adb_bounds.bottom -and
        $_.adb_point.x -ge 0 -and $_.adb_point.x -lt 1280 -and
        $_.adb_point.y -ge 0 -and $_.adb_point.y -lt 720
    })
    if ($beforeButtons.status -ne 'ok' -or $beforeButtons.button_count -lt 1 -or
        $beforeButtons.truncated -or $beforeButtons.error_count -ne 0 -or
        $clickableSemanticButtons.Count -lt 1) {
        $failures.Add('semantic-button-record-incomplete')
    }
    if ([uint64]$afterResumeButtons.generation -le [uint64]$beforeButtons.generation -or
        $afterResumeButtons.age_ms -gt $MaxFreshnessMs) {
        $failures.Add('semantic-button-generation-stalled')
    }
    if ($before.ui_stage -ne 100 -or $before.ui_method_mask -ne 15) {
        $failures.Add('typed-ui-probe-incomplete')
    }
    if (-not $unityThread -or $before.observer_tid -ne $unityThread -or
        $afterClick.observer_tid -ne $unityThread -or $afterResume.observer_tid -ne $unityThread) {
        $failures.Add('unity-main-thread-rendezvous-mismatch')
    }
    if (-not $versionCode -or [string]::IsNullOrWhiteSpace($versionName) -or
        [string]::IsNullOrWhiteSpace($buildFingerprint) -or $abi -ne 'x86_64') {
        $failures.Add('android-version-fingerprint-incomplete')
    }
    if ($logText -match 'Fatal signal|FATAL EXCEPTION|AndroidRuntime.*FATAL') {
        $failures.Add('fatal-marker-present')
    }

    $manifest = [ordered]@{
        schema = 'alas-headless.g3-observer/v1'
        captured_at_utc = $capturedAt.ToString('o')
        serial = $Serial
        package = $UnityPackage
        pid = [int]$targetPid
        socket_name = $socketName
        unity_command_line = $UnityCommandLine
        max_freshness_ms = $MaxFreshnessMs
        angle_apk_sha256 = (Get-FileHash -LiteralPath $angleApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
        unity_apk_sha256 = (Get-FileHash -LiteralPath $unityApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
        driver_revision = $expectedDriverRevision
        android_fingerprint = $buildFingerprint
        android_abi = $abi
        package_version_name = $versionName
        package_version_code = $versionCode
        unity_thread_tid = $unityThread
        original_settings = $originalSettings
        foreground = [ordered]@{
            before = $foregroundBefore
            home = $foregroundHome
            after_resume = $foregroundAfterResume
            home_action_gate_allowed = $homeActionGate
        }
        snapshots = [ordered]@{
            before = $before
            after_click = $afterClick
            after_scene = $afterScene
            home = $homeSnapshot
            after_resume = $afterResume
        }
        semantic_snapshots = [ordered]@{
            before = $beforeButtons
            after_resume = $afterResumeButtons
        }
        bad_request_response = $badRequest
        failures = $failures
        passed = $failures.Count -eq 0
    }
    Write-JsonFile -Path (Join-Path $outputDirectory 'manifest.json') -Value $manifest
    if ($failures.Count -gt 0) { throw "G3 observer contract failed: $($failures -join ', ')" }
    Write-Output $outputDirectory
}
finally {
    if ($forwardPort) {
        Invoke-Adb -Arguments @('-s', $Serial, 'forward', '--remove', "tcp:$forwardPort") `
            -AllowFailure | Out-Null
    }
    if ($settingsChanged) {
        foreach ($name in $settingNames) {
            Restore-GlobalSetting -Name $name -Value $originalSettings[$name]
        }
    }
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'force-stop', $UnityPackage) `
        -AllowFailure | Out-Null
}
