"""
Windows toast notification wrapper.

Abstracts win11toast so the rest of the app deals only with high-level
event types (permission, idle, stop, generic). All calls are fire-and-forget;
errors are logged but never propagated — a broken notification must not
take down the webhook server.

App identity
  Windows identifies the sending application by its AUMID (Application User
  Model ID). The default win11toast AUMID is 'Python', which makes every
  notification header read "Python". We register a custom AUMID
  (cc-notify.ClaudeCodeAgent) in HKCU on first use so notifications display
  "Claude Code Agent" instead.  The registration is done lazily before the
  first notification and cached for the session.

Notification images
  Each notification picks a random PNG from assets/notification_images/ and
  shows it as a hero image (the banner below the notification body).  At
  runtime the images are resolved via sys._MEIPASS when frozen by PyInstaller,
  or from <repo>/assets/notification_images/ in development.

  Recommended image dimensions: 364×180 px (2:1 landscape). Square images
  work but Windows will centre-crop them to the hero aspect ratio.

VS Code focus on click
  Toast notifications that carry a cwd field use a cc-notify://focus URI as
  the on_click value.  Routing the click through the cc-notify protocol handler
  rather than dispatching vscode:// directly solves the cross-virtual-desktop
  focus problem:

    vscode:// (old): Windows shell → short-lived Code.exe (has foreground rights)
                     → IPC forward to existing VS Code → SetForegroundWindow
                     (rights already gone — cannot switch virtual desktops)

    cc-notify://focus (new): Windows shell → cc-notify.exe (has foreground rights)
                             → SetForegroundWindow(vscode_hwnd) [rights still held]
                             → virtual desktop switches on Windows 11
                             → cmd /c start vscode://... (navigation only)

  The cc-notify://focus URI carries the vscode:// target as a percent-encoded
  query parameter.  The cc-notify protocol handler is registered in HKCU by
  _ensure_app_registered() so it is always current.

  A Python callable on_click is unreliable for Action Center activations:
  win11toast dispatches it via asyncio call_soon_threadsafe(), but by the time
  a timed-out toast is clicked the asyncio future is already resolved and the
  activation event is silently discarded.  URI-based activation works
  regardless of when the user clicks.
"""
from __future__ import annotations

import logging
import os.path
import random
import sys
import threading
import urllib.parse
from pathlib import Path
from typing import Optional

from messages import IDLE_MESSAGES, PERMISSION_MESSAGES, STOP_FAILURE_MESSAGES, STOP_MESSAGES

logger = logging.getLogger(__name__)

# AUMID used to identify cc-notify to the Windows notification framework.
# Registered in HKCU\Software\Classes\AppUserModelId\<_AUMID> on first use.
_AUMID = "cc-notify.ClaudeCodeAgent"
_DISPLAY_NAME = "Claude Code Agent"

# WinRT system sound events used per notification type.
_SOUNDS: dict[str, str] = {
    "permission":   "ms-winsoundevent:Notification.Looping.Alarm2",
    "stop_failure": "ms-winsoundevent:Notification.Looping.Alarm",
    "idle":         "ms-winsoundevent:Notification.Default",
    "stop":         "ms-winsoundevent:Notification.Default",
    "generic":      "ms-winsoundevent:Notification.Default",
}

# Cached after first detection — wsl.exe is called at most once per session.
_wsl2_default_distro: Optional[str] = None

# Guards AUMID registration so it runs exactly once per process.
_app_registered = False
_app_registered_lock = threading.Lock()


# ── App identity ──────────────────────────────────────────────────────────────

def _ensure_app_registered() -> None:
    """
    Register cc-notify's AUMID in HKCU so Windows displays 'Claude Code Agent'
    in notification headers instead of 'Python'.

    Also calls SetCurrentProcessExplicitAppUserModelID so the OS associates
    this process with the registered entry. Both operations are no-ops on
    non-Windows platforms (e.g. WSL2 development).
    """
    global _app_registered
    if _app_registered:
        return
    with _app_registered_lock:
        if _app_registered:
            return
        if sys.platform == "win32":
            import ctypes
            import winreg
            try:
                key_path = rf"Software\Classes\AppUserModelId\{_AUMID}"
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, _DISPLAY_NAME)
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_AUMID)
                logger.debug("Registered AUMID %s → %r", _AUMID, _DISPLAY_NAME)
            except Exception as exc:
                logger.warning("Could not register app AUMID: %s", exc)
            try:
                exe = sys.executable
                cmd = f'"{exe}" "%1"'
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\cc-notify") as k:
                    winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:cc-notify Protocol")
                    winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
                with winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER, r"Software\Classes\cc-notify\DefaultIcon"
                ) as k:
                    winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'"{exe}",0')
                with winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER, r"Software\Classes\cc-notify\shell\open\command"
                ) as k:
                    winreg.SetValueEx(k, None, 0, winreg.REG_SZ, cmd)
                logger.debug("Registered cc-notify:// URI scheme → %s", exe)
            except Exception as exc:
                logger.warning("Could not register cc-notify:// URI scheme: %s", exc)
        _app_registered = True


