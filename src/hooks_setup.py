"""
hooks_setup.py — Auto-configure Claude Code webhook hooks.

Modifies ~/.claude/settings.json for:
  - Windows native Claude Code  (always attempted; cc-notify itself runs on Windows)
  - WSL2 Claude Code            (attempted if wsl.exe is available and a distro exists)

Both environments receive:  http://localhost:<port>/webhook

  Windows:  cc-notify and Claude Code for Windows run on the same machine,
            so localhost is always correct.

  WSL2:     WSL2 forwards localhost connections from inside the distro to the
            Windows host by default (localhostForwarding = true in .wslconfig,
            the factory default for both virtual-switch and mirrored-networking
            modes).  If you have explicitly disabled localhost forwarding, edit
            ~/.claude/settings.json inside WSL2 and replace 'localhost' with
            your Windows host IP:
              awk '/^nameserver/{print $2}' /etc/resolv.conf
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
        "StopFailure":       [hook_group],
        "PermissionRequest": [hook_group],
    }


def _apply_hooks(settings: dict, webhook_url: str) -> dict:
    """Merge cc-notify hook entries into an existing settings dict in-place."""
    if "hooks" not in settings:
        settings["hooks"] = {}
    settings["hooks"].update(_build_hooks_block(webhook_url))
    return settings


# ── Windows setup ─────────────────────────────────────────────────────────────

def setup_windows(port: int, token: str) -> tuple[bool, Optional[str]]:
    """
    Merge webhook hooks into %USERPROFILE%\\.claude\\settings.json.

    Returns (success, error_message_or_None).
    """
    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile:
        settings_path = Path(userprofile) / ".claude" / "settings.json"
    else:
        # USERPROFILE is always set for a normal Windows user process; falling
        # back to Path.home() handles edge cases like running from a service.
        logger.warning("[Windows] USERPROFILE env var not set; falling back to Path.home()")
        settings_path = Path.home() / ".claude" / "settings.json"

    # The token is included in the URL so the server can authenticate requests.
    webhook_url = f"http://localhost:{port}/webhook?token={token}"

    logger.info("[Windows] Settings file : %s", settings_path)
    logger.info("[Windows] Webhook URL   : %s", webhook_url)

    try:
        # Ensure the .claude directory exists
        if not settings_path.parent.exists():
            logger.info("[Windows] Creating directory: %s", settings_path.parent)
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Load any existing settings so we don't clobber unrelated keys
        existing: dict = {}
        if settings_path.exists():
            logger.info("[Windows] File exists — reading current content")
            try:
                existing = json.loads(settings_path.read_text(encoding="utf-8"))
                current_hooks = list(existing.get("hooks", {}).keys())
                logger.info("[Windows] Hooks currently configured: %s",
                            current_hooks if current_hooks else "(none)")
            except json.JSONDecodeError as exc:
                logger.warning(
                    "[Windows] settings.json is not valid JSON (%s) — "
                    "existing content will be replaced", exc,
                )
            except OSError as exc:
                logger.warning(
                    "[Windows] Cannot read settings.json (%s) — "
                    "will create a new file", exc,
                )
        else:
            logger.info("[Windows] File not found — will create a new settings.json")

        # Log which events will be overwritten vs added fresh
        existing_hooks: set[str] = set(existing.get("hooks", {}).keys())
        target_events = ["Notification", "Stop", "StopFailure", "PermissionRequest"]
        for event in target_events:
            if event in existing_hooks:
                logger.info("[Windows] Overwriting existing '%s' hook", event)
            else:
                logger.info("[Windows] Adding new '%s' hook", event)

        merged = _apply_hooks(existing, webhook_url)
        logger.info("[Windows] Writing updated settings...")
        settings_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        logger.info("[Windows] ✓ Done — hooks written to %s", settings_path)
        return True, None

    except PermissionError as exc:
        msg = f"Permission denied writing {settings_path}: {exc}"
        logger.error("[Windows] ✗ %s", msg)
        return False, msg
    except OSError as exc:
        logger.error("[Windows] ✗ OS error: %s", exc)
        return False, str(exc)
    except Exception as exc:
        logger.error("[Windows] ✗ Unexpected error: %s", exc, exc_info=True)
        return False, str(exc)


# ── WSL2 detection ────────────────────────────────────────────────────────────

def _wsl2_distros() -> list[str]:
    """
    Return installed WSL2 distro names, or [] if WSL2 is unavailable.

    wsl.exe --list --quiet outputs UTF-16 LE (with null bytes between chars)
    on most Windows versions, so we decode it explicitly rather than relying
    on the default system codec.
    """
    logger.info("[WSL2] Checking for wsl.exe...")
    try:
        result = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True,
            timeout=10,
        )
    except FileNotFoundError:
        logger.info("[WSL2] wsl.exe not found — WSL2 is not installed or not on PATH")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("[WSL2] wsl.exe --list timed out after 10 s")
        return []

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip() if result.stderr else ""
        logger.info(
            "[WSL2] wsl.exe --list returned code %d%s",
            result.returncode,
            f": {stderr}" if stderr else "",
        )
        return []

    raw = result.stdout
    # Try UTF-16 LE first (the predominant encoding); fall back to UTF-8
    try:
        text = raw.decode("utf-16-le")
        logger.debug("[WSL2] Decoded distro list as UTF-16 LE")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="ignore")
        logger.debug("[WSL2] Decoded distro list as UTF-8 (fallback)")

    # Strip null bytes left over from UTF-16 padding
    distros = [line.strip().replace("\x00", "") for line in text.splitlines()]
    distros = [d for d in distros if d]

    if distros:
        logger.info("[WSL2] Found %d distro(s): %s", len(distros), distros)
    else:
        logger.info("[WSL2] wsl.exe responded but listed no distros")

    return distros


# ── WSL2 setup ────────────────────────────────────────────────────────────────

# This script runs inside the WSL2 distro via stdin so the webhook URL is
# passed as argv[1] and never needs to be shell-escaped or embedded in source.
# All print() calls are captured by the caller and forwarded to the logger.
_WSL_SETUP_SCRIPT = """\
import json, os, sys

