$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$watchdogPidFile = Join-Path $Root ".watchdog.pid"
$botPidFile = Join-Path $Root ".bot.pid"
$watchdogLog = Join-Path $Root "logs\watchdog.log"
$botErrLog = Join-Path $Root "logs\bot.err.log"

function Get-WatchdogPid {
    if (Test-Path $watchdogPidFile) {
        $saved = (Get-Content $watchdogPidFile -Raw).Trim()
        if ($saved -match '^\d+$' -and (Get-Process -Id ([int]$saved) -ErrorAction SilentlyContinue)) {
            return [int]$saved
        }
    }
    $cim = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -match '-File\s+.*watchdog_bot\.ps1' } |
        Select-Object -First 1
    if ($cim) { return [int]$cim.ProcessId }
    return $null
}

$watchdogPid = Get-WatchdogPid
$botProcs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'bot\.py' }

if ($watchdogPid) {
    Write-Host "Watchdog is running. PID: $watchdogPid"
} else {
    Write-Host "Watchdog is not running."
}

if ($botProcs) {
    $ids = ($botProcs | Select-Object -ExpandProperty ProcessId) -join ', '
    Write-Host "Bot is running. PID: $ids"
    if (Test-Path $botErrLog) {
        Write-Host "--- last bot log lines ---"
        Get-Content $botErrLog -Tail 8 -Encoding UTF8
    }
} else {
    Write-Host "Bot is stopped."
    if (Test-Path $watchdogLog) {
        Write-Host "--- last watchdog log lines ---"
        Get-Content $watchdogLog -Tail 8 -Encoding UTF8
    }
}

exit 0
