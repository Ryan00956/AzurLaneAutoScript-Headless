[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SystemEvidence,
    [Parameter(Mandatory = $true)][string]$NullEvidence,
    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')) 'evidence')
)

$ErrorActionPreference = 'Stop'

function Get-Median {
    param([Parameter(Mandatory = $true)][double[]]$Values)
    $sorted = @($Values | Sort-Object)
    if ($sorted.Count -eq 0) { throw 'Cannot calculate the median of an empty set' }
    if ($sorted.Count % 2 -eq 1) { return $sorted[[int]($sorted.Count / 2)] }
    return ($sorted[$sorted.Count / 2 - 1] + $sorted[$sorted.Count / 2]) / 2
}

function Read-Leg {
    param([Parameter(Mandatory = $true)][string]$EvidencePath)
    $directory = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($EvidencePath)
    $manifestPath = Join-Path $directory 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        throw "G2 manifest does not exist: $manifestPath"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $hostSamples = @($manifest.host_samples | Where-Object process_alive)
    $guestSamples = @($manifest.memory_samples)
    if ($hostSamples.Count -lt 2 -or $guestSamples.Count -lt 2) {
        throw "Insufficient resource samples in $manifestPath"
    }

    $hostInterval = ([DateTimeOffset]::Parse($hostSamples[-1].captured_at_utc) -
        [DateTimeOffset]::Parse($hostSamples[0].captured_at_utc)).TotalSeconds
    $hostCpuDelta = [double]$hostSamples[-1].cpu_seconds -
        [double]$hostSamples[0].cpu_seconds
    $updates = [double]$manifest.last_heartbeat.updates
    if ($hostInterval -le 0 -or $hostCpuDelta -lt 0 -or $updates -le 0) {
        throw "Invalid timing or counter values in $manifestPath"
    }

    $guestCpu = @($guestSamples | Where-Object { $null -ne $_.cpu_percent } |
        ForEach-Object { [double]$_.cpu_percent })
    $guestPss = @($guestSamples | ForEach-Object { [double]$_.pss_kb })
    $guestRss = @($guestSamples | ForEach-Object { [double]$_.rss_kb })
    $hostWorkingSet = @($hostSamples |
        ForEach-Object { [double]$_.working_set_bytes / 1MB })
    $hostPrivate = @($hostSamples |
        ForEach-Object { [double]$_.private_memory_bytes / 1MB })

    return [ordered]@{
        evidence_directory = $directory
        manifest_sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        driver_mode = $manifest.driver_mode
        passed = [bool]$manifest.passed
        renderer = $manifest.startup.graphics_device
        graphics_type = $manifest.startup.graphics_type
        surface = '{0}x{1}' -f $manifest.startup.screen_width, $manifest.startup.screen_height
        duration_seconds = [double]$manifest.duration_seconds
        serial = $manifest.serial
        unity_apk_sha256 = $manifest.unity_apk_sha256
        angle_apk_sha256 = $manifest.angle_apk_sha256
        host_process_id = $manifest.host_process_id
        host_sample_count = $hostSamples.Count
        host_interval_seconds = [Math]::Round($hostInterval, 3)
        host_cpu_delta_seconds = [Math]::Round($hostCpuDelta, 3)
        host_core_equivalents = [Math]::Round($hostCpuDelta / $hostInterval, 4)
        host_cpu_seconds_per_1000_updates = [Math]::Round(1000 * $hostCpuDelta / $updates, 4)
        host_working_set_first_mib = [Math]::Round($hostWorkingSet[0], 1)
        host_working_set_median_mib = [Math]::Round((Get-Median $hostWorkingSet), 1)
        host_working_set_last_mib = [Math]::Round($hostWorkingSet[-1], 1)
        host_private_first_mib = [Math]::Round($hostPrivate[0], 1)
        host_private_median_mib = [Math]::Round((Get-Median $hostPrivate), 1)
        host_private_last_mib = [Math]::Round($hostPrivate[-1], 1)
        guest_cpu_mean_percent = [Math]::Round(($guestCpu | Measure-Object -Average).Average, 3)
        guest_cpu_max_percent = [Math]::Round(($guestCpu | Measure-Object -Maximum).Maximum, 3)
        guest_pss_first_kib = [int64]$guestPss[0]
        guest_pss_median_kib = [Math]::Round((Get-Median $guestPss))
        guest_pss_last_kib = [int64]$guestPss[-1]
        guest_rss_first_kib = [int64]$guestRss[0]
        guest_rss_median_kib = [Math]::Round((Get-Median $guestRss))
        guest_rss_last_kib = [int64]$guestRss[-1]
        updates = [int64]$manifest.last_heartbeat.updates
        fixed_updates = [int64]$manifest.last_heartbeat.fixed_updates
        end_of_frame = [int64]$manifest.last_heartbeat.end_of_frame
        event_count = [int64]$manifest.event_counts.total
        heartbeat_count = [int64]$manifest.event_counts.heartbeat
        async_outcome_count = [int64]$manifest.event_counts.async_outcome
        semantic = $manifest.last_heartbeat.button_semantic
        failures = @($manifest.failures)
    }
}

