$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$watchdog = Join-Path $Root "watchdog_bot.ps1"
$taskName = "AAA-Bot-Watchdog"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "AAA-Bot-Watchdog.lnk"

if (-not (Test-Path $watchdog)) {
    Write-Host "Watchdog script not found: $watchdog"
    exit 1
}

try {
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdog`""

    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Starts the AAA Telegram bot watchdog when the user logs on." `
        -Force | Out-Null

    Remove-Item $shortcutPath -Force -ErrorAction SilentlyContinue
    Write-Host "Autostart installed: scheduled task '$taskName'."
    Write-Host "Trigger: at logon of $env:USERNAME."
    exit 0
} catch {
    Write-Host "Could not create the scheduled task: $($_.Exception.Message)"
    Write-Host "Falling back to the Startup folder shortcut."

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdog`""
    $shortcut.WorkingDirectory = $Root
    $shortcut.WindowStyle = 7
    $shortcut.Description = "AAA Telegram bot watchdog"
    $shortcut.Save()

    Write-Host "Autostart installed: $shortcutPath"
    exit 0
}