webhook_url = sys.argv[1]
path = os.path.expanduser("~/.claude/settings.json")
settings_dir = os.path.dirname(path)

print(f"target    : {path}", flush=True)
print(f"url       : {webhook_url}", flush=True)

# Ensure ~/.claude/ exists
if not os.path.exists(settings_dir):
    os.makedirs(settings_dir, exist_ok=True)
    print(f"created   : {settings_dir}", flush=True)
else:
    print(f"directory : {settings_dir} (exists)", flush=True)

# Load existing settings
settings = {}
if os.path.exists(path):
    print("file      : exists, reading...", flush=True)
    try:
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
        existing_hooks = list(settings.get("hooks", {}).keys())
        print(f"current hooks: {existing_hooks if existing_hooks else '(none)'}", flush=True)
    except json.JSONDecodeError as exc:
        print(f"warning   : malformed JSON ({exc}), starting fresh", flush=True)
        settings = {}
    except OSError as exc:
        print(f"warning   : cannot read file ({exc}), starting fresh", flush=True)
        settings = {}
else:
    print("file      : not found, will create new settings.json", flush=True)

# Build and merge hooks
block = {"hooks": [{"type": "http", "url": webhook_url, "async": True}]}
if "hooks" not in settings:
    settings["hooks"] = {}

target_events = ["Notification", "Stop", "StopFailure", "PermissionRequest"]
for event in target_events:
    action = "overwriting" if event in settings["hooks"] else "adding"
    print(f"{action:9} : '{event}' hook", flush=True)
settings["hooks"].update({e: [block] for e in target_events})

# Write updated settings
try:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    print(f"written   : {path}", flush=True)
    print(f"hooks set : {list(settings['hooks'].keys())}", flush=True)
except OSError as exc:
    print(f"error     : cannot write {path}: {exc}", file=sys.stderr, flush=True)
    sys.exit(1)
