$ErrorActionPreference = "SilentlyContinue"

$taskName = "AAA-Bot-Watchdog"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "AAA-Bot-Watchdog.lnk"
$removed = $false

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Scheduled task removed: $taskName"
    $removed = $true
}

if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Host "Startup shortcut removed: $shortcutPath"
    $removed = $true
}

if (-not $removed) {
    Write-Host "Autostart is not installed."
}

exit 0
