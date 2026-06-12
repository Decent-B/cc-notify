# cc-notify — Requirements

## Overview

**cc-notify** is a lightweight Windows background application that listens for
Claude Code lifecycle events over HTTP webhooks and presents them as native
Windows toast notifications. The goal is to let users work in another window
while Claude Code runs autonomously, and be alerted the moment it needs
attention.

---

## Functional Requirements

### FR-1 — Notification Events

The app MUST send a native Windows toast notification for the following Claude
Code events:

| Event | Trigger | Notification message |
|---|---|---|
| Permission required | `PermissionRequest` hook OR `Notification[permission_prompt]` | "Claude Code — Permission Required" with tool name or message from hook |
| Idle / waiting for input | `Notification[idle_prompt]` | "Claude Code — Waiting for Input" |
| Generation complete | `Stop` hook | "Claude Code — Task Complete" |
| Auth success (optional) | `Notification[auth_success]` | "Claude Code" with hook message |
| Elicitation (optional) | `Notification[elicitation_dialog]` | "Claude Code" with hook message |

### FR-2 — Webhook HTTP Server

- The app MUST expose a local HTTP POST endpoint at `/webhook`.
- The default port MUST be **9876**, configurable via `config.json`.
- The server MUST accept the full Claude Code hook JSON payload (see [claude-code-hooks.md](claude-code-hooks.md)).
- The server MUST return HTTP 200 immediately for all valid requests.
- The server MUST bind to `0.0.0.0` (not just `127.0.0.1`) so WSL2 and LAN
  access works without extra configuration.
- A liveness endpoint `GET /health` MUST return `{"status": "ok"}`.

### FR-3 — System Tray Presence

- The app MUST show a persistent icon in the Windows system tray.
- The tray menu MUST include at minimum: app name/version label, listening port
  label, and an **Exit** option.
- The tray icon tooltip MUST show the listening port.

### FR-4 — Single-Instance Guard

- The app MUST detect if another instance is already running on the configured
  port and exit gracefully, showing a notification explaining why.

### FR-5 — Configuration File

- All user-configurable options MUST be readable from
  `%APPDATA%\cc-notify\config.json`.
- The app MUST start with defaults if the file is absent or malformed.
- Users MUST be able to toggle each notification type individually.

### FR-6 — Hook Setup Automation

- A PowerShell script (`scripts/setup-hooks.ps1`) MUST merge the required hook
  entries into `%USERPROFILE%\.claude\settings.json` without destroying
  unrelated settings already present.
- A Bash script (`scripts/setup-hooks.sh`) MUST do the same for WSL2
  environments, auto-detecting the Windows host IP.
- Both scripts MUST be idempotent (safe to run multiple times).
- The PowerShell script MUST support an `-AddToStartup` flag that creates a
  Windows startup shortcut.

---

## Non-Functional Requirements

### NFR-1 — Reliability

- A notification failure (e.g. WinRT API error) MUST NOT crash the webhook
  server. All notification calls are wrapped in try/except.
- A malformed or unexpected JSON payload from Claude Code MUST be silently
  ignored (return 200).

### NFR-2 — Performance

- The server MUST respond to webhook requests within 100 ms (notifications are
  dispatched asynchronously after the response is sent — Waitress handles
  thread pooling).
- Idle CPU usage MUST be < 1% on a modern machine.
- Memory footprint MUST be < 100 MB (typical PyInstaller + Python runtime).

### NFR-3 — Security

- The server MUST NOT expose any unauthenticated write surface beyond the
  `/webhook` endpoint.
- No data from the webhook payload is ever sent to external services.
- The app requires no Administrator / elevated privileges to run or send
  notifications (Windows notification APIs block elevated processes).

### NFR-4 — Compatibility

- **Windows 10** (version 1903 and later) and **Windows 11** — both required.
- Python **3.9** through **3.12** for development.
- The distributed `.exe` bundles its own Python runtime; no Python installation
  is required on the target machine.
- Works with Claude Code running **natively on Windows** and via **WSL2**.

### NFR-5 — Distribution

- A GitHub Actions workflow MUST automatically build and publish a pre-built
  `.exe` on every version tag push.
- The release MUST include a `SHA256SUMS.txt` for integrity verification.
- The README MUST document the SmartScreen warning that appears for unsigned
  executables and explain how to bypass it safely.

### NFR-6 — Maintainability

- All notification library calls MUST be isolated in `notifier.py` so the
  underlying library can be swapped without touching the server or tray code.
- Module responsibilities MUST remain distinct: `config.py` (persistence),
  `server.py` (HTTP), `notifier.py` (WinRT), `tray.py` (UI), `main.py`
  (wiring).

---

## Out of Scope

- macOS or Linux desktop notifications (app is Windows-only by design).
- Two-way communication: the server never returns decisions to Claude Code;
  all hooks are configured with `async: true`.
- Notification filtering by project or working directory (can be added later).
- A GUI settings panel (config is edited manually via `config.json` for now).