# ── Notification images ───────────────────────────────────────────────────────

def _notification_image_dir() -> Path:
    """
    Return the directory containing notification hero images.

    When frozen by PyInstaller, files from assets/notification_images/ are
    extracted under sys._MEIPASS/notification_images/.  In development they
    live at <repo_root>/assets/notification_images/.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "notification_images"  # type: ignore[attr-defined]
    return Path(__file__).parent.parent / "assets" / "notification_images"


def _random_image_uri() -> Optional[str]:
    """
    Pick a random PNG from the notification images directory and return a
    file:// URI suitable for win11toast's image parameter, or None if no
    images are available.
    """
    try:
        images = list(_notification_image_dir().glob("*.png"))
        if not images:
            return None
        chosen = random.choice(images)
        # as_posix() converts backslashes to forward slashes on Windows:
        # C:\path\to\file.png → file:///C:/path/to/file.png
        return "file:///" + chosen.as_posix()
    except Exception as exc:
        logger.debug("Could not pick notification image: %s", exc)
        return None


# ── VS Code URI ───────────────────────────────────────────────────────────────

def _get_default_wsl2_distro() -> Optional[str]:
    """
    Return the name of the default WSL2 distro (e.g. "Ubuntu-24.04").

    The result is cached after the first successful call so subsequent
    notifications pay no subprocess overhead.  Returns None if WSL2 is
    unavailable or detection fails — callers should handle this gracefully.
    """
    global _wsl2_default_distro
    if _wsl2_default_distro is not None:
        return _wsl2_default_distro

    import subprocess
    try:
        result = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return None

        # WSL2 outputs UTF-16 LE on most Windows versions; fall back to UTF-8.
        try:
            text = result.stdout.decode("utf-16-le")
        except UnicodeDecodeError:
            text = result.stdout.decode("utf-8", errors="ignore")

        for line in text.splitlines():
            name = line.strip().replace("\x00", "")
            if name:
                _wsl2_default_distro = name
                logger.debug("Detected default WSL2 distro: %s", name)
                return name
    except Exception as exc:
        logger.debug("Could not detect WSL2 distro: %s", exc)
    return None


def _vscode_uri(cwd: str) -> Optional[str]:
    """
    Build a cc-notify://focus URI that embeds the vscode:// workspace path.

    Wrapping the click in a cc-notify:// URI lets the protocol handler call
    SetForegroundWindow while still holding the foreground activation rights
    granted by Windows shell — which on Windows 11 switches the active virtual
    desktop.  The vscode:// URI is forwarded afterwards for navigation only.

    Only absolute paths pass the os.path.isabs() guard.  Values that are not
    filesystem paths are rejected, preventing crafted cwd payloads from
    reaching VS Code as a CLI flag.

    Returns None when the URI cannot be constructed (empty cwd, non-absolute
    path, or WSL2 not available for a Linux path).
    """
    if not cwd or not os.path.isabs(cwd):
        return None

    if cwd.startswith("/"):
        # WSL2/Linux path — use the vscode-remote URI scheme so VS Code opens
        # the folder as a proper Remote-WSL session.
        distro = _get_default_wsl2_distro()
        if not distro:
            logger.warning(
                "Cannot build VS Code URI for WSL2 path: distro not detected. "
                "Ensure WSL2 is installed and at least one distro is running."
            )
            return None
        encoded_path = urllib.parse.quote(cwd, safe="/")
        encoded_distro = urllib.parse.quote(distro, safe="")
        vscode_target = f"vscode://vscode-remote/wsl+{encoded_distro}{encoded_path}"
    else:
        # Windows absolute path.
        forward = cwd.replace("\\", "/")
        vscode_target = f"vscode://file/{urllib.parse.quote(forward, safe=':/')}"

    # Embed the vscode:// URI as a query parameter so the focus handler can
    # reconstruct and dispatch it after activating VS Code's window.
    return f"cc-notify://focus?uri={urllib.parse.quote(vscode_target, safe='')}"


# ── Core send ─────────────────────────────────────────────────────────────────

def _send(
    title: str,
    body: str,
    sound_key: str,
    sound_enabled: bool,
    on_click=None,
) -> None:
    """Dispatch a single toast notification. Swallows all exceptions."""
    _ensure_app_registered()
    try:
        from win11toast import notify  # imported lazily — not available outside Windows

        kwargs: dict = {}
        if sound_enabled:
            kwargs["audio"] = {"src": _SOUNDS.get(sound_key, _SOUNDS["generic"])}
        if on_click is not None:
            kwargs["on_click"] = on_click

        image_uri = _random_image_uri()
        if image_uri:
            kwargs["image"] = {"placement": "hero", "src": image_uri}

        notify(title, body, app_id=_AUMID, **kwargs)
        logger.debug("Notification sent: %s", title)
    except Exception as exc:
        logger.warning("Failed to send notification: %s", exc)


# ── Public notification functions ─────────────────────────────────────────────

def _pick(pool: list[str]) -> str:
    """Return a random entry from pool, falling back to pool[0] on error."""
    try:
        return random.choice(pool)
    except Exception:
        return pool[0]


def permission(message: str, sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code is paused waiting for the user to approve an action."""
    _send(
        "Claude Code — Permission Required", _pick(PERMISSION_MESSAGES),
        "permission", sound_enabled,
        on_click=_vscode_uri(cwd),
    )


