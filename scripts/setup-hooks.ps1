<#
.SYNOPSIS
    Configure Claude Code hooks to send notifications to cc-notify.

.DESCRIPTION
    Merges the required webhook entries into %USERPROFILE%\.claude\settings.json
    so Claude Code fires HTTP hooks to the local cc-notify server.

    Run this ONCE after installing cc-notify. Restart Claude Code afterwards.

.PARAMETER Port
    The port cc-notify is listening on. Default: 9876.

.PARAMETER AddToStartup
    If set, creates a Windows startup shortcut so cc-notify launches at login.
    Requires the path to cc-notify.exe to be passed via -ExePath.

.PARAMETER ExePath
    Full path to cc-notify.exe (only used with -AddToStartup).

.EXAMPLE
    .\setup-hooks.ps1
    .\setup-hooks.ps1 -Port 9999
    .\setup-hooks.ps1 -AddToStartup -ExePath "C:\Tools\cc-notify.exe"
#>
param(
    [int]    $Port        = 9876,
    [switch] $AddToStartup,
    [string] $ExePath     = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Paths ─────────────────────────────────────────────────────────────────────

$SettingsDir  = Join-Path $env:USERPROFILE ".claude"
$SettingsPath = Join-Path $SettingsDir "settings.json"
$WebhookUrl   = "http://localhost:$Port/webhook"

# ── Load or initialise settings ───────────────────────────────────────────────

if (-not (Test-Path $SettingsDir)) {
    New-Item -ItemType Directory -Path $SettingsDir | Out-Null
}

$settings = if (Test-Path $SettingsPath) {
    try   { Get-Content $SettingsPath -Raw | ConvertFrom-Json }
    catch { Write-Warning "settings.json could not be parsed; starting fresh."; [PSCustomObject]@{} }
} else {
    [PSCustomObject]@{}
}

# ── Build hook entry ──────────────────────────────────────────────────────────

$hookEntry = [ordered]@{
    type  = "http"
    url   = $WebhookUrl
    async = $true
}

$hookGroup = [ordered]@{
    hooks = @($hookEntry)
}

# We register three event types:
#   Notification   — permission_prompt, idle_prompt, and other status events
#   Stop           — Claude finished generating a response
#   PermissionRequest — provides tool-level detail before the permission dialog
$newHooks = [ordered]@{
    Notification      = @($hookGroup)
    Stop              = @($hookGroup)
    PermissionRequest = @($hookGroup)
}

# ── Merge into existing settings ──────────────────────────────────────────────

if (-not ($settings.PSObject.Properties.Name -contains "hooks")) {
    $settings | Add-Member -NotePropertyName "hooks" -NotePropertyValue ([PSCustomObject]@{})
}

foreach ($event in $newHooks.Keys) {
    if ($settings.hooks.PSObject.Properties.Name -contains $event) {
        Write-Host "  (overwriting existing '$event' hooks)"
    }
    $settings.hooks | Add-Member -NotePropertyName $event -NotePropertyValue $newHooks[$event] -Force
}

# ── Persist ───────────────────────────────────────────────────────────────────

$settings | ConvertTo-Json -Depth 10 | Set-Content -Path $SettingsPath -Encoding UTF8

Write-Host ""
Write-Host "✅  Claude Code hooks configured at:"
Write-Host "    $SettingsPath"
Write-Host ""
Write-Host "    Webhook URL : $WebhookUrl"
Write-Host "    Events      : Notification, Stop, PermissionRequest"
Write-Host ""
Write-Host "    Restart Claude Code for changes to take effect."

# ── Optional: add to Windows startup ─────────────────────────────────────────

if ($AddToStartup) {
    if (-not $ExePath -or -not (Test-Path $ExePath)) {
        Write-Warning "-ExePath is required and must point to a valid cc-notify.exe."
    } else {
        $StartupDir  = [Environment]::GetFolderPath("Startup")
        $ShortcutPath = Join-Path $StartupDir "cc-notify.lnk"

        $WScript  = New-Object -ComObject WScript.Shell
        $Shortcut = $WScript.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath       = $ExePath
        $Shortcut.WorkingDirectory = Split-Path $ExePath
        $Shortcut.Description      = "Claude Code Notifier"
        $Shortcut.Save()

        Write-Host ""
        Write-Host "✅  Startup shortcut created:"
        Write-Host "    $ShortcutPath"
    }
}
