# Distribution Guide

How cc-notify is packaged, released, and delivered to end users via GitHub.

---

## Build Pipeline Overview

```
git tag v1.0.0
  └── GitHub Actions (windows-latest)
        ├── pip install -r requirements.txt
        ├── pip install pyinstaller
        ├── python scripts/create_icon.py          # generates assets/icon.ico
        ├── pyinstaller build.spec                  # → dist/cc-notify.exe
        ├── rename  cc-notify-1.0.0-windows-x64.exe
        ├── SHA256 checksum  → SHA256SUMS.txt
        └── softprops/action-gh-release → GitHub Release
```

---

## PyInstaller — Single-File EXE

cc-notify is distributed as a single `cc-notify-<version>-windows-x64.exe`
produced by **PyInstaller** with `--onefile` mode (configured in `build.spec`).

| Property | Value |
|---|---|
| Python bundled | 3.11 (set in release.yml) |
| Console window | No (`console=False` in spec) |
| Typical size | 25–50 MB |
| Python required on target | No |

### Why single-file EXE?

- Zero-friction: download and double-click.
- No installer required for a single tray app.
- Fits under GitHub's 100 MB artifact limit.

### Why not an installer?

An Inno Setup / NSIS installer adds value when the app needs to register as a
Windows Service or add startup entries automatically. cc-notify keeps startup
optional (via `-AddToStartup` in `setup-hooks.ps1`) and runs as a regular user
process, so the extra complexity is not warranted yet.

---

## GitHub Releases Structure

```
Release: v1.0.0
├── cc-notify-1.0.0-windows-x64.exe   # Primary download
└── SHA256SUMS.txt                     # Integrity check
```

### Triggering a release

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions builds the EXE and publishes the release automatically.

---

## Code Signing

### Current status: unsigned

The distributed EXE is currently **not code-signed**. Windows SmartScreen will
show a "Windows protected your PC" warning on first run.

**How to bypass the SmartScreen warning:**
1. Click **"More info"** in the SmartScreen dialog.
2. Click **"Run anyway"**.

This is the standard experience for open-source apps without an EV certificate
and is safe for software you downloaded from a known GitHub repository.

### Why no code signing yet?

| Certificate type | SmartScreen result | Cost/year | Requirement |
|---|---|---|---|
| None (current) | Warning on every run | $0 | — |
| OV (Organization Validation) | Warning until reputation builds (weeks/months) | $226–$385 | Registered business |
| EV (Extended Validation) | **Instant trust, no warning** | $279–$560 | Registered business + USB HSM |

For an open-source side project:

- OV costs money but still triggers SmartScreen until the app accumulates
  enough download reputation with Microsoft — not worth it at low volumes.
- EV provides instant trust but requires a legal business entity and a physical
  hardware security module (HSM). This is the right choice once the project
  reaches significant distribution.
- **Recommendation:** Skip signing initially; add Sectigo EV (~$300/year) once
  the project has a registered entity behind it.

### Antivirus false positives

PyInstaller-bundled executables are sometimes flagged by antivirus scanners
because the same packing technique is used by some malware. This is a known
issue with PyInstaller and does not indicate the app is harmful. Submitting
the EXE to VirusTotal and referencing the clean scan result in the README
builds user confidence.

---

## Alternative Installation Methods

### Scoop (community bucket)

Scoop is a command-line installer for Windows, popular with developers:

```powershell
scoop bucket add cc-notify https://github.com/Decent-B/scoop-cc-notify
scoop install cc-notify
```

A Scoop bucket is a separate GitHub repository (`scoop-cc-notify`) containing
a JSON manifest (`bucket/cc-notify.json`) that points to the release EXE.
The `checkver` + `autoupdate` manifest fields let Scoop auto-update the
manifest when a new GitHub release appears.

**To create the bucket repo:** See the
[Scoop App Manifests Wiki](https://github.com/ScoopInstaller/Scoop/wiki/App-Manifests).

### winget

Submit a manifest to
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) so users can
install with:

```powershell
winget install Decent-B.cc-notify
```

Use `winget-create new <release-url>` to generate the manifest YAML, then open
a PR to the winget-pkgs repo. Automated review usually completes in 1–3 days.

**Note:** winget validation runs VirusTotal on the EXE. PyInstaller false
positives can cause rejection. Use an Inno Setup wrapper or sign the EXE to
reduce the false positive rate before submitting.

---

## Auto-Update

cc-notify includes a lightweight in-app update checker. When the user selects
**"Check for Updates"** from the system tray menu, the app queries:

```
https://api.github.com/repos/Decent-B/cc-notify/releases/latest
```

If a newer version is available it shows a clickable toast notification —
clicking the toast opens the releases page in the browser. The user downloads
and runs the new EXE manually; no silent background updates occur.

The implementation lives in `src/updater.py` and uses only the Python standard
library (`urllib`, `json`, `ssl`) plus `certifi` for reliable TLS certificate
verification inside the PyInstaller bundle.

---

## Running from Source (Developers)

```powershell
# Windows PowerShell
cd cc-notify
pip install -r requirements.txt
python src/main.py
```

```bash
# WSL2 — only for development; notifications require Windows-side execution.
pip install flask waitress pillow pystray
# win11toast will install but WinRT calls will fail in WSL2 Linux.
```

The icon is generated at runtime from Pillow code in `tray.py`, so no build
step is needed for development runs.

---

## Building Locally

```powershell
# Requires Windows (PyInstaller can only build for the host OS)
pip install -r requirements.txt
pip install pyinstaller
python scripts/create_icon.py       # generates assets/icon.ico
pyinstaller build.spec              # produces dist/cc-notify.exe
```