$system = Read-Leg -EvidencePath $SystemEvidence
$nullLeg = Read-Leg -EvidencePath $NullEvidence
$failures = [System.Collections.Generic.List[string]]::new()
if (-not $system.passed) { $failures.Add('system-leg-failed') }
if (-not $nullLeg.passed) { $failures.Add('null-leg-failed') }
if ($system.driver_mode -ne 'system' -or $system.renderer -notmatch 'SwiftShader') {
    $failures.Add('system-leg-is-not-swiftshader')
}
if ($nullLeg.driver_mode -ne 'null' -or $nullLeg.renderer -notmatch 'NULL') {
    $failures.Add('null-leg-is-not-null')
}
if ($system.serial -ne $nullLeg.serial) { $failures.Add('serial-mismatch') }
if ($system.unity_apk_sha256 -ne $nullLeg.unity_apk_sha256) { $failures.Add('unity-apk-mismatch') }
if ($system.surface -ne $nullLeg.surface) { $failures.Add('surface-mismatch') }
if ($system.host_process_id -eq $nullLeg.host_process_id) { $failures.Add('host-process-not-cold-restarted') }
if ([Math]::Abs($system.duration_seconds - $nullLeg.duration_seconds) /
    [Math]::Max($system.duration_seconds, $nullLeg.duration_seconds) -gt 0.05) {
    $failures.Add('duration-mismatch-over-five-percent')
}
if ($nullLeg.host_core_equivalents -ge $system.host_core_equivalents) {
    $failures.Add('no-host-cpu-advantage')
}
if ($nullLeg.host_working_set_median_mib -ge $system.host_working_set_median_mib) {
    $failures.Add('no-host-working-set-advantage')
}
if ($nullLeg.guest_rss_median_kib -ge $system.guest_rss_median_kib) {
    $failures.Add('no-guest-rss-advantage')
}

$comparison = [ordered]@{
    host_core_reduction_percent = [Math]::Round(100 *
        (1 - $nullLeg.host_core_equivalents / $system.host_core_equivalents), 2)
    host_cpu_per_update_reduction_percent = [Math]::Round(100 *
        (1 - $nullLeg.host_cpu_seconds_per_1000_updates /
            $system.host_cpu_seconds_per_1000_updates), 2)
    host_working_set_median_reduction_percent = [Math]::Round(100 *
        (1 - $nullLeg.host_working_set_median_mib / $system.host_working_set_median_mib), 2)
    host_private_median_reduction_percent = [Math]::Round(100 *
        (1 - $nullLeg.host_private_median_mib / $system.host_private_median_mib), 2)
    guest_cpu_mean_reduction_percent = [Math]::Round(100 *
        (1 - $nullLeg.guest_cpu_mean_percent / $system.guest_cpu_mean_percent), 2)
    guest_pss_median_reduction_percent = [Math]::Round(100 *
        (1 - $nullLeg.guest_pss_median_kib / $system.guest_pss_median_kib), 2)
    guest_rss_median_reduction_percent = [Math]::Round(100 *
        (1 - $nullLeg.guest_rss_median_kib / $system.guest_rss_median_kib), 2)
}

$capturedAt = [DateTimeOffset]::UtcNow
$outputDirectory = Join-Path $OutputRoot ('g2-comparison-{0}' -f
    $capturedAt.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$result = [ordered]@{
    schema = 'alas-headless.g2-comparison/v1'
    captured_at_utc = $capturedAt.ToString('o')
    comparison_design = 'same Windows host, same AVD and image, separate cold QEMU processes'
    system = $system
    null = $nullLeg
    comparison = $comparison
    failures = $failures
    passed = $failures.Count -eq 0
}
$json = ($result | ConvertTo-Json -Depth 10) + [Environment]::NewLine
[IO.File]::WriteAllText((Join-Path $outputDirectory 'manifest.json'), $json,
    [Text.UTF8Encoding]::new($false))
Write-Output $outputDirectory
if ($failures.Count -gt 0) { throw "G2 comparison failed: $($failures -join ', ')" }
