# Windows Toast Notifications — Reference

Research notes on Windows native toast notification capabilities and limits,
compiled for the cc-notify project.

---

## What a Toast Can Display

### Text

| Element | Limit |
|---|---|
| Total text elements | 3 (1 title + 2 body) |
| Title max lines | 2 (bold, larger) |
| Body max lines (combined) | 4 |

Text supports data binding for live updates post-display.

### Images

| Type | Placement | Optimal size | Notes |
|---|---|---|---|
| App logo override | Left square thumbnail | 48 × 48 px | Supports `hint-crop="circle"` |
| Inline image | Below text, full width | Any | Fills notification width |
| Hero image | Top of notification | 364 × 180 px | Prominent banner |

**File-size limit:** 3 MB on normal connections, 1 MB on metered connections.
Remote images that fail to download are silently dropped.

### Interactive Elements

- **Buttons:** Up to **5 total** (including right-click context menu entries).
  Each button can have a text label, icon (16 × 16 px white PNG), and tooltip
  (Windows 11+).
- **Text input:** Quick-reply box with inline Send button.
- **Selection input:** Dropdown combo box.

### Audio

System sounds via `ms-winsoundevent:` URI (≈ 20 named events), e.g.:

| Event URI | Description |
|---|---|
| `ms-winsoundevent:Notification.Default` | Standard notification chime |
| `ms-winsoundevent:Notification.Looping.Alarm2` | Looping alarm (used for permission prompts) |
| `ms-winsoundevent:Notification.IM` | Instant-message ping |
| `ms-winsoundevent:Notification.Reminder` | Reminder chime |

Custom audio via `ms-appx:///` or `ms-appdata:///` URIs (local files only;
remote audio is not supported in the standard WinRT API).

### Scenarios (Display Modes)

| Scenario | Behaviour |
|---|---|
| *(default)* | Stays on screen for 7 seconds, then moves to Notification Center |
| `Reminder` | Stays until dismissed |
| `Alarm` | Looping audio, stays until dismissed |
| `IncomingCall` | Full-size layout |
| `Urgent` | Breaks through Focus Assist (Windows 11 only, requires user opt-in) |

---

## Limits and Constraints

| Constraint | Value |
|---|---|
| Default popup duration | ~7 seconds |
| Long popup duration (Alarm/Reminder scenario) | 25 seconds |
| Max notifications per app in Notification Center | **20** (oldest are silently removed when exceeded) |
| Notification Center persistence | **7 days** from arrival (configurable via `ExpirationTime`) |
| Tag/Group string max length | 64 characters |
| Button icon size | 16 × 16 px |
| Hero image optimal size | 364 × 180 px |

**Rate limiting:** Windows does not enforce a hard per-second rate limit for
local toast notifications. The 20-per-app cap in Notification Center is the
practical limit. As a best practice, avoid sending more than one notification
every 30 seconds for the same event type.

**Critical:** Apps running with **Administrator / elevated privileges cannot
send notifications** via Windows notification APIs. Run cc-notify as a normal
user — not as admin, not via `sudo`/`runas`.

---

## Python Library Comparison

| Library | Underlying API | Buttons | Images | Hero | Progress Bar | Last release | Status |
|---|---|---|---|---|---|---|---|
| **win11toast** | WinRT (winsdk) | Yes | Yes | Yes | Yes | Jan 2026 | Active ✅ |
| **Windows-Toasts** | WinRT (winrt-python) | Yes | Yes | Yes | Yes | May 2025 | Active ✅ |
| **toasted** | WinRT + registry | Yes | Yes | Yes | Yes | Mar 2024 | Slow |
| **winotify** | PowerShell subprocess | Yes (≤5) | Icon only | No | No | Feb 2022 | Abandoned ❌ |
| **win10toast** | Legacy Win32 | No | Icon only | No | No | 2020 | Obsolete ❌ |

**cc-notify uses `win11toast`** for its simple fire-and-forget `notify()` API
and active maintenance. All notification calls are isolated in `notifier.py`,
so switching to `windows-toasts` requires only editing that one file.

---

## App User Model ID (AUMID)

Windows attributes a toast to a specific app via the App User Model ID. This
controls what name and icon appear in Notification Center.

`win11toast` handles AUMID registration automatically for unpackaged desktop
apps. When PyInstaller bundles the app, the executable's own AUMID is used.

If notifications are not appearing:

1. Confirm the process is **not** running as Administrator.
2. Check that Windows Focus Assist is not blocking notifications from unknown
   apps (Settings → System → Notifications → Focus Assist).
3. Check Windows Settings → System → Notifications → and ensure notifications
   are enabled for the app (it may appear as "Python" or "cc-notify" depending
   on how AUMID registration resolved).

---

## Notification Grouping

- `Tag`: A unique ID for a notification slot. Sending a new notification with
  the same `tag` **replaces** the existing one (update-in-place in Notification
  Center). Useful for "permission required" events where only the latest matters.
- `Group`: Logical category label. Groups tagged notifications into a
  collapsible section in Notification Center.
- `SuppressPopup=True`: Sends a notification silently to Notification Center
  with no popup banner or sound — useful for low-priority status events.

---

## WSL2 Notes

Notifications must be sent from the **Windows side** of the WSL2 boundary.
cc-notify runs as a native Windows executable, so this is handled automatically.

If you want to send a one-off Windows notification from a WSL2 bash script as
a workaround (e.g. for testing), install **BurntToast** in Windows PowerShell
and call it via the `powershell.exe` bridge:

```bash
# Run from WSL2 bash — BurntToast must be installed on the Windows side.
powershell.exe "New-BurntToastNotification -Text 'Title','Body'"
```

BurntToast installation (run in Windows PowerShell, not WSL2):
```powershell
Install-Module -Name BurntToast -Scope CurrentUser -Force
```

---

## References

- [App Notifications Overview — Microsoft Learn](https://learn.microsoft.com/en-us/windows/apps/develop/notifications/app-notifications/)
- [App Notification Content — Microsoft Learn](https://learn.microsoft.com/en-us/windows/apps/develop/notifications/app-notifications/app-notifications-content)
- [win11toast — PyPI](https://pypi.org/project/win11toast/)
- [Windows-Toasts — ReadTheDocs](https://windows-toasts.readthedocs.io/)