def idle(message: str, sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code is idle and waiting for the user to respond."""
    _send(
        "Claude Code — Waiting for Input", _pick(IDLE_MESSAGES),
        "idle", sound_enabled,
        on_click=_vscode_uri(cwd),
    )


def stop(sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code has finished generating a response."""
    _send(
        "Claude Code — Task Complete", _pick(STOP_MESSAGES),
        "stop", sound_enabled,
        on_click=_vscode_uri(cwd),
    )


# Maps the stop_reason values Claude Code sends with a StopFailure event to
# a descriptive toast title so the user can see the error type at a glance.
_STOP_FAILURE_TITLES: dict[str, str] = {
    "rate_limit":            "Claude Code — Rate Limited",
    "authentication_failed": "Claude Code — Auth Failed",
    "billing_error":         "Claude Code — Billing Error",
    "invalid_request":       "Claude Code — Request Error",
    "server_error":          "Claude Code — Server Error",
    "max_output_tokens":     "Claude Code — Token Limit Reached",
}
_STOP_FAILURE_TITLE_DEFAULT = "Claude Code — Something Went Wrong"


def stop_failure(stop_reason: str = "", sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code's turn ended due to an API or server error."""
    title = _STOP_FAILURE_TITLES.get(stop_reason, _STOP_FAILURE_TITLE_DEFAULT)
    _send(
        title, _pick(STOP_FAILURE_MESSAGES),
        "stop_failure", sound_enabled,
        on_click=_vscode_uri(cwd),
    )


def generic(title: str, message: str, sound_enabled: bool = True) -> None:
    """Fallback for any other Claude Code notification type. No VS Code focus."""
    _send(title or "Claude Code", message, "generic", sound_enabled)


def update_available(current: str, latest: str, install_uri: str, sound_enabled: bool = True) -> None:
    """
    Notify that a newer release is available.

    The toast is clickable — clicking it activates install_uri, which is the
    cc-notify:// protocol URI that signals the running instance to apply the
    update without opening a browser.
    """
    _ensure_app_registered()
    try:
        from win11toast import notify

        kwargs: dict = {}
        if sound_enabled:
            kwargs["audio"] = {"src": _SOUNDS["generic"]}

        image_uri = _random_image_uri()
        if image_uri:
            kwargs["image"] = {"placement": "hero", "src": image_uri}

        notify(
            "cc-notify — Update Available",
            f"Version {latest} is available. Click to install automatically.",
            on_click=install_uri,
            app_id=_AUMID,
            **kwargs,
        )
        logger.debug("Update notification sent: %s -> %s", current, latest)
    except Exception as exc:
        logger.warning("Failed to send update notification: %s", exc)
