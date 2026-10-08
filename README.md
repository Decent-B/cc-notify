# cc-notify

A lightweight Windows tray app (WinUI 3 / .NET 8) that pops up a notification
whenever Claude Code needs your attention — permission requests, idle prompts,
task completion and errors.

Works whether Claude Code runs natively on Windows or inside **WSL2**, and on
**multi-monitor** setups: popups appear on the display you are working on.

---

## How It Works

```
Claude Code (WSL2 or Windows)
    │
    │  HTTP POST /webhook  (async, fire-and-forget)
    ▼
cc-notify.exe  (tray app, 127.0.0.1:9876)
    │
    │  router → sound → display selector
    ▼
Popup in the bottom-right of the chosen monitor
(click it to jump to the matching VS Code window)
```

Windows' own toasts always appear on the primary display and cannot be
redirected, so cc-notify draws its own popups. That is what lets it choose the
monitor.

### Notification triggers

| Event | What it means | Notification |
|---|---|---|
| `Notification[permission_prompt]` | Claude is showing you a permission prompt | "Permission Required" |
| `Notification[idle_prompt]` | Claude is waiting for your next message | "Waiting for Input" |
| `Stop` | Claude finished generating a response | "Task Complete" |
| `StopFailure` | The turn ended on an API error (rate limit, auth, server…) | e.g. "Rate Limited" |

`PermissionRequest` is not used: Claude Code fires it *together with*
`Notification[permission_prompt]` (two popups for one prompt) and also when auto
mode decides by itself without asking you.

---

## Installation

