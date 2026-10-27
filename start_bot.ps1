$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$watchdogPidFile = Join-Path $Root ".watchdog.pid"
$watchdogScript = Join-Path $Root "watchdog_bot.ps1"
$watchdogLog = Join-Path $logDir "watchdog.log"
$disabledFlag = Join-Path $Root ".bot.disabled"

Remove-Item $disabledFlag -Force -ErrorAction SilentlyContinue

function Get-WatchdogPid {
    if (Test-Path $watchdogPidFile) {
        $saved = (Get-Content $watchdogPidFile -Raw).Trim()
        if ($saved -match '^\d+$') {
            $proc = Get-Process -Id ([int]$saved) -ErrorAction SilentlyContinue
            if ($proc) {
                return [int]$saved
            }
        }
    }

    $cim = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match '-File\s+.*watchdog_bot\.ps1' } |
        Select-Object -First 1
    if ($cim) {
        return [int]$cim.ProcessId
    }
    return $null
}

function Get-BotPid {
    $bot = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'bot\.py' } |
        Select-Object -First 1
    if ($bot) {
        return [int]$bot.ProcessId
    }
    return $null
}

$watchdogPid = Get-WatchdogPid
if ($watchdogPid) {
    Write-Host "Watchdog is already running. PID: $watchdogPid"
} else {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $watchdogScript + '"'
    $started = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $arguments `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -PassThru
    Write-Host "Watchdog started. PID: $($started.Id)"
}

for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    $botPid = Get-BotPid
    if ($botPid) {
        Write-Host "Bot is running. PID: $botPid"
        Write-Host "Logs: $logDir"
        exit 0
    }
}

Write-Host "Bot did not start. Watchdog log:"
if (Test-Path $watchdogLog) {
    Get-Content $watchdogLog -Tail 20 -Encoding UTF8
}
exit 1
