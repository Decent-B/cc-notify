<#
.SYNOPSIS
    Configure Claude Code hooks to send notifications to cc-notify.

.DESCRIPTION
    Merges the required webhook entries into %USERPROFILE%\.claude\settings.json
    so Claude Code fires HTTP hooks to the local cc-notify server.

    cc-notify.exe must be running before you call this script — it generates
    the per-install authentication token on first launch and stores it in
    %APPDATA%\cc-notify\state.json.  This script reads that token and embeds
    it in the webhook URL so the server can reject unsolicited requests.

    The preferred setup method is the in-app "Setup Claude Code Hooks…" tray
    menu item, which handles the token automatically.  Use this script only when
    manual setup is required (e.g. custom port, startup shortcut).

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
$StatePath    = Join-Path $env:APPDATA "cc-notify\state.json"

# ── Read the per-install webhook token ────────────────────────────────────────

$Token = ""
if (Test-Path $StatePath) {
    try {
        $state = Get-Content $StatePath -Raw | ConvertFrom-Json
        $Token = $state.webhook_token
    } catch {
        Write-Warning "Could not parse state.json: $_"
    }
}

if (-not $Token) {
    Write-Error (
        "Webhook token not found in $StatePath.`n" +
        "Start cc-notify.exe first (it generates the token on launch), " +
        "then re-run this script."
    )
    exit 1
}

$WebhookUrl = "http://localhost:$Port/webhook?token=$Token"

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
# Redact the token from terminal output — it is stored in settings.json already.
Write-Host "    Webhook URL : http://localhost:$Port/webhook?token=<redacted>"
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
