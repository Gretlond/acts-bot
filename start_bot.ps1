$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$pidFile = Join-Path $Root ".bot.pid"
$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "bot.out.log"
$errLog = Join-Path $logDir "bot.err.log"

function Get-BotProcess {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'bot\.py' } |
        Select-Object -First 1
}

$existing = Get-BotProcess
if ($existing) {
    Set-Content -Path $pidFile -Value $existing.ProcessId -Encoding ASCII
    Write-Host "Bot is already running. PID: $($existing.ProcessId)"
    exit 0
}
if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force
}

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "Python not found: .venv\Scripts\python.exe is missing."
        exit 1
    }
    $python = $cmd.Source
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$process = Start-Process `
    -FilePath $python `
    -ArgumentList "bot.py" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

Set-Content -Path $pidFile -Value $process.Id -Encoding ASCII
Start-Sleep -Seconds 3

$alive = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
if (-not $alive) {
    Write-Host "Bot failed to start. Last error log:"
    if (Test-Path $errLog) {
        Get-Content $errLog -Tail 20 -Encoding UTF8
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "Bot started. PID: $($process.Id)"
Write-Host "Logs: $outLog ; $errLog"
exit 0
