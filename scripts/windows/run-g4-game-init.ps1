[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Serial,
    [Parameter(Mandatory = $true)][string]$AngleApk,
    [string]$AnglePackage = 'org.chromium.angle',
    [string]$GamePackage = 'com.bilibili.azurlane',
    [string]$Activity = 'com.manjuu.azurlane.MainActivity',
    [string]$UnityCommandLine = '-force-gfx-st',
    [string]$ExpectedVersionName = '9.7.10',
    [int64]$ExpectedVersionCode = 9710,
    [string]$ExpectedBaseApkSha256 =
        'e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f',
    [string]$ExpectedIl2CppSha256 =
        'e3f1cfc442b67f1d4c9877fd9ceaedc3d68f2842ad677445241b9cc9c05d1c67',
    [ValidateRange(500, 10000)][int]$MaxFreshnessMs = 2500,
    [ValidateRange(10, 300)][int]$StartupTimeoutSeconds = 120,
    [ValidateRange(0, 600)][int]$ObservationSeconds = 0,
    [ValidateRange(250, 10000)][int]$ObservationIntervalMs = 1000,
    [switch]$RequireSemanticButtons,
    [string]$SemanticClickPath = '',
    [string]$ExpectedPostClickName = '',
    [string]$ExpectedPostClickPathSuffix = '',
    [ValidateRange(10, 300)][int]$SemanticClickTimeoutSeconds = 180,
    [string]$ProbePageClickName = '',
    [string]$ProbePageClickPathSuffix = '',
    [string]$ProbePageBackName = 'back_btn',
    [string]$ProbePageBackPathSuffix =
        'NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn',
    [string]$DismissOverlayName = '',
    [string]$DismissOverlayPathSuffix = '',
    [ValidateRange(5, 120)][int]$ProbePageTimeoutSeconds = 30,
    [switch]$AllowRunningProcessRestart,
    [switch]$KeepGameRunningAfterPass,
    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')) 'evidence')
)

$ErrorActionPreference = 'Stop'
$adb = (Get-Command adb -ErrorAction Stop).Source
$angleApkPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($AngleApk)
if (-not (Test-Path -LiteralPath $angleApkPath)) {
    throw "ANGLE APK does not exist: $angleApkPath"
}
if (-not [string]::IsNullOrWhiteSpace($SemanticClickPath) -and
    ([string]::IsNullOrWhiteSpace($ExpectedPostClickName) -or
     [string]::IsNullOrWhiteSpace($ExpectedPostClickPathSuffix))) {
    throw 'semantic click requires both ExpectedPostClickName and ExpectedPostClickPathSuffix'
}
if ([string]::IsNullOrWhiteSpace($ProbePageClickName) -xor
    [string]::IsNullOrWhiteSpace($ProbePageClickPathSuffix)) {
    throw 'page-loop probe requires both ProbePageClickName and ProbePageClickPathSuffix'
}
if (-not [string]::IsNullOrWhiteSpace($ProbePageClickName) -and
    [string]::IsNullOrWhiteSpace($SemanticClickPath)) {
    throw 'page-loop probe requires a successful semantic entry click first'
}
if (-not [string]::IsNullOrWhiteSpace($ProbePageClickName) -and
    ([string]::IsNullOrWhiteSpace($ProbePageBackName) -or
     [string]::IsNullOrWhiteSpace($ProbePageBackPathSuffix))) {
    throw 'page-loop probe requires an exact semantic back target'
}
if ([string]::IsNullOrWhiteSpace($DismissOverlayName) -xor
    [string]::IsNullOrWhiteSpace($DismissOverlayPathSuffix)) {
    throw 'overlay dismissal requires both DismissOverlayName and DismissOverlayPathSuffix'
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$expectedDriverRevision = (Get-Content -LiteralPath (Join-Path $repoRoot 'ANGLE_REVISION') -Raw).Trim()
$capturedAt = [DateTimeOffset]::UtcNow
$captureName = 'g4-game-init-{0}-{1}' -f $capturedAt.ToString('yyyyMMddTHHmmssZ'),
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

function Write-Utf8File {
    param([Parameter(Mandatory = $true)][string]$Path,
          [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    [IO.File]::WriteAllText($Path, $Value, [Text.UTF8Encoding]::new($false))
}

function Write-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)]$Value)
    Write-Utf8File -Path $Path -Value (($Value | ConvertTo-Json -Depth 12) +
        [Environment]::NewLine)
}

function Get-GlobalSetting {
    param([Parameter(Mandatory = $true)][string]$Name)
    return (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'get', 'global',
        $Name)).Trim()
}

function Restore-GlobalSetting {
    param([Parameter(Mandatory = $true)][string]$Name, [AllowEmptyString()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -eq 'null') {
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'delete', 'global', $Name) |
            Out-Null
    }
    else {
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global', $Name,
            $Value) | Out-Null
    }
}

function Get-ForegroundComponent {
    $activities = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'dumpsys', 'activity',
        'activities')
    $line = $activities -split "`r?`n" | Where-Object { $_ -match 'topResumedActivity=' } |
        Select-Object -First 1
    if ($line -match 'u\d+\s+([^\s}]+/[^\s}]+)') { return $Matches[1] }
    return $null
}

