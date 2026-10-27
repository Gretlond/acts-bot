$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$watchdogPidFile = Join-Path $Root ".watchdog.pid"
$botPidFile = Join-Path $Root ".bot.pid"
$stoppedWatchdogs = @()
$stoppedBots = @()

# If autostart is installed, stop its task as well so it does not look "Running".
$taskName = "AAA-Bot-Watchdog"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task -and $task.State -eq "Running") {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# Stop the watchdog first, otherwise it may restart the bot.
if (Test-Path $watchdogPidFile) {
    $saved = (Get-Content $watchdogPidFile -Raw).Trim()
    if ($saved -match '^\d+$') {
        $alive = Get-Process -Id ([int]$saved) -ErrorAction SilentlyContinue
        if ($alive) {
            Stop-Process -Id ([int]$saved) -Force
            $stoppedWatchdogs += [int]$saved
        }
    }
}

$excludePids = @($PID)
$current = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
while ($current -and $current.ParentProcessId) {
    $parentId = [int]$current.ParentProcessId
    if ($excludePids -contains $parentId) { break }
    $excludePids += $parentId
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId"
}

$watchdogProcs = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match '-File\s+.*watchdog_bot\.ps1' -and
        ($excludePids -notcontains [int]$_.ProcessId)
    }

foreach ($proc in $watchdogProcs) {
    Stop-Process -Id $proc.ProcessId -Force
    $stoppedWatchdogs += $proc.ProcessId
}

Start-Sleep -Seconds 2

$botProcs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'bot\.py' }

foreach ($proc in $botProcs) {
    Stop-Process -Id $proc.ProcessId -Force
    $stoppedBots += $proc.ProcessId
}

if (Test-Path $botPidFile) {
    $savedBot = (Get-Content $botPidFile -Raw).Trim()
    if ($savedBot -match '^\d+$') {
        $alive = Get-Process -Id ([int]$savedBot) -ErrorAction SilentlyContinue
        if ($alive) {
            Stop-Process -Id ([int]$savedBot) -Force
            $stoppedBots += [int]$savedBot
        }
    }
}

Remove-Item $watchdogPidFile -Force
Remove-Item $botPidFile -Force

if ($stoppedWatchdogs.Count -gt 0 -or $stoppedBots.Count -gt 0) {
    $wd = ($stoppedWatchdogs | Select-Object -Unique) -join ', '
    $bt = ($stoppedBots | Select-Object -Unique) -join ', '
    Write-Host "Bot stopped. Watchdog PID: $wd ; bot PID: $bt"
    exit 0
}

Write-Host "Bot is not running."
exit 0
