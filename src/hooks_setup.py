"""
hooks_setup.py — Auto-configure Claude Code webhook hooks.

Modifies ~/.claude/settings.json for:
  - Windows native Claude Code  (always attempted; cc-notify itself runs on Windows)
  - WSL2 Claude Code            (attempted if wsl.exe is available and a distro is installed)

All public functions are thread-safe and do not mutate global state.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class SetupResult:
    windows_ok:     bool            = False
    windows_error:  Optional[str]   = None
    wsl2_available: bool            = False
    wsl2_distro:    Optional[str]   = None   # name of the configured distro
    wsl2_ok:        bool            = False
    wsl2_error:     Optional[str]   = None

    @property
    def fully_ok(self) -> bool:
        """True when every detected environment was configured without error."""
        return self.windows_ok and (not self.wsl2_available or self.wsl2_ok)

    def summary(self) -> str:
        """Short human-readable line suitable for a toast notification body."""
        parts: list[str] = []

        if self.windows_ok:
            parts.append("Windows ✓")
        else:
            parts.append(f"Windows ✗ — {self.windows_error or 'unknown error'}")

        if self.wsl2_available:
            label = f"WSL2 ({self.wsl2_distro})" if self.wsl2_distro else "WSL2"
            if self.wsl2_ok:
                parts.append(f"{label} ✓")
            else:
                parts.append(f"{label} ✗ — {self.wsl2_error or 'unknown error'}")
        else:
            parts.append("WSL2 not detected")

        return "  |  ".join(parts)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _build_hooks_block(webhook_url: str) -> dict:
    hook_entry = {"type": "http", "url": webhook_url, "async": True}
    hook_group = {"hooks": [hook_entry]}
    return {
        "Notification":      [hook_group],
        "Stop":              [hook_group],
        "PermissionRequest": [hook_group],
    }


def _apply_hooks(settings: dict, webhook_url: str) -> dict:
    """Merge cc-notify hook entries into an existing settings dict in-place."""
    if "hooks" not in settings:
        settings["hooks"] = {}
    settings["hooks"].update(_build_hooks_block(webhook_url))
    return settings


# ── Windows setup ─────────────────────────────────────────────────────────────

def setup_windows(port: int) -> tuple[bool, Optional[str]]:
    """
    Merge webhook hooks into %USERPROFILE%\\.claude\\settings.json.

    USERPROFILE is always set when the process runs as a native Windows
    executable, so Path.home() is a reliable fallback.

    Returns (success, error_message_or_None).
    """
    settings_path = (
        Path(os.environ.get("USERPROFILE", "")) / ".claude" / "settings.json"
        if os.environ.get("USERPROFILE")
        else Path.home() / ".claude" / "settings.json"
    )
    webhook_url = f"http://localhost:{port}/webhook"

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        existing: dict = {}
        if settings_path.exists():
            try:
                existing = json.loads(settings_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("settings.json unreadable or malformed — starting fresh")

        merged = _apply_hooks(existing, webhook_url)
        settings_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        logger.info("Windows hooks configured → %s", settings_path)
        return True, None
    except Exception as exc:
        logger.error("Windows setup error: %s", exc)
        return False, str(exc)


# ── WSL2 detection ────────────────────────────────────────────────────────────

def _wsl2_distros() -> list[str]:
    """
    Return installed WSL2 distro names, or an empty list if WSL2 is unavailable.

    wsl.exe --list --quiet outputs UTF-16 LE (with null bytes between chars)
    on most Windows versions, so we decode it explicitly rather than relying on
    the default system codec.
    """
    try:
        result = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        raw = result.stdout
        try:
            text = raw.decode("utf-16-le")
        except UnicodeDecodeError:
            # Newer builds may output plain UTF-8.
            text = raw.decode("utf-8", errors="ignore")

        # Strip null characters left over from UTF-16 padding.
        distros = [line.strip().replace("\x00", "") for line in text.splitlines()]
        return [d for d in distros if d]

    except FileNotFoundError:
        # wsl.exe not on PATH — WSL2 is not installed.
        return []
    except subprocess.TimeoutExpired:
        logger.warning("wsl.exe --list timed out")
        return []


def _wsl2_windows_host_ip(distro: Optional[str] = None) -> Optional[str]:
    """
    Ask a WSL2 distro for the Windows host IP address.

    WSL2 always lists the Windows host as the nameserver in /etc/resolv.conf.
    On Windows 11 with mirrored-networking, 'host.docker.internal' also works,
    but the resolv.conf method is universally available across all WSL2 versions.
    """
    cmd = ["wsl.exe"]
    if distro:
        cmd += ["--distribution", distro]
    cmd += ["--", "awk", "/^nameserver/ {print $2; exit}", "/etc/resolv.conf"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        ip = result.stdout.strip()
        return ip if ip else None
    except (subprocess.TimeoutExpired, OSError):
        return None


# ── WSL2 setup ────────────────────────────────────────────────────────────────

# This script runs *inside* the WSL2 distro via stdin.  Using stdin sidesteps
# all shell-quoting issues — the webhook URL is passed as argv[1] so it never
# needs to be embedded in source code or escaped through multiple shell layers.
_WSL_SETUP_SCRIPT = """\
import json, os, sys

