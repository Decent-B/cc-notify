"""
updater.py — Check for newer cc-notify releases on GitHub and apply updates.

SSL note: urllib's default HTTPS context can fail in a PyInstaller bundle on
Windows because the bundle does not carry the system certificate store.
certifi ships the Mozilla CA bundle as a plain file, so it works reliably
regardless of the deployment environment.

Self-update flow
  1. fetch_latest_release() queries the GitHub API and returns a ReleaseInfo
     when a newer EXE asset exists; None when already up to date.
  2. tray.py stores the result via set_pending_release() so the dynamic tray
     menu can offer an "Install Update" item.
  3. When the user activates the install (toast click → cc-notify:// URI →
     short-lived process → GET /do-update → running instance), apply_update()
     downloads the new EXE to %TEMP%, writes a PowerShell helper script,
     launches it as a detached process, and signals the tray to stop.
  4. The PowerShell script waits for the current process to exit, replaces the
     EXE in place, and starts the new instance.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from version import __version__

logger = logging.getLogger(__name__)

_REPO       = "Decent-B/cc-notify"
_API_URL    = f"https://api.github.com/repos/{_REPO}/releases/latest"
INSTALL_URI = "cc-notify://install"

_pending_release: Optional["ReleaseInfo"] = None


@dataclass
class ReleaseInfo:
    tag: str
    download_url: str


# ── Pending release state ─────────────────────────────────────────────────────

def get_pending_release() -> Optional[ReleaseInfo]:
    return _pending_release


def set_pending_release(release: ReleaseInfo) -> None:
    global _pending_release
    _pending_release = release


def clear_pending_release() -> None:
    global _pending_release
    _pending_release = None


# ── SSL / network ─────────────────────────────────────────────────────────────

def _ssl_context() -> ssl.SSLContext:
    """
    Return an SSL context backed by certifi's CA bundle.

    In a PyInstaller bundle urllib's default context may fail certificate
    verification because the bundle does not include the Windows cert store.
    certifi provides a self-contained Mozilla CA bundle that works in any
    deployment environment, including frozen executables.
    """
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


def _parse_semver(tag: str) -> tuple[int, ...]:
    """'v0.1.2' → (0, 1, 2). Returns (0,) on any parse failure."""
    try:
        return tuple(int(x) for x in tag.lstrip("v").split("."))
    except ValueError:
        return (0,)


# ── Release queries ───────────────────────────────────────────────────────────

def fetch_latest_release() -> Optional[ReleaseInfo]:
    """
    Query GitHub for the latest non-draft, non-prerelease release.

    Returns a ReleaseInfo when a newer version with a cc-notify.exe asset
    exists; returns None if already up to date.  Raises on network or parse
    errors so the caller can surface the specific failure reason.
    """
    req = urllib.request.Request(
        _API_URL,
        headers={"User-Agent": f"cc-notify/{__version__}"},
    )
    with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tag = data.get("tag_name", "").strip()
    logger.debug("Latest release tag from GitHub: %s", tag or "(none)")
    if not tag:
        raise ValueError("GitHub response contained no tag_name field")

    if not (_parse_semver(tag) > _parse_semver(__version__)):
        logger.info("Already on latest version (%s)", __version__)
        return None

    for asset in data.get("assets", []):
        if asset.get("name", "").lower() == "cc-notify.exe":
            logger.info("Update available: %s → %s", __version__, tag)
            return ReleaseInfo(tag=tag, download_url=asset["browser_download_url"])

    logger.warning("Release %s has no cc-notify.exe asset — skipping", tag)
    return None


# ── Download ──────────────────────────────────────────────────────────────────

def download_update(release: ReleaseInfo) -> str:
    """
    Download the EXE asset for *release* to %TEMP%/cc-notify-update.exe.

    Returns the absolute path to the downloaded file.  Streams in 64 KB
    chunks so large files do not require holding the full EXE in memory.
    Raises on any network or I/O error.
    """
    import tempfile
    dest = os.path.join(tempfile.gettempdir(), "cc-notify-update.exe")
    req = urllib.request.Request(
        release.download_url,
        headers={"User-Agent": f"cc-notify/{__version__}"},
    )
    logger.info("Downloading %s → %s", release.download_url, dest)
    with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as resp, \
         open(dest, "wb") as out:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            out.write(chunk)
    logger.info("Download complete: %s", dest)
    return dest


# ── PowerShell updater script ─────────────────────────────────────────────────

def _ps_escape(path: str) -> str:
    """Escape a path for use in a PowerShell single-quoted string."""
    return path.replace("'", "''")


def _write_updater_script(old_pid: int, old_exe: str, new_exe: str) -> str:
    """
    Write a PowerShell helper script to %TEMP%/cc-notify-update.ps1 and
    return its path.

    The script waits for *old_pid* to exit (up to 15 s), replaces *old_exe*
    with *new_exe* (Move-Item backup fallback on copy failure), starts the
    new EXE, then deletes both the temporary EXE and itself.

    Single-quoted PowerShell strings are used for all paths so that
    backslashes and dollar signs in typical Windows paths are literal — no
    extra escaping is needed.
    """
    import tempfile

    script = (
        f"$oldPid = {old_pid}\n"
        f"$oldExe = '{_ps_escape(old_exe)}'\n"
        f"$newExe = '{_ps_escape(new_exe)}'\n"
        "$deadline = (Get-Date).AddSeconds(15)\n"
        "while ((Get-Process -Id $oldPid -ErrorAction SilentlyContinue) -and\n"
        "       (Get-Date) -lt $deadline) {\n"
        "    Start-Sleep -Milliseconds 300\n"
        "}\n"
        "Start-Sleep -Seconds 1\n"
        "try {\n"
        "    Copy-Item $newExe $oldExe -Force -ErrorAction Stop\n"
        "} catch {\n"
        "    $backup = \"$oldExe.old\"\n"
        "    Move-Item $oldExe $backup -Force -ErrorAction SilentlyContinue\n"
        "    Copy-Item $newExe $oldExe -Force\n"
        "    Remove-Item $backup -Force -ErrorAction SilentlyContinue\n"
        "}\n"
        "Start-Process $oldExe\n"
        "Remove-Item $newExe -Force -ErrorAction SilentlyContinue\n"
        "Remove-Item $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue\n"
    )
    script_path = os.path.join(tempfile.gettempdir(), "cc-notify-update.ps1")
    Path(script_path).write_text(script, encoding="utf-8")
    return script_path


# ── Apply ─────────────────────────────────────────────────────────────────────

def apply_update(
    release: ReleaseInfo,
    notify_fn: Optional[Callable[[str, str], None]] = None,
    stop_icon_fn: Optional[Callable[[], None]] = None,
) -> None:
    """
    Download *release*, swap the EXE via a detached PowerShell script, and
    signal the tray icon to stop so the process can exit cleanly.

    notify_fn(title, body) — optional; shows status toasts during download
        and install steps.
    stop_icon_fn()         — optional; called after the PS script is launched
        to remove the tray icon and let the main thread return.
    """
    if notify_fn:
        notify_fn(
            "cc-notify — Downloading Update…",
            f"Fetching version {release.tag}, please wait.",
        )

    try:
        new_exe = download_update(release)
    except Exception as exc:
        logger.error("Update download failed: %s", exc, exc_info=True)
        if notify_fn:
            notify_fn("cc-notify — Update Failed", f"Download error: {exc}")
        return

    if notify_fn:
        notify_fn("cc-notify — Installing…", "The app will restart in a moment.")

    old_exe = sys.executable
    old_pid = os.getpid()
    script_path = _write_updater_script(old_pid, old_exe, new_exe)

    logger.info(
        "Launching updater script (pid=%d, old=%s, new=%s)",
        old_pid, old_exe, new_exe,
    )

    import subprocess
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
    )

    if stop_icon_fn:
        stop_icon_fn()
