[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Serial,

    [Parameter(Mandatory = $true)]
    [string]$Package,

    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')) 'evidence'),

    [switch]$UseRoot
)

$ErrorActionPreference = 'Stop'
$scriptVersion = '1.0.0'
$adbCommand = Get-Command adb -ErrorAction Stop
$capturedAt = [DateTimeOffset]::UtcNow
$captureName = '{0}-{1}' -f $capturedAt.ToString('yyyyMMddTHHmmssZ'), ($Serial -replace '[^A-Za-z0-9._-]', '_')
$outputDirectory = Join-Path $OutputRoot $captureName
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

$commandResults = [System.Collections.Generic.List[object]]::new()

function Write-Utf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [AllowEmptyString()][string]$Content
    )

    [IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
}

function Invoke-AdbCapture {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Required
    )

    $outputPath = Join-Path $outputDirectory ($Name + '.txt')
    $started = [DateTimeOffset]::UtcNow
    $output = @(& $adbCommand.Source @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $text = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    if ($text.Length -gt 0) {
        $text += [Environment]::NewLine
    }
    Write-Utf8File -Path $outputPath -Content $text

    $commandResults.Add([ordered]@{
        name = $Name
        arguments = $Arguments
        exit_code = $exitCode
        required = [bool]$Required
        duration_ms = [int]([DateTimeOffset]::UtcNow - $started).TotalMilliseconds
        file = [IO.Path]::GetFileName($outputPath)
    })

    if ($Required -and $exitCode -ne 0) {
        throw "Required ADB capture '$Name' failed with exit code $exitCode. See $outputPath"
    }

    return $text
}

function Invoke-DeviceShellCapture {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command,
        [switch]$Required,
        [switch]$Root
    )

    if ($Root) {
        return Invoke-AdbCapture -Name $Name -Arguments @('-s', $Serial, 'shell', "su -c '$Command'") -Required:$Required
    }
    return Invoke-AdbCapture -Name $Name -Arguments @('-s', $Serial, 'shell', $Command) -Required:$Required
}

try {
    Invoke-AdbCapture -Name 'host-adb' -Arguments @('version') -Required | Out-Null
    Invoke-AdbCapture -Name 'devices' -Arguments @('devices', '-l') -Required | Out-Null

    $propertiesCommand = @(
        'getprop ro.build.fingerprint'
        'getprop ro.build.version.sdk'
        'getprop ro.product.cpu.abilist'
        'getprop ro.hardware.egl'
        'getprop ro.hardware.vulkan'
        'getprop ro.opengles.version'
        'getprop debug.angle.null_refresh_hz'
        'wm size'
        'wm density'
    ) -join '; '
    Invoke-DeviceShellCapture -Name 'properties' -Command $propertiesCommand -Required | Out-Null

    Invoke-DeviceShellCapture -Name 'display' -Command 'dumpsys display' -Required | Out-Null
    Invoke-DeviceShellCapture -Name 'package' -Command "dumpsys package $Package" -Required | Out-Null
    Invoke-DeviceShellCapture -Name 'top-activity' -Command 'dumpsys activity activities' -Required | Out-Null

    $pidText = Invoke-DeviceShellCapture -Name 'pid' -Command "pidof $Package" -Required
    $targetPid = ($pidText -split '\s+' | Where-Object { $_ -match '^\d+$' } | Select-Object -First 1)
    if (-not $targetPid) {
        throw "Package $Package has no running process; G0 requires a live process."
    }

    Invoke-DeviceShellCapture -Name 'process' -Command "ps -A -o USER,PID,PPID,NAME,ARGS | grep -F $Package" -Required | Out-Null
    $graphicsPattern = 'Unity|GfxDevice|OpenGL|GLES|EGL|Vulkan|ANGLE|Renderer|graphics'
    $logText = Invoke-AdbCapture -Name 'process-log-raw' -Arguments @('-s', $Serial, 'logcat', '--pid', $targetPid, '-d')
    $graphicsLines = $logText -split "`r?`n" | Where-Object { $_ -match $graphicsPattern }
    Write-Utf8File -Path (Join-Path $outputDirectory 'graphics-log.txt') -Content (($graphicsLines -join [Environment]::NewLine) + [Environment]::NewLine)

    $mapsCommand = "cat /proc/$targetPid/maps"
    if ($UseRoot) {
        $mapsText = Invoke-DeviceShellCapture -Name 'process-maps-raw' -Command $mapsCommand -Root
    }
    else {
        $mapsText = Invoke-DeviceShellCapture -Name 'process-maps-raw' -Command $mapsCommand
    }
    $mappedLines = $mapsText -split "`r?`n" | Where-Object {
        $_ -match 'libunity|libil2cpp|libEGL|libGLES|libvulkan|libangle|houdini|ndk_translation'
    }
    Write-Utf8File -Path (Join-Path $outputDirectory 'mapped-libraries.txt') -Content (($mappedLines -join [Environment]::NewLine) + [Environment]::NewLine)

    $binaryPaths = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $apkPathsText = Invoke-DeviceShellCapture -Name 'apk-paths' -Command "pm path $Package"
    foreach ($line in ($apkPathsText -split "`r?`n")) {
        if ($line -match '^package:(/.+)$') {
            [void]$binaryPaths.Add($Matches[1])
        }
    }
    foreach ($line in $mappedLines) {
        if ($line -match '\s(/\S*(?:libunity|libil2cpp)\.so)\s*$') {
            [void]$binaryPaths.Add($Matches[1])
        }
    }

    $hashCommands = foreach ($path in $binaryPaths) {
        if ($path -notmatch '^/[A-Za-z0-9._/+=:@~-]+$') {
            throw "Refusing to interpolate an unexpected device path into sha256sum: $path"
        }
        "sha256sum -- $path"
    }
    if ($hashCommands.Count -gt 0) {
        Invoke-DeviceShellCapture -Name 'binary-hashes' -Command ($hashCommands -join '; ') -Root:$UseRoot | Out-Null
    }
    else {
        Write-Utf8File -Path (Join-Path $outputDirectory 'binary-hashes.txt') -Content "no readable binary paths discovered`n"
    }

    $fileEntries = Get-ChildItem -LiteralPath $outputDirectory -File |
        Where-Object { $_.Name -ne 'manifest.json' } |
        Sort-Object Name |
        ForEach-Object {
            [ordered]@{
                name = $_.Name
                bytes = $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }

    $manifest = [ordered]@{
        schema = 'alas-headless.g0-evidence/v1'
        script_version = $scriptVersion
        captured_at_utc = $capturedAt.ToString('o')
        serial = $Serial
        package = $Package
        pid = [int]$targetPid
        root_requested = [bool]$UseRoot
        commands = $commandResults
        files = $fileEntries
    }
    Write-Utf8File -Path (Join-Path $outputDirectory 'manifest.json') -Content (($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine)

    Write-Output $outputDirectory
}
catch {
    $failure = [ordered]@{
        schema = 'alas-headless.g0-evidence/v1'
        script_version = $scriptVersion
        captured_at_utc = $capturedAt.ToString('o')
        serial = $Serial
        package = $Package
        root_requested = [bool]$UseRoot
        error = $_.Exception.Message
        commands = $commandResults
    }
    Write-Utf8File -Path (Join-Path $outputDirectory 'manifest.failed.json') -Content (($failure | ConvertTo-Json -Depth 8) + [Environment]::NewLine)
    throw
}
