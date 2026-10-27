$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$pidFile = Join-Path $Root ".bot.pid"

$stopped = @()

$botProcs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'bot\.py' }

foreach ($proc in $botProcs) {
    Stop-Process -Id $proc.ProcessId -Force
    $stopped += $proc.ProcessId
}

if (Test-Path $pidFile) {
    $savedPid = (Get-Content $pidFile -Raw).Trim()
    if ($savedPid -match '^\d+$') {
        $alive = Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue
        if ($alive) {
            Stop-Process -Id ([int]$savedPid) -Force
            $stopped += [int]$savedPid
        }
    }
    Remove-Item $pidFile -Force
}

if ($stopped.Count -gt 0) {
    $unique = $stopped | Select-Object -Unique
    Write-Host "Bot stopped. PID: $($unique -join ', ')"
    exit 0
}

Write-Host "Bot is not running."
exit 0
