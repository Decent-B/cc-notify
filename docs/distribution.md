# Distribution Guide

## Build pipeline

```
git tag v0.2.0 && git push origin v0.2.0
        │
        ▼
GitHub Actions (.github/workflows/release.yml, windows-latest)
        ├── dotnet test tests/CcNotify.Core.Tests
        ├── dotnet publish src/CcNotify.App -c Release -p:Platform=x64 -p:Version=<tag> -o dist
        ├── rename → cc-notify-<version>-windows-x64.exe, SHA-256 checksum
        └── create GitHub Release with the EXE + SHA256SUMS.txt
```

## Single-file, self-contained EXE

The app is an **unpackaged, self-contained WinUI 3** program published with
`PublishSingleFile` + compression (see the properties in
`src/CcNotify.App/CcNotify.App.csproj`, per the
[Windows App SDK docs](https://learn.microsoft.com/windows/apps/package-and-deploy/unpackage-winui-app)).

- Nothing to install: the .NET runtime and the Windows App SDK runtime are inside the EXE
  (about 90 MB, compressed).
- On first launch the bundle extracts to a temp folder, so the very first start is slower.
- No MSIX / package identity, so no Store updates — cc-notify updates itself from GitHub Releases.

## Auto-update

*Tray → Check for updates* (or Settings) calls the GitHub API for the latest release, picks the
`cc-notify*.exe` asset, downloads it to `%TEMP%`, and starts a detached PowerShell helper that
waits for the app to exit, swaps the EXE in place and starts the new one. HTTPS uses the
Windows certificate store through .NET; no extra CA bundle is needed.

> Releases up to 0.1.7 only self-update from an asset named exactly `cc-notify.exe`, but CI used to
> publish only `cc-notify-<version>-windows-x64.exe`, so their updater never found anything. From
> 0.2 the release also carries a copy named `cc-notify.exe`, so 0.1.x users can run *Check for
> updates* and get the new build in place (not yet tested end-to-end against a real 0.1.x install).

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


## Building locally

```powershell
dotnet publish src/CcNotify.App -c Release -p:Platform=x64 -o dist   # → dist/cc-notify.exe
```

From WSL2: `bash scripts/build-windows.sh`.
