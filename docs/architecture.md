# Architecture

cc-notify is two projects: **Core** (everything that can be decided without a screen) and **App**
(the WinUI 3 shell that draws things). Dependencies point one way: `App → Core`.

```
                          ┌──────────────── CcNotify.App (WinUI 3) ─────────────────┐
                          │ AppHost (composition root)                              │
 Claude Code ──HTTP──►    │ TrayMenu · ToastPresenter/ToastWindow · SettingsWindow  │
                          └───────────────▲─────────────────────────────────────────┘
                                          │ implements IToastPresenter, ISettingsActions
┌───────────────────────────── CcNotify.Core ─────────────────────────────────────────┐
│ WebhookServer ─► HookEvent ─► NotificationRouter ─► NotificationService             │
│                                   (pure)              ├─ ISoundPlayer               │
│                                                       ├─ DisplaySelector ─► IDisplayProvider, IVsCodeWindows
│                                                       ├─ IVsCodeLauncher ─► IWsl ─► IProcessRunner
│                                                       └─ IToastPresenter  (UI)      │
│ HookSetupService ─► IHookInstaller[] (Windows, WSL2)    UpdateService               │
│ AutostartService ─► registry                            SettingsStore · AppState    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Request flow

1. `WebhookServer` (HttpListener on `127.0.0.1`) checks the `?token=` secret in constant time and
   parses the payload into a `HookEvent`.
2. `NotificationRouter.Route(event, settings)` — a pure function — returns the `Notification` to
   show, or null (event disabled / unknown). Message bodies come from `IMessageCatalog`
   (`Resources/messages.json`).
3. `NotificationService` plays the sound, asks `DisplaySelector` which monitor to use, attaches the
   click action (focus VS Code for `cwd`) and hands it to `IToastPresenter`.
4. `ToastPresenter` (App) stacks `ToastWindow`s in the bottom-right of that display's work area.

## Choosing the monitor

Windows toasts cannot be placed; they always use the primary display. So popups are our own
borderless, always-on-top, non-activating WinUI windows (`WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`, shown
with `AppWindow.Show(activateWindow: false)` so they never steal keyboard focus).

`DisplaySelector` applies `MonitorTarget` from settings:

| Target | Rule |
|---|---|
| `FollowVsCode` | monitor of the VS Code window whose title contains the project folder, else any VS Code window, else the cursor's monitor |
| `FollowCursor` | monitor under the cursor |
| `Primary` | primary monitor |
| `Specific` | monitor with the saved `DeviceName`; falls back to cursor/primary if unplugged |

Positions are computed in physical pixels from each monitor's own work area and effective DPI
(`GetDpiForMonitor`, app is PerMonitorV2), so mixed-DPI setups lay out correctly.

## Start with Windows

`AutostartService` follows the Windows `StartupTask` principle that an app must not override the
user's choice:

- Writes only `HKCU\…\Run` with a **quoted** exe path.
- Never touches `StartupApproved\Run` — that value is the Settings › Apps › Startup / Task Manager
  switch. An odd first byte means the user turned it off → status `DisabledBySystem`, the
  Settings window explains it and links to `ms-settings:startupapps`.
- On by default **once**: `AppSettings.AutostartInitialized` records that the default was applied,
  so a later "Off" sticks. Later launches only repair the path if the exe moved.

## Design rules

- **Core has no UI types.** Anything touching a screen sits behind an interface
  (`IToastPresenter`, `IDisplayProvider`, `IVsCodeWindows`, `IProcessRunner`, `IWsl`), which is
  what makes the pure logic testable (`tests/CcNotify.Core.Tests`).
- **Open for extension, closed for modification.** A new Claude Code environment = a new
  `IHookInstaller`. A new popup style = another `IToastPresenter`. A new event = one case in
  `NotificationRouter`.
- **One composition root** (`AppHost`) wires concrete classes; nothing else uses `new` on a service.
- **Immutable settings.** `AppSettings` is a record; `ISettingsStore.Update(s => s with { … })`
  persists atomically and raises `Changed`.
- **Failures never reach Claude Code.** The popup pipeline catches and logs; the server always
  answers 200 to authenticated hooks.
- **Backwards compatible files.** `config.json` / `state.json` keep the snake_case keys of the
  Python releases, so upgrading preserves the webhook token and existing hooks keep working.

## Sandbox mode

`CC_NOTIFY_DATA_DIR=<folder>` redirects config/state/log there and makes hook setup write to
`<folder>\home` instead of the real Claude Code settings (WSL is skipped). Use it to run a dev build
safely next to your real install.

## Testing

`dotnet test tests/CcNotify.Core.Tests` covers routing, settings/state compatibility, the hook
merger and installer, VS Code URI building, update logic, and autostart against a throwaway
registry key. Window/popup behaviour is verified by running the app (see `CC_NOTIFY_DATA_DIR`).
