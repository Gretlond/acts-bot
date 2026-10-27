$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$pidFile = Join-Path $Root ".bot.pid"
$errLog = Join-Path $Root "logs\bot.err.log"

$botProcs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'bot\.py' }

if ($botProcs) {
    $ids = ($botProcs | Select-Object -ExpandProperty ProcessId) -join ', '
    Write-Host "Bot is running. PID: $ids"
    if (Test-Path $errLog) {
        Write-Host "--- last log lines ---"
        Get-Content $errLog -Tail 8 -Encoding UTF8
    }
    exit 0
}

if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force
}
Write-Host "Bot is stopped."
exit 0
