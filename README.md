# cc-notify

A lightweight Windows tray application that sends **native Windows toast
notifications** whenever Claude Code needs your attention — permission requests,
idle prompts, and task completion signals.

Works whether Claude Code runs natively on Windows or inside **WSL2**.

---

## How It Works

```
Claude Code (WSL2 or Windows)
    │
    │  HTTP POST /webhook  (async, fire-and-forget)
    ▼
cc-notify.exe  (Windows tray app, port 9876)
    │
    │  WinRT toast API
    ▼
Windows Notification Center
```

Claude Code fires HTTP webhook hooks at key lifecycle events. cc-notify
receives them and shows a native toast that appears in the bottom-right corner
of your screen and persists in Notification Center.

### Notification triggers

| Event | What it means | Notification |
|---|---|---|
| `PermissionRequest` | Claude wants to run a tool and needs your OK | "Permission Required" — includes the tool name |
| `Notification[permission_prompt]` | Same, from the UI-layer signal | "Permission Required" |
| `Notification[idle_prompt]` | Claude is waiting for your next message | "Waiting for Input" |
| `Stop` | Claude finished generating a response | "Task Complete" |

---

## Installation

### Step 1 — Download cc-notify

Go to the [**Releases**](https://github.com/Decent-Cypher/ai-notification/releases)
page and download the latest `cc-notify-<version>-windows-x64.exe`.

> **SmartScreen warning?**
> Click **"More info"** → **"Run anyway"**.
> This is expected for open-source apps without an expensive EV code-signing
> certificate. The source is fully auditable here on GitHub.

Double-click the EXE — a purple bell icon appears in your system tray.
The webhook server is now listening on `http://localhost:9876`.

### Step 2 — Configure Claude Code hooks

**Option A — from the tray icon (recommended):**

Right-click the purple bell in the system tray and choose
**"Setup Claude Code Hooks…"**.

cc-notify auto-detects whether Claude Code is installed natively on Windows,
inside WSL2, or both, and configures each environment. A toast notification
reports the result when finished. Restart Claude Code to apply.

**Option B — command line:**

If you prefer to run the scripts manually:

*Windows (Claude Code native):*
```powershell
.\scripts\setup-hooks.ps1
```

*WSL2 (Claude Code running inside WSL2) — run from inside the distro:*
```bash
bash scripts/setup-hooks.sh
```

**Restart Claude Code** for the hook changes to take effect.

### Step 3 — (Optional) Start with Windows

To have cc-notify launch automatically at login:

```powershell
# Pass -ExePath with the full path where you saved cc-notify.exe
.\scripts\setup-hooks.ps1 -AddToStartup -ExePath "C:\Tools\cc-notify.exe"
```

Or manually: press `Win+R`, type `shell:startup`, and place a shortcut to
`cc-notify.exe` in the folder that opens.

---

## Manual Hook Configuration

If you prefer to configure the hooks yourself, add the following to
`~/.claude/settings.json`:

```jsonc
{
  "hooks": {
    "Notification": [
      {
        "hooks": [{ "type": "http", "url": "http://localhost:9876/webhook", "async": true }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "http", "url": "http://localhost:9876/webhook", "async": true }]
      }
    ],
    "PermissionRequest": [
      {
        "hooks": [{ "type": "http", "url": "http://localhost:9876/webhook", "async": true }]
      }
    ]
  }
}
```

**WSL2 users:** Replace `localhost` with your Windows host IP:
```bash
awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf
```

A full example file is in [examples/settings-snippet.json](examples/settings-snippet.json).

---

## Configuration

cc-notify reads `%APPDATA%\cc-notify\config.json` on startup (defaults are
used if the file does not exist):

```jsonc
{
  "port": 9876,               // webhook server port
  "sound_enabled": true,      // play a sound with each toast
  "notify_on_stop": true,     // "Task Complete" when Claude finishes
  "notify_on_permission": true, // "Permission Required" notifications
  "notify_on_idle": true      // "Waiting for Input" notifications
}
```

See [examples/config-example.json](examples/config-example.json) for a
commented template. Edit the file, then **restart cc-notify** for changes to
apply.

---

## Verify it Works

With cc-notify running, open a terminal and send a test webhook:

```powershell
# PowerShell
Invoke-RestMethod -Uri "http://localhost:9876/webhook" -Method Post `
  -ContentType "application/json" `
  -Body '{"hook_event_name":"Stop","session_id":"test","cwd":"C:\\"}'
```

```bash
# Bash (Windows or WSL2)
curl -s -X POST http://localhost:9876/webhook \
  -H "Content-Type: application/json" \
  -d '{"hook_event_name":"Stop","session_id":"test","cwd":"/tmp"}'
```

You should see a "Task Complete" toast in the bottom-right corner.

---

## Building from Source

Requires **Windows** with [uv](https://docs.astral.sh/uv/) installed.

```powershell
# Install uv (once, if not already installed)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

git clone https://github.com/Decent-Cypher/ai-notification.git
cd ai-notification

uv sync                    # create .venv and install all runtime dependencies
uv run python src/main.py  # run directly during development
```

### Build a standalone EXE

```powershell
uv sync --group dev                       # also installs PyInstaller
uv run python scripts/create_icon.py     # generates assets/icon.ico
uv run pyinstaller build.spec            # output: dist/cc-notify.exe
```

### Publish a release

```bash
git tag v1.2.0
git push origin v1.2.0
```

GitHub Actions builds the EXE and creates a GitHub Release automatically.
See [.github/workflows/release.yml](.github/workflows/release.yml).

---

## Repository Structure

```
cc-notify/
├── src/
│   ├── main.py         # entry point — wires server + tray
│   ├── server.py       # Flask webhook receiver
│   ├── notifier.py     # win11toast wrapper
│   ├── tray.py         # pystray system tray + "Setup Hooks" menu action
│   ├── hooks_setup.py  # auto-detect + configure Windows/WSL2 Claude Code hooks
│   └── config.py       # %APPDATA% config persistence
├── scripts/
│   ├── setup-hooks.ps1 # Windows: configure Claude Code hooks
│   ├── setup-hooks.sh  # WSL2: configure Claude Code hooks
│   └── create_icon.py  # generate assets/icon.ico via Pillow
├── examples/
│   ├── settings-snippet.json   # drop this into ~/.claude/settings.json
│   └── config-example.json     # annotated cc-notify config template
├── docs/
│   ├── requirements.md         # functional + non-functional requirements
│   ├── claude-code-hooks.md    # full hooks event reference
│   ├── windows-notifications.md # Windows toast capabilities + limits
│   └── distribution.md         # build, release, and code-signing guide
├── .github/workflows/
│   └── release.yml     # CI: build EXE and publish GitHub Release on tag
├── build.spec          # PyInstaller configuration
├── requirements.txt    # runtime Python dependencies
└── pyproject.toml      # project metadata
```

---

## Dependencies

All dependencies are declared in `pyproject.toml` and managed by [uv](https://docs.astral.sh/uv/).

| Package | Group | Purpose |
|---|---|---|
| `win11toast` | runtime | WinRT-based Windows toast notifications |
| `flask` | runtime | Lightweight webhook HTTP server |
| `waitress` | runtime | Production WSGI server (replaces Flask dev server) |
| `pystray` | runtime | System tray icon |
| `pillow` | runtime | Icon image generation |
| `pyinstaller` | dev | Packages the app into a standalone Windows EXE |

---

## Troubleshooting

**No notifications appear**

- Confirm cc-notify is running (purple bell in system tray).
- Check Windows Settings → System → Notifications → ensure notifications are
  not globally disabled.
- Do NOT run cc-notify as Administrator — Windows blocks notifications from
  elevated processes.
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
| [docs/windows-notifications.md](docs/windows-notifications.md) | Windows toast capabilities and limits |
| [docs/distribution.md](docs/distribution.md) | Build, release, and code-signing guide |

---

## License

MIT — see [LICENSE](LICENSE).
