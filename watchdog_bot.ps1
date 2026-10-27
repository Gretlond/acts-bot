$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$watchdogPidFile = Join-Path $Root ".watchdog.pid"
$botPidFile = Join-Path $Root ".bot.pid"
$disabledFlag = Join-Path $Root ".bot.disabled"
$heartbeatFile = Join-Path $Root ".bot.heartbeat"
$heartbeatStaleMinutes = 10
$watchdogLog = Join-Path $logDir "watchdog.log"
$botOutLog = Join-Path $logDir "bot.out.log"
$botErrLog = Join-Path $logDir "bot.err.log"

function Write-WatchdogLog([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -Path $watchdogLog -Value $line -Encoding UTF8
}

function Get-BotProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'bot\.py' }
}

function Rotate-File([string]$Path, [int64]$MaxBytes = 5MB) {
    if ((Test-Path $Path) -and ((Get-Item $Path).Length -gt $MaxBytes)) {
        Move-Item -Path $Path -Destination "$Path.1" -Force
    }
}

function Test-HeartbeatStale {
    if (-not (Test-Path $heartbeatFile)) {
        return $false
    }
    try {
        $age = (Get-Date) - (Get-Item $heartbeatFile).LastWriteTime
        return ($age.TotalMinutes -gt $heartbeatStaleMinutes)
    } catch {
        return $false
    }
}

if (Test-Path $disabledFlag) {
    Write-WatchdogLog "bot disabled by .bot.disabled; watchdog exiting"
    exit 0
}

# One watchdog only. The mutex is released automatically if the process dies.
$mutex = New-Object System.Threading.Mutex($false, "Local\AAA-Bot-Watchdog-Mutex")
if (-not $mutex.WaitOne(0)) {
    exit 0
}

Set-Content -Path $watchdogPidFile -Value $PID -Encoding ASCII
Write-WatchdogLog "watchdog started (pid=$PID)"

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-WatchdogLog "python not found; watchdog stopped"
        Remove-Item $watchdogPidFile -Force -ErrorAction SilentlyContinue
        $mutex.ReleaseMutex()
        $mutex.Dispose()
        exit 1
    }
    $python = $cmd.Source
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$delay = 5

while ($true) {
    $bot = Get-BotProcesses | Select-Object -First 1
    if (-not $bot) {
        try { Rotate-File $botOutLog } catch { }
        try { Rotate-File $botErrLog } catch { }

        Write-WatchdogLog "bot is not running; starting"
        try {
            $proc = Start-Process `
                -FilePath $python `
                -ArgumentList "bot.py" `
                -WorkingDirectory $Root `
                -WindowStyle Hidden `
                -RedirectStandardOutput $botOutLog `
                -RedirectStandardError $botErrLog `
                -PassThru

            Set-Content -Path $botPidFile -Value $proc.Id -Encoding ASCII
            Start-Sleep -Seconds 4

            $alive = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
            if ($alive) {
                Write-WatchdogLog "bot started (pid=$($proc.Id))"
                $delay = 5
            } else {
                $delay = [Math]::Min(60, $delay * 2)
                Write-WatchdogLog "bot exited immediately; retry in $delay s"
            }
        } catch {
            $delay = [Math]::Min(60, $delay * 2)
            Write-WatchdogLog "start failed: $($_.Exception.Message); retry in $delay s"
        }
    } else {
        if (Test-HeartbeatStale) {
            Write-WatchdogLog "heartbeat is stale; restarting bot (pid=$($bot.ProcessId))"
            try {
                Stop-Process -Id $bot.ProcessId -Force -ErrorAction Stop
                Start-Sleep -Seconds 2
            } catch {
                Write-WatchdogLog "failed to stop stale bot: $($_.Exception.Message)"
            }
            $delay = 5
            Start-Sleep -Seconds $delay
            continue
        }
        if ($delay -ne 5) {
            Write-WatchdogLog "bot is healthy again (pid=$($bot.ProcessId))"
            $delay = 5
        }
    }

    Start-Sleep -Seconds $delay
}
