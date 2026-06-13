#!/usr/bin/env bash
# scripts/build-windows.sh — Build the Windows EXE from inside a WSL2 distro.
#
# The app uses Windows-only APIs (WinRT toast, Win32 tray) so its runtime
# dependencies cannot install in a Linux environment. This script drives uv
# and PyInstaller on the Windows side via WSL2 interop, so you never need
# to open a separate Windows terminal.
#
# Prerequisites — install uv on the Windows side (once):
#   powershell.exe -ExecutionPolicy ByPass \
#     -c "irm https://astral.sh/uv/install.ps1 | iex"
#
# Usage:
#   bash scripts/build-windows.sh            # build only
#   bash scripts/build-windows.sh --launch   # build then launch the EXE

set -euo pipefail

# ── Guard: must run from inside WSL2 ─────────────────────────────────────────

if ! grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
  echo "error: this script is for WSL2 only." >&2
  echo "       On native Windows, run:" >&2
  echo "         uv sync --group dev --no-install-project" >&2
  echo "         uv run python scripts/create_icon.py" >&2
  echo "         uv run pyinstaller build.spec" >&2
  exit 1
fi

if ! command -v powershell.exe &>/dev/null; then
  echo "error: powershell.exe not found. WSL2 interop may be disabled." >&2
  exit 1
fi

# ── Parse arguments ───────────────────────────────────────────────────────────

LAUNCH=false
for arg in "$@"; do
  [[ "$arg" == "--launch" ]] && LAUNCH=true
done

# ── Resolve paths ─────────────────────────────────────────────────────────────

# Must be called from anywhere inside the repo; resolves to the repo root.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_PATH=$(wslpath -w "$REPO_ROOT")

echo "cc-notify — building for Windows from WSL2"
echo "  WSL2  : ${REPO_ROOT}"
echo "  Win32 : ${WIN_PATH}"
echo ""

# ── Delegate to Windows PowerShell ───────────────────────────────────────────

# NOTE on PATH: powershell.exe started from WSL2 with -NoProfile does not
# inherit the Windows user PATH set by installer scripts (uv, etc.).
# We re-read both Machine and User scopes from the registry explicitly so
# any tool installed on Windows is visible to this session.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "
  \$ErrorActionPreference = 'Stop'

  \$env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')

  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv not found on the Windows PATH. Install it from a Windows PowerShell: irm https://astral.sh/uv/install.ps1 | iex'
  }

  Set-Location '${WIN_PATH}'

  Write-Host '>>> Installing dependencies'
  uv sync --group dev --no-install-project

  Write-Host '>>> Generating icon'
  uv run python scripts/create_icon.py

  Write-Host '>>> Building EXE'
  uv run pyinstaller build.spec

  Write-Host ''
  Write-Host 'Build complete: dist\cc-notify.exe'
"

# ── Optionally launch the EXE ─────────────────────────────────────────────────

if $LAUNCH; then
  echo ""
  echo "Launching cc-notify.exe on Windows..."
  powershell.exe -NoProfile -Command "Start-Process '${WIN_PATH}\dist\cc-notify.exe'"
fi