"""


def setup_wsl2(port: int, token: str, distro: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """
    Configure Claude Code hooks inside a WSL2 distro.

    Sends _WSL_SETUP_SCRIPT to python3 via stdin so the webhook URL is never
    shell-interpolated.  Uses 'localhost' as the webhook host — WSL2 forwards
    localhost connections from inside the distro to the Windows host by default.

    Returns (success, error_message_or_None).
    """
    label = distro or "(default distro)"
    # Token is included in the URL so the server can authenticate requests from
    # Claude Code running inside the WSL2 distro.
    webhook_url = f"http://localhost:{port}/webhook?token={token}"

    logger.info("[WSL2:%s] Configuring hooks", label)
    logger.info("[WSL2:%s] Webhook URL: %s", label, webhook_url)
    logger.info(
        "[WSL2:%s] Using 'localhost' — WSL2 forwards this to the Windows host "
        "via localhostForwarding (enabled by default). If you have disabled "
        "localhost forwarding in .wslconfig, manually replace 'localhost' with "
        "your Windows host IP in ~/.claude/settings.json inside the distro.",
        label,
    )

    cmd = ["wsl.exe"]
    if distro:
        cmd += ["--distribution", distro]
    # python3 -  reads the script from stdin; argv[1] carries the webhook URL.
    cmd += ["--", "python3", "-", webhook_url]
    logger.info("[WSL2:%s] Running: %s", label, " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            input=_WSL_SETUP_SCRIPT,
            capture_output=True,
            text=True,
            # Explicit UTF-8 ensures the script is transmitted as UTF-8 to WSL2's
            # python3 regardless of the Windows system code page.  Without this,
            # text=True uses the ANSI code page (e.g. CP1252) which encodes
            # non-ASCII chars like em dashes as single bytes (\x97, etc.) that
            # Python 3 inside the distro rejects with "Non-UTF-8 code" SyntaxError.
            encoding="utf-8",
            timeout=30,
        )

        # Forward every line of the embedded script's output to our logger
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                logger.info("[WSL2:%s] %s", label, line)
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                logger.warning("[WSL2:%s] stderr: %s", label, line)

        if result.returncode != 0:
            error = result.stderr.strip() or f"exit code {result.returncode}"
            logger.error("[WSL2:%s] ✗ Setup failed: %s", label, error)
            return False, error

        logger.info("[WSL2:%s] ✓ Hooks configured successfully", label)
        return True, None

    except subprocess.TimeoutExpired:
        logger.error("[WSL2:%s] ✗ Command timed out after 30 s", label)
        return False, "WSL2 command timed out (30 s)"
    except OSError as exc:
        logger.error("[WSL2:%s] ✗ OS error launching wsl.exe: %s", label, exc)
        return False, str(exc)


# ── Combined entry point ──────────────────────────────────────────────────────

def setup_all(port: int) -> SetupResult:
    """
    Detect available environments and configure Claude Code hooks in all of them.

    Windows is always configured.  WSL2 is configured if wsl.exe is reachable
    and at least one distro is installed — only the default (first) distro is
    targeted; users with multiple distros can run scripts/setup-hooks.sh
    manually inside each additional distro.

    The webhook token is read from state.json and embedded in every hook URL.
    ensure_webhook_token() must have been called from the main thread before
    this function runs so the token is guaranteed to exist.

    This function may take several seconds when WSL2 is present (subprocess
    round-trips to the distro).  Call it from a background thread.
    """
    from state import get_webhook_token
    token = get_webhook_token() or ""

    logger.info("=== cc-notify hook setup starting (port %d) ===", port)
    result = SetupResult()

    # ── Step 1/2: Windows ────────────────────────────────────────────────────
    logger.info("--- [1/2] Windows Claude Code ---")
    result.windows_ok, result.windows_error = setup_windows(port, token)
    if result.windows_ok:
        logger.info("[1/2] Windows ✓")
    else:
        logger.error("[1/2] Windows ✗ — %s", result.windows_error)

    # ── Step 2/2: WSL2 ───────────────────────────────────────────────────────
    logger.info("--- [2/2] WSL2 Claude Code ---")
    distros = _wsl2_distros()
    result.wsl2_available = bool(distros)

    if not distros:
        logger.info("[2/2] No WSL2 distros found — skipping WSL2 configuration")
    else:
        result.wsl2_distro = distros[0]
        if len(distros) > 1:
            logger.info(
                "[2/2] %d distros found: %s — configuring '%s' only. "
                "Run scripts/setup-hooks.sh inside any other distro manually.",
                len(distros), distros, result.wsl2_distro,
            )
        result.wsl2_ok, result.wsl2_error = setup_wsl2(port, token, result.wsl2_distro)
        if result.wsl2_ok:
            logger.info("[2/2] WSL2 (%s) ✓", result.wsl2_distro)
        else:
            logger.error("[2/2] WSL2 (%s) ✗ — %s", result.wsl2_distro, result.wsl2_error)

    logger.info("=== Hook setup complete: %s ===", result.summary())
    return result