Download the latest `cc-notify-<version>-windows-x64.exe` from
[**Releases**](https://github.com/Decent-B/cc-notify/releases) and double-click
it (SmartScreen: **More info → Run anyway**; the app is not code-signed).
A purple bell appears in the tray. Nothing else to install — the .NET and
Windows App SDK runtimes are bundled.

On first launch cc-notify:

- **starts with Windows** — turned on once by default; switch it off in
  *Settings* (tray icon → *Settings…*) or in Windows Settings › Apps › Startup.
  If you switch it off in Windows, cc-notify never turns it back on;
- **configures Claude Code hooks** automatically for Windows and the default
  WSL2 distro (redo it any time from the tray menu). Restart Claude Code once.

For manual setup see [Manual Hook Configuration](#manual-hook-configuration).

### Choosing the monitor

*Settings → Notification display*:

| Mode | Popup appears on |
|---|---|
| Follow VS Code (default) | the display holding the VS Code window of that project; falls back to the cursor's display |
| Follow the mouse cursor | the display the cursor is on |
| Always the primary display | the primary display |
| *Display N …* | one fixed display (falls back if it is unplugged) |

Use **Send test notification** to see where it lands.

---

## Manual Hook Configuration

If you prefer to configure the hooks yourself (`<TOKEN>` is `webhook_token` in `%APPDATA%\cc-notify\state.json`), add the following to
`~/.claude/settings.json`:

```jsonc
{
  "hooks": {
    "Notification": [
      {
        "hooks": [{ "type": "http", "url": "http://localhost:9876/webhook?token=<TOKEN>", "async": true }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "http", "url": "http://localhost:9876/webhook?token=<TOKEN>", "async": true }]
      }
    ],
    "StopFailure": [
      {
        "hooks": [{ "type": "http", "url": "http://localhost:9876/webhook?token=<TOKEN>", "async": true }]
      }
    ]
  }
}
```

**WSL2 users:** `localhost` works with WSL's default localhost forwarding. If you
turned that off, use your Windows host IP:
```bash
awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf
```

A full example file is in [examples/settings-snippet.json](examples/settings-snippet.json).

---

## Configuration

Everything is in the Settings window (tray icon → *Settings…*). It is stored in
`%APPDATA%\cc-notify\config.json`:

```jsonc
{
  "port": 9876,                    // webhook port (edit by hand, then restart)
  "sound_enabled": true,
  "notify_on_stop": true,
  "notify_on_stop_failure": true,
  "notify_on_permission": true,
  "notify_on_idle": true,
  "monitor": "follow_vs_code",     // follow_vs_code | follow_cursor | primary | specific
  "monitor_device_name": null,     // e.g. "\\\\.\\DISPLAY2" when monitor is "specific"
  "autostart_initialized": true    // managed by the app
}
```

Logs: `%APPDATA%\cc-notify\cc-notify.log`.

---

## Verify it Works

Use *Settings → Send test notification*, or post a webhook yourself (the token
is `webhook_token` in `%APPDATA%\cc-notify\state.json`):

```powershell
Invoke-RestMethod -Method Post "http://localhost:9876/webhook?token=<TOKEN>" `
  -ContentType "application/json" `
  -Body '{"hook_event_name":"Stop","cwd":"C:\\"}'
```

---

## Building from Source

Requires the Windows [.NET 8 SDK](https://dotnet.microsoft.com/download)
(`winget install Microsoft.DotNet.SDK.8`).

**Native Windows**

```powershell
dotnet test tests/CcNotify.Core.Tests
dotnet run --project src/CcNotify.App -p:Platform=x64
dotnet publish src/CcNotify.App -c Release -p:Platform=x64 -o dist   # single-file dist/cc-notify.exe
```

**From WSL2** (MSBuild dislikes `\\wsl$` paths, so the script mirrors the repo to the Windows drive):

```bash
bash scripts/build-windows.sh            # test + publish → dist/cc-notify.exe
bash scripts/build-windows.sh --launch   # ...and start it
bash scripts/pre-push-check.sh           # build, launch, fire a webhook per event type
```

To try a build without touching your real setup, set `CC_NOTIFY_DATA_DIR` to a
scratch folder before launching: config, state and logs go there and hooks are
written to a fake home instead of the real Claude Code settings.

### Publish a release

```bash
git tag v0.2.0 && git push origin v0.2.0
```

GitHub Actions tests, publishes and creates the release
([release.yml](.github/workflows/release.yml)).

---

## Repository Structure

```
cc-notify/
├── src/
│   ├── CcNotify.Core/        # UI-free logic, unit-tested
│   │   ├── Notifications/    # hook event → router → NotificationService, messages
│   │   ├── Server/           # loopback webhook server (token-authenticated)
│   │   ├── Displays/         # monitor enumeration + selection policy
│   │   ├── VsCode/           # find/focus VS Code, vscode:// URIs, WSL helper
│   │   ├── Hooks/            # install hooks into Windows / WSL2 Claude Code settings
│   │   ├── Autostart/        # start with Windows (HKCU Run + StartupApproved)
│   │   ├── Updates/          # GitHub release self-update
│   │   └── Settings/         # config.json / state.json
│   └── CcNotify.App/         # WinUI 3 shell: tray, popups, settings window, composition root
├── tests/CcNotify.Core.Tests/
├── scripts/                  # build, pre-push check, manual hook setup
├── docs/                     # architecture, hooks reference, distribution
└── .github/workflows/release.yml
```

See [docs/architecture.md](docs/architecture.md) for the design.

---

## Troubleshooting

**No notifications appear**

- Confirm cc-notify is running (purple bell in system tray).
- Check `%APPDATA%\cc-notify\cc-notify.log`.
- Hooks carry a secret token; if you deleted `state.json`, run *Set up Claude Code
  hooks…* again so Claude Code gets the new token.
- Verify the hook URL is correct: `curl http://localhost:9876/health` should
  return `{"status":"ok"}`.

**WSL2: notifications fire but nothing appears**

- The cc-notify.exe must be running on the **Windows side**, not inside WSL2.
  Check your Windows system tray.
- Confirm the Windows host IP in the hook URL is correct:
  `awk '/^nameserver/{print $2}' /etc/resolv.conf`

**Port already in use**

- Another instance of cc-notify may be running. Look for a purple bell icon in
  the system tray and exit it before starting a new one.
- To use a different port: edit `%APPDATA%\cc-notify\config.json` and re-run
  the setup script with `-Port <new-port>`.

**SmartScreen blocks the EXE**

Click **"More info"** → **"Run anyway"**. See
[docs/distribution.md](docs/distribution.md#code-signing) for context on why
this happens and what it means.

---

## Documentation

| Document | Description |
|---|---|
| [docs/requirements.md](docs/requirements.md) | Functional and non-functional requirements |
| [docs/claude-code-hooks.md](docs/claude-code-hooks.md) | Claude Code hook event reference |
| [docs/architecture.md](docs/architecture.md) | Layers, design decisions, how to extend |
| [docs/windows-notifications.md](docs/windows-notifications.md) | Background: Windows toast capabilities and limits |
| [docs/distribution.md](docs/distribution.md) | Build, release, and code-signing guide |

---

## License

MIT — see [LICENSE](LICENSE).
