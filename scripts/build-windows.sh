#!/usr/bin/env bash
# scripts/build-windows.sh — Build, test and publish cc-notify for Windows from inside WSL2.
#
# The app is a WinUI 3 / .NET 8 program, so it must be built by the Windows .NET SDK.
# MSBuild and NuGet misbehave on \\wsl$ UNC paths, so the sources are first mirrored to a
# folder on the Windows C: drive, built there, and the single-file EXE is copied back to
# dist/cc-notify.exe.
#
# Prerequisite (once, on Windows):  winget install Microsoft.DotNet.SDK.8
#
# Usage:
#   bash scripts/build-windows.sh            # test + publish
#   bash scripts/build-windows.sh --launch   # ...then start the EXE

set -euo pipefail

if ! grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
  echo "error: this script is for WSL2 only. On native Windows run:" >&2
  echo "         dotnet test tests/CcNotify.Core.Tests" >&2
  echo "         dotnet publish src/CcNotify.App -c Release -p:Platform=x64 -o dist" >&2
  exit 1
fi
command -v powershell.exe >/dev/null || { echo "error: powershell.exe not found (WSL interop disabled?)" >&2; exit 1; }
command -v rsync >/dev/null || { echo "error: rsync is required (sudo apt install rsync)" >&2; exit 1; }

LAUNCH=false
for arg in "$@"; do [[ "$arg" == "--launch" ]] && LAUNCH=true; done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_TEMP="$(powershell.exe -NoProfile -Command 'Write-Output $env:LOCALAPPDATA' | tr -d '\r')"
BUILD_WIN="${WIN_TEMP}\\cc-notify-build"
BUILD_WSL="$(wslpath "$BUILD_WIN")"

echo "cc-notify — building for Windows from WSL2"
echo "  sources : ${REPO_ROOT}"
echo "  build in: ${BUILD_WIN}"

mkdir -p "$BUILD_WSL"
rsync -a --delete --exclude .git --exclude bin --exclude obj --exclude dist \
  "$REPO_ROOT/" "$BUILD_WSL/"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "
  \$ErrorActionPreference = 'Stop'
  \$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
  if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'dotnet SDK not found. Run: winget install Microsoft.DotNet.SDK.8' }
  Set-Location '${BUILD_WIN}'

  Write-Host '>>> Running tests'
  dotnet test tests\\CcNotify.Core.Tests --nologo -v q
  if (\$LASTEXITCODE -ne 0) { throw 'tests failed' }

  Write-Host '>>> Publishing single-file EXE'
  dotnet publish src\\CcNotify.App -c Release -p:Platform=x64 -o publish --nologo -v q
  if (\$LASTEXITCODE -ne 0) { throw 'publish failed' }
"

mkdir -p "$REPO_ROOT/dist"
cp "$BUILD_WSL/publish/cc-notify.exe" "$REPO_ROOT/dist/cc-notify.exe"
echo ""
echo "Build complete: dist/cc-notify.exe"

if $LAUNCH; then
  echo "Launching..."
  powershell.exe -NoProfile -Command "Start-Process '${BUILD_WIN}\\publish\\cc-notify.exe'"
fi
