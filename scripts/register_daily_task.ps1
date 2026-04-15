[CmdletBinding()]
param(
    [string]$TaskName = "LinkedIn Content Agent Daily",
    [string]$Time = "08:00"
)

$ErrorActionPreference = "Stop"

try {
    $scheduledAt = [DateTime]::ParseExact($Time, "HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
}
catch {
    throw "Time must use 24-hour format HH:mm, for example 08:00 or 21:30."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerScript = (Resolve-Path (Join-Path $scriptDir "run_daily_agent.ps1")).Path
$userId = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runnerScript`""

$trigger = New-ScheduledTaskTrigger -Daily -At $scheduledAt
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Runs the LinkedIn content agent locally every day." `
    -Force | Out-Null

Write-Output "Registered scheduled task '$TaskName' for $Time local time."
Write-Output "Runner script: $runnerScript"