function Get-ForegroundPackage {
    $component = Get-ForegroundComponent
    if ($component -match '^([^/]+)/') { return $Matches[1] }
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
          [Parameter(Mandatory = $true)][int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null
    do {
        try {
            $last = Invoke-ObserverRequest -Port $Port -Request "GET /v1/snapshot`n"
            $script:lastObserverResponse = $last
            if (& $Predicate $last) { return $last }
        }
        catch {
            $last = [ordered]@{ error = $_.Exception.Message }
            $script:lastObserverResponse = $last
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "observer snapshot timeout: $($last | ConvertTo-Json -Compress)"
}

function Get-Sha256FromDevice {
    param([Parameter(Mandatory = $true)][string]$Path)
    $output = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'sha256sum', '--', $Path)
    if ($output -notmatch '^([0-9a-fA-F]{64})\s') { throw "invalid sha256sum output: $output" }
    return $Matches[1].ToLowerInvariant()
}

$settingNames = @('angle_debug_package', 'angle_gl_driver_selection_pkgs',
    'angle_gl_driver_selection_values', 'show_angle_in_use_dialog_box')
$originalSettings = [ordered]@{}
$settingsChanged = $false
$forwardPort = $null
$targetPid = $null
$script:lastObserverResponse = $null
$runPassed = $false

try {
    if ((Invoke-Adb -Arguments @('-s', $Serial, 'get-state')).Trim() -ne 'device') {
        throw 'ADB device is not ready'
    }
    $initialPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $GamePackage) `
        -AllowFailure).Trim()
    if ($initialPid -and -not $AllowRunningProcessRestart) {
        throw "game process is already running ($initialPid); pass -AllowRunningProcessRestart only on a test guest"
    }

    $packageDump = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'dumpsys', 'package',
        $GamePackage)
    $versionCode = if ($packageDump -match 'versionCode=(\d+)') { [int64]$Matches[1] } else { $null }
    $versionName = if ($packageDump -match 'versionName=([^\r\n]+)') {
        $Matches[1].Trim()
    }
    else { $null }
    $primaryAbi = if ($packageDump -match 'primaryCpuAbi=([^\r\n]+)') {
        $Matches[1].Trim()
    }
    else { $null }
    $basePath = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pm', 'path', $GamePackage)).Trim() `
        -replace '^package:', ''
    if ($packageDump -notmatch 'nativeLibraryDir=([^\r\n]+)') {
        throw 'nativeLibraryDir is missing from the package fingerprint'
    }
    $nativeLibraryDir = $Matches[1].Trim()
    $il2CppPaths = @((Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'find',
        $nativeLibraryDir, '-type', 'f', '-name', 'libil2cpp.so', '-print')) -split "`r?`n" |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($il2CppPaths.Count -ne 1) {
        throw "expected exactly one libil2cpp.so below nativeLibraryDir, found $($il2CppPaths.Count)"
    }
    $il2CppPath = $il2CppPaths[0].Trim()
    $baseApkSha256 = Get-Sha256FromDevice -Path $basePath
    $il2CppSha256 = Get-Sha256FromDevice -Path $il2CppPath
    if ($versionName -ne $ExpectedVersionName -or $versionCode -ne $ExpectedVersionCode -or
        $primaryAbi -ne 'x86_64' -or $baseApkSha256 -ne $ExpectedBaseApkSha256 -or
        $il2CppSha256 -ne $ExpectedIl2CppSha256) {
        throw 'game package fingerprint does not match the pinned G4 target'
    }

    foreach ($name in $settingNames) { $originalSettings[$name] = Get-GlobalSetting -Name $name }
    Invoke-Adb -Arguments @('-s', $Serial, 'install', '-r', '-d', '--force-queryable',
        $angleApkPath) | Out-Null
    $settingsChanged = $true
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_debug_package', $AnglePackage) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_gl_driver_selection_pkgs', $GamePackage) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'angle_gl_driver_selection_values', 'angle') | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'settings', 'put', 'global',
        'show_angle_in_use_dialog_box', '0') | Out-Null

    Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'force-stop', $GamePackage) | Out-Null
    Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '-c') | Out-Null
    $component = "$GamePackage/$Activity"
    $startOutput = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'start', '-W',
        '--es', 'unity', $UnityCommandLine, '-n', $component)
    Write-Utf8File -Path (Join-Path $outputDirectory 'start.txt') -Value $startOutput

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    do {
        $targetPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $GamePackage) `
            -AllowFailure).Trim()
        if ($targetPid -match '^\d+$') { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    if ($targetPid -notmatch '^\d+$') { throw 'game process did not start' }

    $socketName = "alas.g3.$targetPid"
    $forwardPort = [int](Invoke-Adb -Arguments @('-s', $Serial, 'forward', 'tcp:0',
        "localabstract:$socketName")).Trim()
    $first = Wait-ObserverSnapshot -Port $forwardPort -TimeoutSeconds $StartupTimeoutSeconds `
        -Predicate {
            param($snapshot)
            $snapshot.status -eq 'ok' -and $snapshot.flags -eq 15 -and
            $snapshot.main_thread -and $snapshot.age_ms -le $MaxFreshnessMs
        }
    $second = Wait-ObserverSnapshot -Port $forwardPort -TimeoutSeconds 20 -Predicate {
        param($snapshot)
        $snapshot.status -eq 'ok' -and
        [uint64]$snapshot.generation -gt [uint64]$first.generation -and
        $snapshot.age_ms -le $MaxFreshnessMs
    }
    $badRequest = Invoke-ObserverRequest -Port $forwardPort `
        -Request "CALL il2cpp_runtime_invoke`n"

    $observationRecords = [System.Collections.Generic.List[object]]::new()
    if ($ObservationSeconds -gt 0) {
        $observationDeadline = [DateTimeOffset]::UtcNow.AddSeconds($ObservationSeconds)
        do {
            $sampledAt = [DateTimeOffset]::UtcNow
            try {
                $sample = Invoke-ObserverRequest -Port $forwardPort `
                    -Request "GET /v1/snapshot`n"
                $script:lastObserverResponse = $sample
                $observationRecords.Add([ordered]@{
                    captured_at_utc = $sampledAt.ToString('o')
                    snapshot = $sample
                })
            }
            catch {
                $observationRecords.Add([ordered]@{
                    captured_at_utc = $sampledAt.ToString('o')
                    error = $_.Exception.Message
                })
            }
            if ([DateTimeOffset]::UtcNow -lt $observationDeadline) {
                Start-Sleep -Milliseconds $ObservationIntervalMs
            }
        } while ([DateTimeOffset]::UtcNow -lt $observationDeadline)
        Write-JsonFile -Path (Join-Path $outputDirectory 'observations.json') `
            -Value $observationRecords
    }

    $validObservations = @($observationRecords | Where-Object {
        $_.snapshot -and $_.snapshot.status -eq 'ok'
    })
    $freshObservations = @($validObservations | Where-Object {
        $_.snapshot.age_ms -le $MaxFreshnessMs -and $_.snapshot.main_thread -and
        $_.snapshot.flags -eq 15
    })
    $observationGenerations = @($validObservations | ForEach-Object {
        [uint64]$_.snapshot.generation
    })
    $lastObservation = if ($validObservations.Count -gt 0) {
        $validObservations[-1].snapshot
    }
    else { $null }
    $observationSummary = [ordered]@{
        requested_seconds = $ObservationSeconds
        interval_ms = $ObservationIntervalMs
        sample_count = $observationRecords.Count
        valid_sample_count = $validObservations.Count
        fresh_sample_count = $freshObservations.Count
        first_generation = if ($observationGenerations.Count -gt 0) {
            $observationGenerations[0]
        }
        else { $null }
        last_generation = if ($observationGenerations.Count -gt 0) {
            $observationGenerations[-1]
        }
        else { $null }
        distinct_generation_count = @($observationGenerations | Sort-Object -Unique).Count
        distinct_scene_handles = @($validObservations | ForEach-Object {
            $_.snapshot.scene_handle
        } | Sort-Object -Unique)
        maximum_button_count = if ($validObservations.Count -gt 0) {
            ($validObservations | ForEach-Object { $_.snapshot.button_count } |
                Measure-Object -Maximum).Maximum
        }
        else { $null }
        maximum_active_button_count = if ($validObservations.Count -gt 0) {
            ($validObservations | ForEach-Object { $_.snapshot.active_button_count } |
                Measure-Object -Maximum).Maximum
        }
        else { $null }
        maximum_interactable_button_count = if ($validObservations.Count -gt 0) {
            ($validObservations | ForEach-Object { $_.snapshot.interactable_button_count } |
                Measure-Object -Maximum).Maximum
        }
        else { $null }
    }
    $semanticButtons = Invoke-ObserverRequest -Port $forwardPort -Request "GET /v1/buttons`n"
    Write-JsonFile -Path (Join-Path $outputDirectory 'buttons.json') -Value $semanticButtons
    $actionableSemanticButtons = @($semanticButtons.buttons | Where-Object {
        $_.active_in_hierarchy -and $_.active_and_enabled -and $_.interactable -and
        $_.raycast_top -eq $true -and
        -not [string]::IsNullOrWhiteSpace($_.name) -and
        -not [string]::IsNullOrWhiteSpace($_.path) -and $_.adb_point -and
        $_.adb_bounds -and $_.adb_bounds.left -lt $_.adb_bounds.right -and
        $_.adb_bounds.top -lt $_.adb_bounds.bottom -and
        $_.adb_point.x -ge $_.adb_bounds.left -and $_.adb_point.x -le $_.adb_bounds.right -and
        $_.adb_point.y -ge $_.adb_bounds.top -and $_.adb_point.y -le $_.adb_bounds.bottom -and
        $_.adb_point.x -ge 0 -and $_.adb_point.x -lt 1280 -and
        $_.adb_point.y -ge 0 -and $_.adb_point.y -lt 720
    })
    $foregroundComponent = Get-ForegroundComponent
    $foreground = if ($foregroundComponent -match '^([^/]+)/') { $Matches[1] } else { $null }
    $semanticClick = $null
    if (-not [string]::IsNullOrWhiteSpace($SemanticClickPath)) {
        $clickTargets = @($semanticButtons.buttons | Where-Object {
            $_.path -ceq $SemanticClickPath
        })
        if ($foregroundComponent -ne $component -or $semanticButtons.status -ne 'ok' -or
            $semanticButtons.age_ms -gt $MaxFreshnessMs -or $semanticButtons.truncated -or
            $semanticButtons.error_count -ne 0 -or $clickTargets.Count -ne 1) {
            throw 'refusing semantic click because its fail-closed preconditions are not met'
        }
        $clickTarget = $clickTargets[0]
        if (-not $clickTarget.active_in_hierarchy -or -not $clickTarget.active_and_enabled -or
            -not $clickTarget.interactable -or $clickTarget.raycast_top -ne $true -or
            -not $clickTarget.adb_point -or
            -not $clickTarget.adb_bounds -or
            $clickTarget.adb_bounds.left -ge $clickTarget.adb_bounds.right -or
            $clickTarget.adb_bounds.top -ge $clickTarget.adb_bounds.bottom -or
            $clickTarget.adb_point.x -lt $clickTarget.adb_bounds.left -or
            $clickTarget.adb_point.x -gt $clickTarget.adb_bounds.right -or
            $clickTarget.adb_point.y -lt $clickTarget.adb_bounds.top -or
            $clickTarget.adb_point.y -gt $clickTarget.adb_bounds.bottom -or
            $clickTarget.adb_point.x -lt 0 -or $clickTarget.adb_point.x -ge 1280 -or
            $clickTarget.adb_point.y -lt 0 -or $clickTarget.adb_point.y -ge 720) {
            throw 'refusing semantic click because the target is not actionable'
        }
        $clickX = [int][Math]::Round([double]$clickTarget.adb_point.x)
        $clickY = [int][Math]::Round([double]$clickTarget.adb_point.y)
        $clickIssuedAt = [DateTimeOffset]::UtcNow
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'input', 'tap', "$clickX", "$clickY") |
            Out-Null

        $postClickButtons = $null
        $postClickTarget = $null
        $clickDeadline = [DateTimeOffset]::UtcNow.AddSeconds($SemanticClickTimeoutSeconds)
        do {
            Start-Sleep -Milliseconds 750
            $currentPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $GamePackage) `
                -AllowFailure).Trim()
            if ($currentPid -ne $targetPid) {
                throw 'game process changed after semantic click'
            }
            try {
                $candidateButtons = Invoke-ObserverRequest -Port $forwardPort `
                    -Request "GET /v1/buttons`n"
                $script:lastObserverResponse = $candidateButtons
                $matches = @($candidateButtons.buttons | Where-Object {
                    $_.name -ceq $ExpectedPostClickName -and $_.path -and
                    $_.path.EndsWith($ExpectedPostClickPathSuffix,
                        [StringComparison]::Ordinal) -and
                    $_.active_in_hierarchy -and $_.active_and_enabled -and $_.interactable -and
                    $_.adb_point
                })
                if ($candidateButtons.status -eq 'ok' -and
                    $candidateButtons.age_ms -le $MaxFreshnessMs -and $matches.Count -eq 1) {
                    $postClickButtons = $candidateButtons
                    $postClickTarget = $matches[0]
                    break
                }
            }
            catch { }
        } while ([DateTimeOffset]::UtcNow -lt $clickDeadline)
        if (-not $postClickTarget) {
            throw 'semantic click did not reach the expected post-click UI'
        }
        $postClickForegroundComponent = Get-ForegroundComponent
        if ($postClickForegroundComponent -ne $component) {
            throw 'game activity is not foreground after semantic click'
        }
        $postClickSnapshot = Invoke-ObserverRequest -Port $forwardPort `
            -Request "GET /v1/snapshot`n"
        Write-JsonFile -Path (Join-Path $outputDirectory 'buttons.after-click.json') `
            -Value $postClickButtons
        $semanticClick = [ordered]@{
            issued_at_utc = $clickIssuedAt.ToString('o')
            target = $clickTarget
            adb_point = [ordered]@{ x = $clickX; y = $clickY }
            post_click_target = $postClickTarget
            post_click_buttons = $postClickButtons
            post_click_snapshot = $postClickSnapshot
            post_click_foreground_component = $postClickForegroundComponent
        }
    }
    $pageLoop = $null
    if (-not [string]::IsNullOrWhiteSpace($ProbePageClickName)) {
        $mainButtons = $semanticClick.post_click_buttons
        $overlayDismissal = $null
        $settledMainButtons = $null
        $settledGenerationCount = 0
        $lastSettledGeneration = [uint64]$mainButtons.generation
        $settleDeadline = [DateTimeOffset]::UtcNow.AddSeconds($ProbePageTimeoutSeconds)
        do {
            Start-Sleep -Milliseconds 750
            try {
                $candidate = Invoke-ObserverRequest -Port $forwardPort `
                    -Request "GET /v1/buttons`n"
                $script:lastObserverResponse = $candidate
                $loadingButtons = @($candidate.buttons | Where-Object {
                    $_.name -ceq 'Loading(Clone)' -or
                    ($_.path -and $_.path.Contains('/UIOverlay/Loading(Clone)',
                        [StringComparison]::Ordinal))
                })
                $requiredMainTargets = @($candidate.buttons | Where-Object {
                    ($_.name -ceq $ProbePageClickName -and $_.path -and
                     $_.path.EndsWith($ProbePageClickPathSuffix,
                         [StringComparison]::Ordinal)) -or
                    ($_.name -ceq $ExpectedPostClickName -and $_.path -and
                     $_.path.EndsWith($ExpectedPostClickPathSuffix,
                         [StringComparison]::Ordinal))
                })
                if ($candidate.status -eq 'ok' -and
                    $candidate.age_ms -le $MaxFreshnessMs -and -not $candidate.truncated -and
                    $candidate.error_count -eq 0 -and $loadingButtons.Count -eq 0 -and
                    $requiredMainTargets.Count -eq 2 -and
                    [uint64]$candidate.generation -gt $lastSettledGeneration) {
                    $lastSettledGeneration = [uint64]$candidate.generation
                    ++$settledGenerationCount
                    $settledMainButtons = $candidate
                    if ($settledGenerationCount -ge 5) { break }
                }
            }
            catch { }
        } while ([DateTimeOffset]::UtcNow -lt $settleDeadline)
        if (-not $settledMainButtons -or $settledGenerationCount -lt 5) {
            throw 'main semantic UI did not settle after entry'
        }
        $mainButtons = $settledMainButtons

        $bulletinButtons = @($mainButtons.buttons | Where-Object {
            $_.path -and $_.path.Contains('/NewBulletinBoardUI(Clone)/',
                [StringComparison]::Ordinal)
        })
        if ($bulletinButtons.Count -gt 0) {
            $dismissTargets = @($bulletinButtons | Where-Object {
                $_.name -ceq $DismissOverlayName -and
                $_.path.EndsWith($DismissOverlayPathSuffix, [StringComparison]::Ordinal) -and
                $_.active_in_hierarchy -and $_.active_and_enabled -and $_.interactable -and
                $_.raycast_top -eq $true -and
                $_.adb_point -and $_.adb_bounds -and
                $_.adb_bounds.left -lt $_.adb_bounds.right -and
                $_.adb_bounds.top -lt $_.adb_bounds.bottom -and
                $_.adb_point.x -ge $_.adb_bounds.left -and
                $_.adb_point.x -le $_.adb_bounds.right -and
                $_.adb_point.y -ge $_.adb_bounds.top -and
                $_.adb_point.y -le $_.adb_bounds.bottom -and
                $_.adb_point.x -ge 0 -and $_.adb_point.x -lt 1280 -and
                $_.adb_point.y -ge 0 -and $_.adb_point.y -lt 720
            })
            if ($bulletinButtons.Count -ne 1 -or $dismissTargets.Count -ne 1 -or
                (Get-ForegroundComponent) -ne $component) {
                throw 'refusing page-loop because the bulletin overlay is not uniquely mapped'
            }
            $dismissTarget = $dismissTargets[0]
            $dismissX = [int][Math]::Round([double]$dismissTarget.adb_point.x)
            $dismissY = [int][Math]::Round([double]$dismissTarget.adb_point.y)
            $dismissIssuedAt = [DateTimeOffset]::UtcNow
            Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'input', 'tap', "$dismissX",
                "$dismissY") | Out-Null
            $afterDismissButtons = $null
            $dismissDeadline = [DateTimeOffset]::UtcNow.AddSeconds($ProbePageTimeoutSeconds)
            do {
                Start-Sleep -Milliseconds 750
                try {
                    $candidate = Invoke-ObserverRequest -Port $forwardPort `
                        -Request "GET /v1/buttons`n"
                    $script:lastObserverResponse = $candidate
                    $remainingBulletinButtons = @($candidate.buttons | Where-Object {
                        $_.path -and $_.path.Contains('/NewBulletinBoardUI(Clone)/',
                            [StringComparison]::Ordinal)
                    })
                    $remainingLoadingButtons = @($candidate.buttons | Where-Object {
                        $_.name -ceq 'Loading(Clone)' -or
                        ($_.path -and $_.path.Contains('/UIOverlay/Loading(Clone)',
                            [StringComparison]::Ordinal))
                    })
                    $requiredMainTargets = @($candidate.buttons | Where-Object {
                        ($_.name -ceq $ProbePageClickName -and $_.path -and
                         $_.path.EndsWith($ProbePageClickPathSuffix,
                             [StringComparison]::Ordinal)) -or
                        ($_.name -ceq $ExpectedPostClickName -and $_.path -and
                         $_.path.EndsWith($ExpectedPostClickPathSuffix,
                             [StringComparison]::Ordinal))
                    })
                    if ($candidate.status -eq 'ok' -and
                        $candidate.age_ms -le $MaxFreshnessMs -and
                        $remainingBulletinButtons.Count -eq 0 -and
                        $remainingLoadingButtons.Count -eq 0 -and
                        $requiredMainTargets.Count -eq 2 -and
                        [uint64]$candidate.generation -gt [uint64]$mainButtons.generation) {
                        $afterDismissButtons = $candidate
                        break
                    }
                }
                catch { }
            } while ([DateTimeOffset]::UtcNow -lt $dismissDeadline)
            if (-not $afterDismissButtons) {
                throw 'mapped overlay dismissal did not restore an unobstructed main UI'
            }
            Write-JsonFile -Path (Join-Path $outputDirectory 'buttons.after-overlay-dismiss.json') `
                -Value $afterDismissButtons
            $overlayDismissal = [ordered]@{
                issued_at_utc = $dismissIssuedAt.ToString('o')
                target = $dismissTarget
                adb_point = [ordered]@{ x = $dismissX; y = $dismissY }
                after_buttons = $afterDismissButtons
            }
            $mainButtons = $afterDismissButtons
        }
        $pageClickTargets = @($mainButtons.buttons | Where-Object {
            $_.name -ceq $ProbePageClickName -and $_.path -and
            $_.path.EndsWith($ProbePageClickPathSuffix, [StringComparison]::Ordinal) -and
            $_.active_in_hierarchy -and $_.active_and_enabled -and $_.interactable -and
            $_.raycast_top -eq $true -and
            $_.adb_point -and $_.adb_bounds -and
            $_.adb_bounds.left -lt $_.adb_bounds.right -and
            $_.adb_bounds.top -lt $_.adb_bounds.bottom -and
            $_.adb_point.x -ge $_.adb_bounds.left -and
            $_.adb_point.x -le $_.adb_bounds.right -and
            $_.adb_point.y -ge $_.adb_bounds.top -and
            $_.adb_point.y -le $_.adb_bounds.bottom -and
            $_.adb_point.x -ge 0 -and $_.adb_point.x -lt 1280 -and
            $_.adb_point.y -ge 0 -and $_.adb_point.y -lt 720
        })
        if ($pageClickTargets.Count -ne 1 -or
            (Get-ForegroundComponent) -ne $component) {
            throw 'refusing page-loop click because its fail-closed preconditions are not met'
        }
        $pageClickTarget = $pageClickTargets[0]
        $pageClickX = [int][Math]::Round([double]$pageClickTarget.adb_point.x)
        $pageClickY = [int][Math]::Round([double]$pageClickTarget.adb_point.y)
        $pageClickIssuedAt = [DateTimeOffset]::UtcNow
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'input', 'tap', "$pageClickX",
            "$pageClickY") | Out-Null

        $pageButtons = $null
        $pageCandidateGeneration = [uint64]0
        $firstPageNewPaths = $null
        $mainPathSet = [Collections.Generic.HashSet[string]]::new(
            [StringComparer]::Ordinal)
        foreach ($button in $mainButtons.buttons) {
            if ($button.path) { [void]$mainPathSet.Add([string]$button.path) }
        }
        $pageDeadline = [DateTimeOffset]::UtcNow.AddSeconds($ProbePageTimeoutSeconds)
        do {
            Start-Sleep -Milliseconds 750
            try {
                $candidate = Invoke-ObserverRequest -Port $forwardPort `
                    -Request "GET /v1/buttons`n"
                $script:lastObserverResponse = $candidate
                $newPagePaths = @($candidate.buttons | Where-Object {
                    $_.path -and -not $mainPathSet.Contains([string]$_.path)
                } | ForEach-Object {
                    [string]$_.path
                })
                $validPageCandidate = $candidate.status -eq 'ok' -and
                    $candidate.age_ms -le $MaxFreshnessMs -and -not $candidate.truncated -and
                    $candidate.error_count -eq 0 -and $candidate.button_count -gt 0 -and
                    $newPagePaths.Count -gt 0 -and
                    [uint64]$candidate.generation -gt [uint64]$mainButtons.generation
                if ($validPageCandidate -and $pageCandidateGeneration -eq 0) {
                    $pageCandidateGeneration = [uint64]$candidate.generation
                    $firstPageNewPaths = [Collections.Generic.HashSet[string]]::new(
                        [string[]]$newPagePaths, [StringComparer]::Ordinal)
                }
                elseif ($validPageCandidate -and
                    [uint64]$candidate.generation -gt $pageCandidateGeneration) {
                    $stableNewPaths = @($newPagePaths | Where-Object {
                        $firstPageNewPaths.Contains([string]$_)
                    })
                    if ($stableNewPaths.Count -gt 0) {
                        $pageButtons = $candidate
                        break
                    }
                }
            }
            catch { }
        } while ([DateTimeOffset]::UtcNow -lt $pageDeadline)
        if (-not $pageButtons) {
            throw 'page-loop click did not reach a stable non-main semantic UI'
        }
        if ((Get-ForegroundComponent) -ne $component) {
            throw 'game activity is not foreground on the page-loop target'
        }
        Write-JsonFile -Path (Join-Path $outputDirectory 'buttons.page.json') -Value $pageButtons

        $backTargets = @($pageButtons.buttons | Where-Object {
            $_.name -ceq $ProbePageBackName -and $_.path -and
            $_.path.EndsWith($ProbePageBackPathSuffix, [StringComparison]::Ordinal) -and
            $_.active_in_hierarchy -and $_.active_and_enabled -and $_.interactable -and
            $_.raycast_top -eq $true -and $_.adb_point -and $_.adb_bounds -and
            $_.adb_bounds.left -lt $_.adb_bounds.right -and
            $_.adb_bounds.top -lt $_.adb_bounds.bottom -and
            $_.adb_point.x -ge $_.adb_bounds.left -and
            $_.adb_point.x -le $_.adb_bounds.right -and
            $_.adb_point.y -ge $_.adb_bounds.top -and
            $_.adb_point.y -le $_.adb_bounds.bottom -and
            $_.adb_point.x -ge 0 -and $_.adb_point.x -lt 1280 -and
            $_.adb_point.y -ge 0 -and $_.adb_point.y -lt 720
        })
        if ($backTargets.Count -ne 1 -or (Get-ForegroundComponent) -ne $component) {
            throw 'refusing page-loop return because its semantic target is not actionable'
        }
        $backTarget = $backTargets[0]
        $backX = [int][Math]::Round([double]$backTarget.adb_point.x)
        $backY = [int][Math]::Round([double]$backTarget.adb_point.y)
        $backIssuedAt = [DateTimeOffset]::UtcNow
        $pageAddedPathSet = [Collections.Generic.HashSet[string]]::new(
            [StringComparer]::Ordinal)
        foreach ($button in $pageButtons.buttons) {
            if ($button.path -and -not $mainPathSet.Contains([string]$button.path)) {
                [void]$pageAddedPathSet.Add([string]$button.path)
            }
        }
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'input', 'tap', "$backX", "$backY") |
            Out-Null
        $returnedButtons = $null
        $returnDeadline = [DateTimeOffset]::UtcNow.AddSeconds($ProbePageTimeoutSeconds)
        do {
            Start-Sleep -Milliseconds 750
            try {
                $candidate = Invoke-ObserverRequest -Port $forwardPort `
                    -Request "GET /v1/buttons`n"
                $script:lastObserverResponse = $candidate
                $returnedMainTargets = @($candidate.buttons | Where-Object {
                    ($_.name -ceq $ProbePageClickName -and $_.path -and
                     $_.path.EndsWith($ProbePageClickPathSuffix,
                         [StringComparison]::Ordinal)) -or
                    ($_.name -ceq $ExpectedPostClickName -and $_.path -and
                     $_.path.EndsWith($ExpectedPostClickPathSuffix,
                         [StringComparison]::Ordinal))
                })
                $remainingPagePaths = @($candidate.buttons | Where-Object {
                    $_.path -and $pageAddedPathSet.Contains([string]$_.path)
                })
                if ($candidate.status -eq 'ok' -and
                    $candidate.age_ms -le $MaxFreshnessMs -and -not $candidate.truncated -and
                    $candidate.error_count -eq 0 -and $returnedMainTargets.Count -eq 2 -and
                    $remainingPagePaths.Count -eq 0 -and
                    [uint64]$candidate.generation -gt [uint64]$pageButtons.generation) {
                    $returnedButtons = $candidate
                    break
                }
            }
            catch { }
        } while ([DateTimeOffset]::UtcNow -lt $returnDeadline)
        if (-not $returnedButtons -or (Get-ForegroundComponent) -ne $component) {
            throw 'page-loop back action did not restore the expected main semantic UI'
        }
        Write-JsonFile -Path (Join-Path $outputDirectory 'buttons.after-return.json') `
            -Value $returnedButtons
        $pageLoop = [ordered]@{
            overlay_dismissal = $overlayDismissal
            click_issued_at_utc = $pageClickIssuedAt.ToString('o')
            click_target = $pageClickTarget
            click_adb_point = [ordered]@{ x = $pageClickX; y = $pageClickY }
            page_buttons = $pageButtons
            back_issued_at_utc = $backIssuedAt.ToString('o')
            back_target = $backTarget
            back_adb_point = [ordered]@{ x = $backX; y = $backY }
            returned_buttons = $returnedButtons
            foreground_component = Get-ForegroundComponent
        }
    }
    $logText = Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '--pid', $targetPid, '-d')
    Write-Utf8File -Path (Join-Path $outputDirectory 'logcat.txt') -Value $logText
    $maps = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'cat', "/proc/$targetPid/maps") `
        -AllowFailure
    Write-Utf8File -Path (Join-Path $outputDirectory 'process-maps.txt') -Value $maps

    $failures = [System.Collections.Generic.List[string]]::new()
    if ($foreground -ne $GamePackage) { $failures.Add('game-not-foreground') }
    if ($foregroundComponent -ne $component) { $failures.Add('unity-activity-not-foreground') }
    if ($badRequest.status -ne 'bad-request') { $failures.Add('unknown-request-not-rejected') }
    if ($badRequest.PSObject.Properties.Name -contains 'generation') {
        $failures.Add('bad-request-leaked-snapshot')
    }
    if ($first.protocol_schema -ne 'alas-headless.observer/v1' -or
        $first.snapshot_schema -ne 1) { $failures.Add('observer-schema-mismatch') }
    if ($first.package -ne $GamePackage -or $first.pid -ne [int]$targetPid) {
        $failures.Add('observer-process-identity-mismatch')
    }
    if ($first.driver_revision -ne $expectedDriverRevision -or $first.abi -ne 'x86_64') {
        $failures.Add('observer-version-fingerprint-mismatch')
    }
    # The Unity render thread is normally already attached to IL2CPP. In that case the
    # observer must reuse the existing attachment instead of attaching it a second time,
    # so observer_attached=false is expected. flags=15 and main_thread=true already prove
    # that the typed snapshot ran on the selected, IL2CPP-attached Unity thread.
    if (-not $first.main_thread -or $first.flags -ne 15 -or
        $first.ui_stage -ne 100 -or $first.ui_method_mask -ne 15) {
        $failures.Add('typed-ui-probe-incomplete')
    }
    if ($first.assembly_count -lt 100) { $failures.Add('game-assembly-set-incomplete') }
    if ($ObservationSeconds -gt 0) {
        $expectedSamples = [Math]::Max(1, [Math]::Floor(
            ($ObservationSeconds * 1000) / $ObservationIntervalMs))
        $minimumHealthySamples = [Math]::Max(1, [Math]::Floor($expectedSamples * 0.8))
        if ($freshObservations.Count -lt $minimumHealthySamples) {
            $failures.Add('sustained-observer-health-insufficient')
        }
        if (-not $lastObservation -or
            [uint64]$lastObservation.generation -le [uint64]$second.generation -or
            $observationSummary.distinct_generation_count -lt 2) {
            $failures.Add('sustained-observer-generation-stalled')
        }
    }
    if ($semanticButtons.protocol_schema -ne 'alas-headless.observer/v1' -or
        $semanticButtons.semantic_schema -ne 'alas-headless.buttons/v1' -or
        $semanticButtons.schema -ne 1 -or $semanticButtons.package -ne $GamePackage -or
        $semanticButtons.pid -ne [int]$targetPid -or
        $semanticButtons.driver_revision -ne $expectedDriverRevision) {
        $failures.Add('semantic-button-contract-mismatch')
    }
    if ($RequireSemanticButtons -and
        ($semanticButtons.status -ne 'ok' -or $semanticButtons.age_ms -gt $MaxFreshnessMs -or
         $semanticButtons.truncated -or $semanticButtons.error_count -ne 0 -or
         $actionableSemanticButtons.Count -lt 1)) {
        $failures.Add('semantic-button-record-incomplete')
    }
    if ($semanticClick -and
        ([uint64]$semanticClick.post_click_buttons.generation -le
         [uint64]$semanticButtons.generation -or
         $semanticClick.post_click_snapshot.status -ne 'ok' -or
         $semanticClick.post_click_snapshot.age_ms -gt $MaxFreshnessMs -or
         $semanticClick.post_click_snapshot.flags -ne 15 -or
         -not $semanticClick.post_click_snapshot.main_thread)) {
        $failures.Add('semantic-click-postcondition-incomplete')
    }
    if ($logText -match 'Fatal signal|FATAL EXCEPTION|AndroidRuntime.*FATAL') {
        $failures.Add('fatal-marker-present')
    }

    $manifest = [ordered]@{
        schema = 'alas-headless.g4-game-init/v1'
        captured_at_utc = $capturedAt.ToString('o')
        serial = $Serial
        package = $GamePackage
        activity = $Activity
        pid = [int]$targetPid
        socket_name = $socketName
        unity_command_line = $UnityCommandLine
        angle_apk_sha256 = (Get-FileHash -LiteralPath $angleApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
        driver_revision = $expectedDriverRevision
        package_version_name = $versionName
        package_version_code = $versionCode
        primary_abi = $primaryAbi
        base_apk_sha256 = $baseApkSha256
        il2cpp_sha256 = $il2CppSha256
        initial_pid = $initialPid
        foreground = $foreground
        foreground_component = $foregroundComponent
        original_settings = $originalSettings
        snapshots = [ordered]@{ first = $first; second = $second }
        observation = $observationSummary
        semantic_buttons = $semanticButtons
        actionable_semantic_button_count = $actionableSemanticButtons.Count
        semantic_click = $semanticClick
        page_loop = $pageLoop
        bad_request_response = $badRequest
        failures = $failures
        passed = $failures.Count -eq 0
    }
    Write-JsonFile -Path (Join-Path $outputDirectory 'manifest.json') -Value $manifest
    if ($failures.Count -gt 0) { throw "G4 game initialization failed: $($failures -join ', ')" }
    $runPassed = $true
    Write-Output $outputDirectory
}
catch {
    $caught = $_
    $failureForeground = $null
    $failureForegroundComponent = $null
    $failureLog = ''
    try {
        $failureForegroundComponent = Get-ForegroundComponent
        if ($failureForegroundComponent -match '^([^/]+)/') { $failureForeground = $Matches[1] }
        $activityDump = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'dumpsys', 'activity',
            'activities') -AllowFailure
        Write-Utf8File -Path (Join-Path $outputDirectory 'activity.failed.txt') `
            -Value $activityDump
    }
    catch { }
    try {
        $logArguments = if ($targetPid -match '^\d+$') {
            @('-s', $Serial, 'logcat', '--pid', $targetPid, '-d')
        }
        else { @('-s', $Serial, 'logcat', '-d') }
        $failureLog = Invoke-Adb -Arguments $logArguments -AllowFailure
        Write-Utf8File -Path (Join-Path $outputDirectory 'logcat.failed.txt') -Value $failureLog
    }
    catch { }
    $failureManifest = [ordered]@{
        schema = 'alas-headless.g4-game-init-failure/v1'
        captured_at_utc = $capturedAt.ToString('o')
        serial = $Serial
        package = $GamePackage
        activity = $Activity
        pid = if ($targetPid -match '^\d+$') { [int]$targetPid } else { $null }
        unity_command_line = $UnityCommandLine
        foreground = $failureForeground
        foreground_component = $failureForegroundComponent
        last_observer_response = $script:lastObserverResponse
        failure = $caught.Exception.Message
        passed = $false
    }
    try {
        Write-JsonFile -Path (Join-Path $outputDirectory 'manifest.failed.json') `
            -Value $failureManifest
    }
    catch { }
    throw $caught
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
    if (-not $runPassed -or -not $KeepGameRunningAfterPass) {
        Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'am', 'force-stop', $GamePackage) `
            -AllowFailure | Out-Null
    }
}