webhook_url = sys.argv[1]
path = os.path.expanduser("~/.claude/settings.json")
os.makedirs(os.path.dirname(path), exist_ok=True)

try:
    with open(path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

block = {"hooks": [{"type": "http", "url": webhook_url, "async": True}]}
if "hooks" not in settings:
    settings["hooks"] = {}
settings["hooks"].update({
    "Notification":      [block],
    "Stop":              [block],
    "PermissionRequest": [block],
})

with open(path, "w") as f:
    json.dump(settings, f, indent=2)

print("configured:", path)
"""


def setup_wsl2(port: int, distro: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """
    Configure Claude Code hooks inside a WSL2 distro.

    Steps:
      1. Determine the Windows host IP as seen from inside the distro.
      2. Run _WSL_SETUP_SCRIPT via stdin so the webhook URL is never
         shell-interpolated (wsl.exe passes stdin directly to python3).

    Returns (success, error_message_or_None).
    """
    host_ip = _wsl2_windows_host_ip(distro)
    if not host_ip:
        return False, "Could not determine Windows host IP from inside WSL2"

    webhook_url = f"http://{host_ip}:{port}/webhook"

    cmd = ["wsl.exe"]
    if distro:
        cmd += ["--distribution", distro]
    # python3 - reads the script from stdin; argv[1] carries the webhook URL.
    cmd += ["--", "python3", "-", webhook_url]

    try:
        result = subprocess.run(
            cmd,
            input=_WSL_SETUP_SCRIPT.encode("utf-8"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or f"exit code {result.returncode}"
            logger.error("WSL2 setup failed (%s): %s", distro or "default", error)
            return False, error

        logger.info("WSL2 hooks configured (%s): %s", distro or "default", result.stdout.strip())
        return True, None
    except subprocess.TimeoutExpired:
        return False, "WSL2 command timed out (30 s)"
    except OSError as exc:
        return False, str(exc)


# ── Combined entry point ──────────────────────────────────────────────────────

def setup_all(port: int) -> SetupResult:
    """
    Detect available environments and configure Claude Code hooks in all of them.

    Windows is always configured.  WSL2 is configured if wsl.exe is reachable
    and at least one distro is installed — only the default (first) distro is
    targeted; users with multiple distros can run setup-hooks.sh manually.

    This function may take several seconds when WSL2 is present (subprocess
    round-trips to the distro).  Call it from a background thread.
    """
    result = SetupResult()

    result.windows_ok, result.windows_error = setup_windows(port)

    distros = _wsl2_distros()
    result.wsl2_available = bool(distros)

    if distros:
        result.wsl2_distro = distros[0]
        result.wsl2_ok, result.wsl2_error = setup_wsl2(port, distros[0])

    return result
